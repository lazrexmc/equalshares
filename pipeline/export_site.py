#!/usr/bin/env python3
"""export_site.py - EqualShares "The Roll Call": DB -> static site JSON artifacts.

Reads data/rollcall.db and writes exactly the artifacts the site renders:

    site/data/meta.json              filer + filing + engine-run provenance + totals + the
                                     managementRecommendation semantics check
    site/data/rollup.json            per-category rollup (NO blended cross-category number)
    site/data/category/<slug>.json   per-category records (one row = one vote lot), with receipts

Vocabulary (cold-read round one, 2026-08-29 - four strangers could not tell what a row was):
  * A RECORD is one row: one <voteRecord> lot of one <proxyTable> block, or the single row a
    block with zero lots produces (its how-voted fields absent-in-source, lot_index 0).
  * A LOT is a record that came from a <voteRecord> (lot_index >= 1).
  * A PROPOSAL is one distinct (issuer, CUSIP, meeting date, description, proposed-by); it can
    span several blocks and hold many lots. proposal_no / lot_index / lots_in_proposal come
    from extract.py and are published per record so the page can group lots.
  * managementRecommendation is a PER-LOT field and, in the filing we have, tracks the lot.
    No published headline rests on it. meta.mgmt_rec_semantics carries the computed check that
    says so per filing, so a filer whose field IS the board's view is re-admitted by evidence.

Contract points enforced here:
  * ANTI-BLEND: rollup.json's only top-level key is "categories". Nothing aggregates across
    categories. Inside a category, "% FOR" is split by who proposed the item (voteSource) and
    each cell states its own numerator and denominator.
  * Slugs are derived HERE and only here; the site consumes them verbatim.
  * Every record's source_url is copied verbatim from the DB (stored at ingest) - never built.
  * Failure is not emptiness: an empty DB, mixed provenance, an enum violation, a slug collision,
    an empty source_url, or more than one series in a filing is a loud exit(1).
  * Deterministic output: sorted JSON keys, stable orderings - a re-run over the same DB is
    byte-identical except generated_at.

LOCKSTEP with pipeline/checks.py G7/G8: bucket(), slugify(), source_bucket(), record_sort_key()
and every formula below are recomputed there from the DB. Change both or G7 fails - the point.

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
REC_ENUM = VOTE_ENUM + ("NONE",)
SOURCE_KEYS = ("ISSUER", "SECURITY HOLDER")   # as filed; anything else -> OTHER; blank -> ABSENT


def log(msg=""):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def die(msg):
    log(f"ERROR: {msg}")
    sys.exit(1)


def bucket(category_type):
    """Map a stored category_type to its display bucket. None / blank -> UNCATEGORIZED so
    every record lands in exactly one category and sum(category n) == totals.records holds.
    Raw values in the DB are never altered; display grouping only. LOCKSTEP: checks.py G7."""
    if category_type is None or str(category_type).strip() == "":
        return UNCATEGORIZED
    return category_type


def source_bucket(vote_source):
    """voteSource as filed -> the key the by_source split uses. LOCKSTEP: checks.py G7."""
    if vote_source is None or str(vote_source).strip() == "":
        return "ABSENT"
    v = str(vote_source).strip().upper()
    return v if v in SOURCE_KEYS else "OTHER"


def slugify(category):
    """Contract slug rule: lowercase; every run of non-alphanumerics -> single '-'; trim '-'.
    LOCKSTEP with pipeline/checks.py G7."""
    return re.sub(r"[^a-z0-9]+", "-", category.lower()).strip("-")


def record_sort_key(r):
    """Order: meeting_date, issuer_name, proposal_no, lot_index, seq - None first, matching SQL
    ASC. Lots of one proposal are contiguous, which is what lets the page group them.
    LOCKSTEP with pipeline/checks.py G7 (which reads the JSON back)."""
    return (
        r["meeting_date"] is not None,
        r["meeting_date"] or "",
        r["issuer_name"] is not None,
        r["issuer_name"] or "",
        r["proposal_no"] if r["proposal_no"] is not None else -1,
        r["lot_index"] if r["lot_index"] is not None else -1,
        r["seq"],
    )


def pct(num, den):
    return round(100 * num / den, 1) if den else None


def dump_json(path, obj):
    text = json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    return len(text.encode("utf-8"))


def load_config():
    """thin_n comes from CONFIG in pipeline/sources.py - the same CONFIG that is hashed into
    config_hash, so changing it changes the engine_run_id. It is the ONE typed constant that
    shapes what the page shows, and meta.config publishes it (cold-read round two, R6)."""
    sys.path.insert(0, str(PIPELINE_DIR))
    try:
        from sources import CONFIG  # noqa: PLC0415 - deliberate late import
    except Exception as e:
        die(f"cannot import CONFIG from pipeline/sources.py: {e!r}")
    if "thin_n" not in CONFIG:
        die("CONFIG in pipeline/sources.py has no 'thin_n' key")
    try:
        return int(CONFIG["thin_n"])
    except (TypeError, ValueError):
        die(f"CONFIG['thin_n'] is not an integer: {CONFIG['thin_n']!r}")


def source_cell(rs, thin_n):
    """One by_source cell: how the fund voted on the items one kind of proposer put forward.
    n_voted is the denominator "% FOR" is over: lots with a normalised vote AND shares voted
    above zero (round two, R4: a lot that voted no shares is not a vote cast; those are counted
    in zero_share_lots beside it). Every number a reader might quote carries its numerator and
    denominator beside it."""
    lots = [r for r in rs if (r["lot_index"] or 0) >= 1]
    readable = [r for r in lots if r["how_voted"] in VOTE_ENUM]
    voted = [r for r in readable if r["shares_voted"] is None or r["shares_voted"] > 0]
    for_lots = sum(1 for r in voted if r["how_voted"] == "FOR")
    return {
        "n_records": len(rs),
        "n_lots": len(lots),
        "n_proposals": len({r["proposal_no"] for r in rs}),
        "n_voted": len(voted),
        "zero_share_lots": sum(1 for r in readable if r["shares_voted"] == 0),
        "for_lots": for_lots,
        "for_pct": pct(for_lots, len(voted)),
        "thin": len(voted) < thin_n,
    }


def crosstab(rs):
    """vote x recommendation counts over lots with both normalised. Keys "VOTE/REC"."""
    out = {}
    for r in rs:
        if r["how_voted"] in VOTE_ENUM and r["mgmt_rec"] in REC_ENUM:
            k = f"{r['how_voted']}/{r['mgmt_rec']}"
            out[k] = out.get(k, 0) + 1
    return out


def mgmt_rec_semantics(rows, thin_n):
    """The computed check behind "no headline rests on managementRecommendation", threshold-free
    (round two, R5, three readers): a board recommends once per item, so a filing in which the
    lots of ONE proposal carry DIFFERENT recommendation values is not publishing a board's view.
    Published: the count of such proposals, one example a reader can open, the vote x
    recommendation crosstab on shareholder and on management lots (the Vanguard filing is an
    exact mirror on shareholder lots: AGAINST/FOR 819, FOR/AGAINST 408, ABSTAIN/AGAINST 206),
    and the agreement rate as evidence, not as the test. Verdict: not-board-view when the
    mixed-proposal count reaches thin_n; insufficient when fewer than thin_n lots carry a
    recommendation at all; board-view otherwise. Gated by G8: headline_allowed only on board-view."""
    lots = [r for r in rows if (r["lot_index"] or 0) >= 1]
    with_any_rec = [r for r in lots if r["mgmt_rec"] in VOTE_ENUM]
    by_prop = {}
    for r in with_any_rec:
        by_prop.setdefault(r["proposal_no"], set()).add(r["mgmt_rec"])
    mixed = sorted(pn for pn, vals in by_prop.items() if len(vals) > 1)
    example = None
    if mixed:
        # The example with the most lots, so the contradiction is visible in one place.
        best = max(mixed, key=lambda pn: sum(1 for r in lots if r["proposal_no"] == pn))
        ex_rows = [r for r in lots if r["proposal_no"] == best]
        example = {
            "proposal_no": best,
            "issuer_name": ex_rows[0]["issuer_name"],
            "meeting_date": ex_rows[0]["meeting_date"],
            "vote_description": ex_rows[0]["vote_description"],
            "category_slug": slugify(bucket(ex_rows[0]["category_type"])),
            "lots": len(ex_rows),
            "recommendations": sorted({r["mgmt_rec"] for r in ex_rows if r["mgmt_rec"]}),
        }
    sh = [r for r in lots if source_bucket(r["vote_source"]) == "SECURITY HOLDER"]
    with_rec = [r for r in sh if r["how_voted"] in VOTE_ENUM and r["mgmt_rec"] in VOTE_ENUM]
    agree = sum(1 for r in with_rec if r["how_voted"] == r["mgmt_rec"])
    if len(with_any_rec) < thin_n:
        verdict = "insufficient"
    elif len(mixed) >= thin_n:
        verdict = "not-board-view"
    else:
        verdict = "board-view"
    return {
        "field": "managementRecommendation",
        "test": "a board recommends once per item; proposals whose lots carry more than one "
                "recommendation value are counted, and the count must stay below thin_n",
        "lots_with_recommendation": len(with_any_rec),
        "proposals_with_recommendation": len(by_prop),
        "proposals_with_mixed_recommendation": len(mixed),
        "example_mixed_proposal": example,
        "crosstab_shareholder_lots": crosstab(sh),
        "crosstab_management_lots": crosstab(
            [r for r in lots if source_bucket(r["vote_source"]) == "ISSUER"]),
        "shareholder_lots": len(sh),
        "shareholder_lots_with_recommendation": len(with_rec),
        "agreeing": agree,
        "agreement": f"{agree}/{len(with_rec)}",
        "agreement_pct": pct(agree, len(with_rec)),
        "verdict": verdict,
        "headline_allowed": verdict == "board-view",
    }


def main():
    log("EqualShares export_site - data/rollcall.db -> site/data JSON artifacts")
    thin_n = load_config()
    log(f"thin_n = {thin_n} (CONFIG, pipeline/sources.py)")
    if not DB_PATH.exists():
        die(f"database not found: {DB_PATH} - run the ingest + extract first")

    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row

    filings = con.execute(
        "SELECT * FROM filings ORDER BY (filed_at IS NULL), filed_at DESC, accession DESC"
    ).fetchall()
    if not filings:
        die("filings table is empty - nothing to export")
    filing = filings[0]
    if len(filings) > 1:
        log(f"note: {len(filings)} filings in DB; exporting the most recent: {filing['accession']}")
    acc = filing["accession"]

    filer = con.execute(
        "SELECT cik, name FROM filers WHERE cik = ?", (filing["cik"],)
    ).fetchone()
    if filer is None:
        die(f"filings.cik {filing['cik']!r} has no filers row - referential integrity broken")

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
            f"no vote_records for {acc} - refusing to export an empty site "
            "(failure is not emptiness; run extract.py, and if it found zero records "
            "that is trap 6.8, not a quiet filer)"
        )
    if len(run_ids) > 1:
        die(
            f"vote_records for {acc} carry {len(run_ids)} distinct engine_run_ids "
            f"{run_ids} - mixed provenance; re-run extract.py before exporting"
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
               mgmt_rec, mgmt_rec_raw, vote_source, vote_series, categories_all,
               proposal_no, lot_index, lots_in_proposal, source_url
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
        if r["how_voted"] is not None and r["how_voted"] not in VOTE_ENUM:
            die(f"vote_records seq {r['seq']}: how_voted={r['how_voted']!r} is outside "
                f"{VOTE_ENUM} - extractor contract broken; fix extract.py, do not export")
        if r["mgmt_rec"] is not None and r["mgmt_rec"] not in REC_ENUM:
            die(f"vote_records seq {r['seq']}: mgmt_rec={r['mgmt_rec']!r} is outside "
                f"{REC_ENUM} - extractor contract broken; fix extract.py, do not export")
        if r["proposal_no"] is None or r["lot_index"] is None or r["lots_in_proposal"] is None:
            die(f"vote_records seq {r['seq']}: proposal grouping is NULL - the store predates "
                "proposal grouping; re-run extract.py before exporting")
        su = r["source_url"]
        if not isinstance(su, str) or su.strip() == "":
            die(f"vote_records seq {r['seq']}: empty source_url - receipts are mandatory")
    series_ids = sorted({r["vote_series"] for r in rows if r["vote_series"]})
    if len(series_ids) != 1:
        die(f"filing {acc} carries {len(series_ids)} distinct voteSeries values {series_ids}; "
            "the page says 'one fund' and will not say it over a filing that is not")

    # -- bucket into categories ------------------------------------------------
    by_cat = {}
    for r in rows:
        by_cat.setdefault(bucket(r["category_type"]), []).append(r)

    # Round two, R2: 198 proposals have lots in more than one category, so a category list
    # shows "2 of 3" without "1 of 3". Each record publishes the OTHER categories its sibling
    # lots fall in, and each category counts the proposals it shares.
    cats_of_proposal = {}
    for r in rows:
        cats_of_proposal.setdefault(r["proposal_no"], set()).add(bucket(r["category_type"]))

    slug_owner = {}
    categories = []
    for name, rs in by_cat.items():
        slug = slugify(name)
        if not slug:
            die(f"category {name!r} slugifies to an empty string - cannot publish it")
        if slug in slug_owner and slug_owner[slug] != name:
            die(f"slug collision: {slug_owner[slug]!r} and {name!r} both slugify to {slug!r}")
        slug_owner[slug] = name

        n = len(rs)
        votes = {k: 0 for k in VOTE_ENUM}
        shares_sum = 0.0
        any_shares = False
        for r in rs:
            hv = r["how_voted"]
            if hv in votes:
                votes[hv] += 1
            sv = r["shares_voted"]
            if sv is not None:
                shares_sum += sv
                any_shares = True
        # Tri-valued honesty: 'unparseable' (raw kept, normalisation failed) and 'absent in
        # source' (no how-voted at all) are DIFFERENT states. enum + UNPARSEABLE + ABSENT == n.
        votes["UNPARSEABLE"] = sum(
            1 for r in rs if r["how_voted_raw"] is not None and r["how_voted"] is None)
        votes["ABSENT"] = sum(1 for r in rs if r["how_voted_raw"] is None)

        by_source = {}
        for key in SOURCE_KEYS:
            by_source[key] = source_cell([r for r in rs if source_bucket(r["vote_source"]) == key],
                                         thin_n)
        for key in ("OTHER", "ABSENT"):
            sub = [r for r in rs if source_bucket(r["vote_source"]) == key]
            if sub:
                by_source[key] = source_cell(sub, thin_n)

        props_here = {r["proposal_no"] for r in rs}
        categories.append(
            {
                "category": name,
                "slug": slug,
                "n": n,
                "n_lots": sum(1 for r in rs if (r["lot_index"] or 0) >= 1),
                "n_proposals": len(props_here),
                "n_proposals_shared": sum(1 for pn in props_here if len(cats_of_proposal[pn]) > 1),
                "n_zero_share_lots": sum(1 for r in rs if (r["lot_index"] or 0) >= 1
                                         and r["shares_voted"] == 0),
                "votes": votes,
                "shares_voted_total": round(shares_sum, 4) if any_shares else None,
                "by_source": by_source,
            }
        )
    categories.sort(key=lambda c: (-c["n"], c["category"]))

    totals = {
        "records": len(rows),
        "lots": sum(1 for r in rows if (r["lot_index"] or 0) >= 1),
        "zero_lot_rows": sum(1 for r in rows if (r["lot_index"] or 0) == 0),
        "proposals": len({r["proposal_no"] for r in rows}),
        "proposals_in_multiple_categories": sum(
            1 for pn, cs in cats_of_proposal.items() if len(cs) > 1),
        "issuers": len({r["cusip"] for r in rows if r["cusip"]}),
        "issuer_name_spellings": len({r["issuer_name"] for r in rows if r["issuer_name"]}),
        "categories": len(categories),
        "unparseable_how_voted": sum(
            1 for r in rows if r["how_voted_raw"] is not None and r["how_voted"] is None
        ),
        "absent_how_voted": sum(1 for r in rows if r["how_voted_raw"] is None),
        "zero_share_lots": sum(
            1 for r in rows if (r["lot_index"] or 0) >= 1 and r["shares_voted"] == 0),
        # Records the filer tagged with MORE than one category. Each is grouped under its FIRST
        # category only (no double counting; sum(n)==records stays exact).
        "multi_category_records": sum(
            1 for r in rows if (r["categories_all"] or "").find("|") != -1
        ),
    }
    if sum(c["n"] for c in categories) != totals["records"]:
        die("internal invariant broken: sum(category n) != totals.records")
    if totals["lots"] + totals["zero_lot_rows"] != totals["records"]:
        die("internal invariant broken: lots + zero-lot rows != records")

    try:
        filing_obj = {
            k: filing[k]
            for k in (
                "accession", "form", "filed_at", "period_of_report", "series_name",
                "vote_doc_view_url", "vote_doc_name", "vote_doc_type", "vote_doc_url",
                "index_url", "raw_sha256", "raw_bytes", "fetched_at",
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
    filing_obj["series_id"] = series_ids[0]

    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "filer": {"cik": filer["cik"], "name": filer["name"]},
        "filing": filing_obj,
        "engine_run": engine_obj,
        "totals": totals,
        "thin_n": thin_n,
        # The typed constants that shape the page, published so the "computed" claim can name
        # its exceptions (round two, R6). One remains.
        "config": {"thin_n": thin_n},
        "mgmt_rec_semantics": mgmt_rec_semantics(rows, thin_n),
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
    sem = meta["mgmt_rec_semantics"]
    log(
        f"wrote site/data/meta.json  ({b} bytes; records={totals['records']}, "
        f"lots={totals['lots']}, proposals={totals['proposals']}, "
        f"categories={totals['categories']}, unparseable_how_voted={totals['unparseable_how_voted']}; "
        f"mgmt_rec_semantics mixed={sem['proposals_with_mixed_recommendation']} "
        f"agreement={sem['agreement']} -> {sem['verdict']})"
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
                    "proposal_no": r["proposal_no"],
                    "lot_index": r["lot_index"],
                    "lots_in_proposal": r["lots_in_proposal"],
                    "other_categories": sorted(
                        cats_of_proposal[r["proposal_no"]] - {c["category"]}),
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
