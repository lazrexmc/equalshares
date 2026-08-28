#!/usr/bin/env python3
"""export_site.py — EqualShares "The Roll Call": DB -> static site JSON artifacts.

Reads data/rollcall.db and writes exactly the artifacts the site renders:

    site/data/meta.json              filer + filing + engine-run provenance + totals
    site/data/rollup.json            per-category rollup (NO blended cross-category number)
    site/data/category/<slug>.json   per-category vote records, with receipts

Contract points enforced here:
  * ANTI-BLEND: rollup.json's only top-level key is "categories". No blended
    cross-category concordance number is computed or written anywhere. One real
    filing is ~73% director elections; a blended number measures nothing.
  * Slugs are derived HERE and only here; the site consumes them verbatim.
  * Every record's source_url is copied verbatim from the DB (stored at ingest
    time) — never constructed at export time.
  * Failure is not emptiness: an empty DB, mixed provenance, an enum violation,
    a slug collision, or an empty source_url is a loud exit(1), never a quiet
    empty artifact.
  * Deterministic output: sorted JSON keys, stable orderings — a re-run over the
    same DB is byte-identical except generated_at.

Stdlib only (Python 3.14). Run from anywhere: paths anchor on this file.
"""

import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent
ROOT = PIPELINE_DIR.parent
DB_PATH = ROOT / "data" / "rollcall.db"
SITE_DATA = ROOT / "site" / "data"
CATEGORY_DIR = SITE_DATA / "category"

UNCATEGORIZED = "UNCATEGORIZED"
VOTE_ENUM = ("FOR", "AGAINST", "ABSTAIN", "WITHHOLD")


def log(msg=""):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def die(msg):
    log(f"ERROR: {msg}")
    sys.exit(1)


def bucket(category_type):
    """Map a stored category_type to its display bucket.

    None / blank -> UNCATEGORIZED so every record lands in exactly one category
    and sum(category n) == totals.records holds. Raw values in the DB are never
    altered; this is a display grouping only.
    LOCKSTEP: pipeline/checks.py G7 carries an identical copy of this function.
    Change both or G7 fails — which is the point.
    """
    if category_type is None or str(category_type).strip() == "":
        return UNCATEGORIZED
    return category_type


def slugify(category):
    """Contract slug rule: lowercase; every run of non-alphanumerics -> single
    '-'; trim '-'. LOCKSTEP with pipeline/checks.py G7."""
    return re.sub(r"[^a-z0-9]+", "-", category.lower()).strip("-")


def record_sort_key(r):
    """Order: meeting_date, issuer_name, seq — None first, matching SQL ASC.
    LOCKSTEP with pipeline/checks.py G7 (which reads the JSON back)."""
    return (
        r["meeting_date"] is not None,
        r["meeting_date"] or "",
        r["issuer_name"] is not None,
        r["issuer_name"] or "",
        r["seq"],
    )


def dump_json(path, obj):
    text = json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    return len(text.encode("utf-8"))


def load_thin_n():
    """thin_n comes from CONFIG in pipeline/sources.py — the same CONFIG that is
    hashed into config_hash, so changing it changes the engine_run_id."""
    sys.path.insert(0, str(PIPELINE_DIR))
    try:
        from sources import CONFIG  # noqa: PLC0415 — deliberate late import
    except Exception as e:
        die(f"cannot import CONFIG from pipeline/sources.py: {e!r}")
    if "thin_n" not in CONFIG:
        die("CONFIG in pipeline/sources.py has no 'thin_n' key (contract: thin_n = 5)")
    try:
        return int(CONFIG["thin_n"])
    except (TypeError, ValueError):
        die(f"CONFIG['thin_n'] is not an integer: {CONFIG['thin_n']!r}")


