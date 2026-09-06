#!/usr/bin/env python
"""verify_receipts.py - does every published receipt actually RENDER at EDGAR?

WHY (2026-09-06). Every row on this site carries one receipt per filing, and the site's
load-bearing promise is that a reader can follow it to the source. Four of eight filings were
publishing a receipt that returned **HTTP 200 whose body is "XML input exceeds maximum allowed
size." followed by a 404 page** - EDGAR refuses to render documents above a size limit, and
iShares (172 MB), Fidelity (132 MB), SPDR (101 MB) and Schwab (84 MB) all exceed it. A status-code
check calls that healthy. Nothing in eleven gates, nine claim checks or three cold-read rounds
looked at the body, so half the receipts were broken for a week.

This reads the first bytes of every published receipt and of every vote-document link, and fails
when one is a 404 wearing a 200. It reaches the network, so it is NOT one of the offline gates -
it lives here beside verify_deploy and is run after a publish, like that one.

  python tools/verify_receipts.py
  python tools/verify_receipts.py --json

Exit 0 only when every published receipt renders. Stdlib only.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
SITE_DATA = ROOT / "site" / "data"
UA = "EqualShares/0.1 (lancemccarter1316@hotmail.com)"
DELAY = 0.6                      # EDGAR politeness floor is 0.5s
TOO_LARGE = "XML input exceeds maximum allowed size"


def probe(url):
    """Read the first bytes and say what the URL really is. Accept-Encoding: identity on purpose -
    reading the head of a gzipped body yields binary and every broken viewer then reads as fine,
    which is exactly the false negative that shipped once on 2026-09-06."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            head = r.read(600).decode("utf-8", "replace")
            status = r.status
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}", False
    except Exception as e:
        return f"{type(e).__name__}", False
    finally:
        time.sleep(DELAY)
    if TOO_LARGE in head:
        return "200 but: XML input exceeds maximum allowed size", False
    if "404 Not Found" in head or "Error 404" in head:
        return f"{status} but: 404 page in the body", False
    if status != 200:
        return f"HTTP {status}", False
    return f"{status} renders", True


def main():
    ap = argparse.ArgumentParser(description="every published receipt must render, not merely resolve")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    index_path = SITE_DATA / "index.json"
    if not index_path.exists():
        print(f"missing {index_path} - run export_site.py first")
        return 1
    rows = json.loads(index_path.read_text(encoding="utf-8")).get("filings", [])
    results = []
    for row in rows:
        meta = json.loads((SITE_DATA / row["dir"] / "meta.json").read_text(encoding="utf-8"))
        f = meta["filing"]
        # The receipt every row of this filing carries, as extract.py chose it.
        receipt = f.get("vote_doc_view_url") or f.get("index_url")
        checks = [("row receipt", receipt),
                  ("vote document", f.get("vote_doc_url")),
                  ("filing index", f.get("index_url"))]
        for label, url in checks:
            if not url:
                continue
            detail, ok = probe(url)
            results.append({"series": row.get("series_name"), "what": label, "url": url,
                            "detail": detail, "ok": ok,
                            "declared": f.get("vote_doc_view_status")})

    bad = [r for r in results if not r["ok"]]
    if a.json:
        print(json.dumps({"results": results, "failed": len(bad)}, indent=2))
        return 1 if bad else 0

    print(f"\nReceipt check - {len(rows)} filing(s), {len(results)} URL(s)\n")
    for r in results:
        mark = "PASS" if r["ok"] else "FAIL"
        print(f"  {mark}  {(r['series'] or '')[:30]:<31} {r['what']:<14} {r['detail']}")
    if bad:
        print(f"\n  {len(bad)} receipt(s) do not render. A reader following them lands on an error.\n")
        return 1
    print("\n  ALL RECEIPTS RENDER - every published link opens the thing it claims to.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
