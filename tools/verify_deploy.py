#!/usr/bin/env python
"""verify_deploy.py - does the origin serve what git holds?

Shape: Glizzness tools/verify_deploy.py (the standard's deploy verifier; EventFinds and VisibleGov are
its other consumers), with this site's constants and one addition - the JSON content-type check,
because README's Live section claims "JSON is served as application/json" and a claim needs a check.

WHY (Glizzness, 2026-08-29): a site was pushed and never appeared; the GitHub integration had died
weeks earlier with no failure anywhere. "Every push redeploys" is a sentence until something reads
the bytes at the origin.

  python tools/verify_deploy.py                  compare the marker set against the live origin
  python tools/verify_deploy.py --origin https://<preview>.equalshares.pages.dev
  python tools/verify_deploy.py --json

Exit 0 only when every marker is DEPLOYED. STALE = the origin serves different bytes (deploy lagging
or dead); MISSING = 404 at the origin (never deployed, or a redirect ate it). Stdlib only. Not in CI
on purpose: a push is not yet a deploy, so CI would race it. Run after pushing site/.
"""
import argparse
import json
import re
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
ORIGIN = "https://equalshares.pages.dev"
# Files whose bytes must match the origin exactly: the page, every script, the stylesheet, and the
# two publication files a reader's first load fetches. Headers are checked separately (not a file).
MARKERS = [
    ("site/index.html", "/"),
    ("site/js/rollcall.js", "/js/rollcall.js"),
    ("site/js/data.js", "/js/data.js"),
    ("site/js/receipts.js", "/js/receipts.js"),
    ("site/css/site.css", "/css/site.css"),
    ("site/data/meta.json", "/data/meta.json"),
    ("site/data/rollup.json", "/data/rollup.json"),
    ("site/_headers", None),          # not served; listed so a reader sees it is deliberately skipped
]
HEADER_MARKERS = ["content-security-policy", "x-content-type-options", "referrer-policy"]
JSON_MARKERS = ["/data/meta.json", "/data/rollup.json"]   # must come back as application/json
USER_AGENT = "equalshares-verify-deploy/1.0"

# Cloudflare Web Analytics injects exactly this tag into HTML at the edge (a zone setting, not a
# file in git). Not enabled here as of 2026-08-29; kept so enabling it later is not read as drift.
_CF_BEACON = re.compile(rb"<script[^>]*static\.cloudflareinsights\.com/beacon\.min\.js[^>]*></script>")
_SEQ = [0]


def compare(local, remote):
    """DEPLOYED when the origin's bytes equal git's, ignoring line endings, whitespace runs and the
    edge-injected analytics tag. Any other byte is STALE."""
    if remote is None:
        return "MISSING"
    norm = lambda b: re.sub(rb"\s+", b" ", _CF_BEACON.sub(b"", b.replace(b"\r\n", b"\n"))).strip()
    return "DEPLOYED" if norm(local) == norm(remote) else "STALE"


def bust(url):
    """A unique query string per request: the one thing an edge cannot answer from an old copy.
    Pages ignores unknown queries; a request-header no-cache is only advisory."""
    _SEQ[0] += 1
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}vd={int(time.time() * 1000)}{_SEQ[0]}"


def fetch(url):
    req = urllib.request.Request(bust(url), headers={"User-Agent": USER_AGENT, "Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read(), {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        return e.code, None, {}
    except Exception as e:
        return 0, None, {"error": f"{type(e).__name__}: {e}"}


def main():
    ap = argparse.ArgumentParser(description="compare local site/ files with what the origin serves")
    ap.add_argument("--origin", default=ORIGIN)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    origin = a.origin.rstrip("/")

    results = []
    for local_rel, path in MARKERS:
        if path is None:
            continue
        local = (ROOT / local_rel).read_bytes()
        status, body, headers = fetch(origin + path)
        verdict = compare(local, body if status == 200 else None)
        results.append({"file": local_rel, "url": origin + path, "http": status, "verdict": verdict})
        if path in JSON_MARKERS:
            ctype = headers.get("content-type", "")
            results.append({"file": local_rel, "url": origin + path, "http": status,
                            "verdict": "DEPLOYED" if ctype.startswith("application/json") else "STALE",
                            "header": f"content-type={ctype or '(none)'}"})

    status, _, headers = fetch(origin + "/")
    for h in HEADER_MARKERS:
        results.append({"file": "site/_headers", "url": origin + "/", "http": status,
                        "verdict": "DEPLOYED" if h in headers else "MISSING", "header": h})

    bad = [r for r in results if r["verdict"] != "DEPLOYED"]
    if a.json:
        print(json.dumps({"origin": origin, "results": results, "failed": len(bad)}, indent=2))
        return 1 if bad else 0

    print(f"\nDeploy check - local site/ vs {origin}\n")
    for r in results:
        label = r.get("header", r["file"])
        mark = "PASS" if r["verdict"] == "DEPLOYED" else "FAIL"
        print(f"  {mark}  {label:44s} {r['verdict']:9s} HTTP {r['http']}")
    if bad:
        print(f"\n  {len(bad)} marker(s) not deployed. The origin is NOT serving the pushed site/ - check")
        print("  Cloudflare Dashboard -> Workers & Pages -> equalshares -> Deployments (failed build? integration gone?).\n")
        return 1
    print("\n  ALL DEPLOYED - the origin serves exactly what git holds.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