def main():
    log("EqualShares export_site — data/rollcall.db -> site/data JSON artifacts")
    thin_n = load_thin_n()
    log(f"thin_n = {thin_n} (from CONFIG in pipeline/sources.py)")
    if not DB_PATH.exists():
        die(f"database not found: {DB_PATH} — run the ingest + extract first")

    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row

    filings = con.execute(
        "SELECT * FROM filings ORDER BY (filed_at IS NULL), filed_at DESC, accession DESC"
    ).fetchall()
    if not filings:
        die("filings table is empty — nothing to export")
    filing = filings[0]
    if len(filings) > 1:
        log(f"note: {len(filings)} filings in DB; exporting the most recent: {filing['accession']}")
    acc = filing["accession"]

    filer = con.execute(
        "SELECT cik, name FROM filers WHERE cik = ?", (filing["cik"],)
    ).fetchone()
    if filer is None:
        die(f"filings.cik {filing['cik']!r} has no filers row — referential integrity broken")

    run_ids = [
        r[0]
        for r in con.execute(
            "SELECT DISTINCT engine_run_id FROM vote_records WHERE accession = ? "
            "ORDER BY engine_run_id",
            (acc,),
        ).fetchall()
    ]
    if len(run_ids) == 0:
        die(
            f"no vote_records for {acc} — refusing to export an empty site "
            "(failure is not emptiness; run extract.py, and if it found zero records "
            "that is trap 6.8, not a quiet filer)"
        )
    if len(run_ids) > 1:
        die(
            f"vote_records for {acc} carry {len(run_ids)} distinct engine_run_ids "
            f"{run_ids} — mixed provenance; re-run extract.py before exporting"
        )
    engine = con.execute(
        "SELECT engine_run_id, engine_version, code_fingerprint, config_hash, git_commit "
        "FROM engine_runs WHERE engine_run_id = ?",
        (run_ids[0],),
    ).fetchone()
    if engine is None:
        die(f"engine_run_id {run_ids[0]} has no engine_runs manifest row (orphan provenance)")

    rows = con.execute(
        """
        SELECT seq, issuer_name, cusip, isin, meeting_date, category_type,
               vote_description, shares_voted, how_voted, how_voted_raw,
               mgmt_rec, mgmt_rec_raw, vote_source, categories_all, source_url
          FROM vote_records
         WHERE accession = ?
         ORDER BY seq
        """,
        (acc,),
    ).fetchall()
    con.close()
    log(f"loaded {len(rows)} vote_records for {acc}")

    # -- validate before publishing: never emit guessed or malformed rows -----
    for r in rows:
        for col in ("how_voted", "mgmt_rec"):
            v = r[col]
            if v is not None and v not in VOTE_ENUM:
                die(
                    f"vote_records seq {r['seq']}: {col}={v!r} is outside the "
                    f"normalization enum {VOTE_ENUM} — extractor contract broken; "
                    "fix extract.py, do not export"
                )
        su = r["source_url"]
        if not isinstance(su, str) or su.strip() == "":
            die(f"vote_records seq {r['seq']}: empty source_url — receipts are mandatory")

    # -- bucket into categories ------------------------------------------------
    by_cat = {}
    for r in rows:
        by_cat.setdefault(bucket(r["category_type"]), []).append(r)

    slug_owner = {}
    categories = []
    for name, rs in by_cat.items():
        slug = slugify(name)
        if not slug:
            die(f"category {name!r} slugifies to an empty string — cannot publish it")
        if slug in slug_owner and slug_owner[slug] != name:
            die(f"slug collision: {slug_owner[slug]!r} and {name!r} both slugify to {slug!r}")
        slug_owner[slug] = name

        n = len(rs)
        votes = {k: 0 for k in VOTE_ENUM}
        n_comparable = 0
        with_mgmt = 0
        shares_sum = 0.0
        any_shares = False
        for r in rs:
            hv, mr = r["how_voted"], r["mgmt_rec"]
            if hv in votes:
                votes[hv] += 1
            if hv is not None and mr is not None:
                n_comparable += 1
                if hv == mr:
                    with_mgmt += 1
            sv = r["shares_voted"]
            if sv is not None:
                shares_sum += sv
                any_shares = True
        # Tri-valued honesty (review finding 2026-08-28): 'unparseable' (raw
        # kept, normalization failed) and 'absent in source' (no how-voted at
        # all) are DIFFERENT states and the old single OTHER column conflated
        # them - the page visibly contradicted its own totals line because of
        # it. enum + UNPARSEABLE + ABSENT == n exactly.
        votes["UNPARSEABLE"] = sum(
            1 for r in rs
            if r["how_voted_raw"] is not None and r["how_voted"] is None)
        votes["ABSENT"] = sum(1 for r in rs if r["how_voted_raw"] is None)
        with_mgmt_pct = round(100 * with_mgmt / n_comparable, 1) if n_comparable else None
        categories.append(
            {
                "category": name,
                "slug": slug,
                "n": n,
                "votes": votes,
                "shares_voted_total": round(shares_sum, 4) if any_shares else None,
                "n_comparable": n_comparable,
                "with_mgmt": with_mgmt,
                "with_mgmt_pct": with_mgmt_pct,
                "thin": n_comparable < thin_n,
            }
        )
    categories.sort(key=lambda c: (-c["n"], c["category"]))

    totals = {
        "records": len(rows),
        "categories": len(categories),
        "comparable_records": sum(c["n_comparable"] for c in categories),
        "unparseable_how_voted": sum(
            1 for r in rows if r["how_voted_raw"] is not None and r["how_voted"] is None
        ),
        # Records the filer tagged with MORE than one category. Each is grouped
        # under its FIRST category only (no double counting; sum(n)==records
        # stays exact); this count makes that editorial rule visible on the page.
        "multi_category_records": sum(
            1 for r in rows
            if (r["categories_all"] or "").find("|") != -1
        ),
    }
    if sum(c["n"] for c in categories) != totals["records"]:
        die("internal invariant broken: sum(category n) != totals.records")

    try:
        filing_obj = {
            k: filing[k]
            for k in (
                "accession", "form", "filed_at", "period_of_report", "series_name", "vote_doc_view_url",
                "vote_doc_name", "vote_doc_type", "vote_doc_url", "index_url",
                "raw_sha256", "raw_bytes", "fetched_at",
            )
        }
        engine_obj = {
            k: engine[k]
            for k in (
                "engine_run_id", "engine_version", "code_fingerprint",
                "config_hash", "git_commit",
            )
        }
    except (IndexError, KeyError) as e:
        die(f"DB schema is missing an expected column: {e!r}")

    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "filer": {"cik": filer["cik"], "name": filer["name"]},
        "filing": filing_obj,
        "engine_run": engine_obj,
        "totals": totals,
        "thin_n": thin_n,
    }

    # -- write -----------------------------------------------------------------
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    CATEGORY_DIR.mkdir(parents=True, exist_ok=True)
    stale = sorted(CATEGORY_DIR.glob("*.json"))
    for p in stale:
        p.unlink()
    if stale:
        log(f"removed {len(stale)} stale category file(s) before writing")

    b = dump_json(SITE_DATA / "meta.json", meta)
    log(
        f"wrote site/data/meta.json  ({b} bytes; records={totals['records']}, "
        f"categories={totals['categories']}, comparable={totals['comparable_records']}, "
        f"unparseable_how_voted={totals['unparseable_how_voted']})"
    )
    b = dump_json(SITE_DATA / "rollup.json", {"categories": categories})
    log(
        f"wrote site/data/rollup.json  ({b} bytes; {len(categories)} categories "
        "sorted n desc; NO blended top-level number)"
    )
    for c in categories:
        recs = sorted(by_cat[c["category"]], key=record_sort_key)
        payload = {
            "category": c["category"],
            "slug": c["slug"],
            "n": c["n"],
            "records": [
                {
                    "seq": r["seq"],
                    "issuer_name": r["issuer_name"],
                    "cusip": r["cusip"],
                    "isin": r["isin"],
                    "meeting_date": r["meeting_date"],
                    "vote_description": r["vote_description"],
                    "shares_voted": r["shares_voted"],
                    "how_voted": r["how_voted"],
                    "how_voted_raw": r["how_voted_raw"],
                    "mgmt_rec": r["mgmt_rec"],
                    "mgmt_rec_raw": r["mgmt_rec_raw"],
                    "vote_source": r["vote_source"],
                    "categories_all": r["categories_all"],
                    "source_url": r["source_url"],
                }
                for r in recs
            ],
        }
        b = dump_json(CATEGORY_DIR / f"{c['slug']}.json", payload)
        log(f"wrote site/data/category/{c['slug']}.json  ({b} bytes; n={c['n']})")

    log(
        f"export complete: filing {acc} ({filing['form']}, period "
        f"{filing['period_of_report']}), engine_run {engine['engine_run_id']}"
    )


if __name__ == "__main__":
    main()
