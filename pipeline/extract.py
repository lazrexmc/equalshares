"""SEPARATE extraction pass - network-free by construction (no urllib import).

Reads filings rows + raw XML files, parses namespace-agnostically (match on
localname, strip namespace), emits one vote_records row per voteRecord child
(a VOTE LOT; parent proposal fields carried; a block with zero lots emits one
row with the how-voted fields absent-in-source), groups rows into PROPOSALS
across blocks (proposal_no / lot_index / lots_in_proposal), tri-valued normalization
(extracted / absent-in-source raw NULL / unparseable raw kept + normalized
NULL - never invent, never blank a raw), UPSERTs on (accession, seq), and
stamps every row with engine_run_id provenance.

PROVENANCE (extractor-provenance module):
  code_fingerprint = sha256 over the concatenated bytes of
                     extract.py + edgar_npx.py + store.py (that order)
  config_hash      = sha256 of canonical JSON (sorted keys) of CONFIG
                     (sources.config_hash(); EXTRACT_CONFIG_PERTURB=1 is the
                     G6 test seam)
  engine_run_id    = sha256(code_fingerprint + "|" + config_hash)[:16]
  git_commit       = trace only - NEVER part of the id (an unrelated commit
                     must NOT change engine_run_id; that is the negative test)

STRUCTURE ASSERT: if the expected localnames are absent, or the parse yields
zero records, print a structure report and exit non-zero. A FUND VOTING REPORT
that parses to ZERO records is an ERROR, never success - that is trap 6.8's
empty-result-that-looks-legitimate, and this pass refuses to emit guessed rows.

Usage:
  python pipeline/extract.py
  python pipeline/extract.py --db data/rollcall.db
"""

import sys

# First thing: Windows consoles default to cp1252 and issuer names are not ASCII.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import argparse
import hashlib
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

_PIPELINE_DIR = Path(__file__).resolve().parent
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

import sources
import store

REPO_ROOT = _PIPELINE_DIR.parent

# The files whose bytes define extraction behaviour, in contract order.
# sources.py's CONFIG is covered separately by config_hash.
# export_site.py computes every PUBLISHED number from these rows, so it is
# part of the behaviour the fingerprint must cover (review finding 2026-08-28:
# published behaviour could change without the fingerprint changing).
FINGERPRINT_FILES = ["extract.py", "edgar_npx.py", "store.py", "export_site.py"]

# If any of these localnames is entirely absent from a parsed vote document,
# the structure has deviated from what this extractor understands - fail
# loudly with a report rather than emit guessed rows.
EXPECTED_LOCALNAMES = ("proxyTable", "issuerName", "voteRecord", "howVoted")

MEETING_DATE_RE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- provenance

def compute_code_fingerprint():
    h = hashlib.sha256()
    for name in FINGERPRINT_FILES:
        # Line-ending normalization: core.autocrlf can hand a fresh Windows
        # clone CRLF bytes for the identical commit, which would mint a
        # different engine_run_id for byte-identical logic (review finding
        # 2026-08-28). The fingerprint hashes the LOGIC, so normalize.
        h.update((_PIPELINE_DIR / name).read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()


def git_commit_or_empty():
    """Trace metadata only - '' on any failure, and NEVER part of the
    engine_run_id (extractor-provenance trap 6.2)."""
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT),
                           capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------- XML helpers

def localname(tag):
    """Namespace-agnostic tag name: '{ns}issuerName' -> 'issuerName'."""
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) and "}" in tag else tag


def text_or_none(elem):
    """Element text, stripped; an empty or whitespace-only element reads as
    absent-in-source (raw NULL)."""
    t = (elem.text or "").strip()
    return t if t else None


def direct_child_text(elem, name):
    """First DIRECT child with this localname. Direct-only matters:
    sharesVoted exists at both the proposal level and inside voteRecord, and a
    descendant search would blur the two."""
    for child in elem:
        if localname(child.tag) == name:
            return text_or_none(child)
    return None


def first_descendant_text(elem, name):
    """First descendant with this localname, document order (used for
    categoryType, which nests under voteCategories/voteCategory)."""
    for d in elem.iter():
        if localname(d.tag) == name:
            return text_or_none(d)
    return None


# ---------------------------------------------------------------- normalization

def normalize_vote(raw):
    """Tri-valued: (None, None) = absent-in-source; (raw, enum) = extracted;
    (raw, None) = unparseable, raw kept. The enum is exactly
    {FOR, AGAINST, ABSTAIN, WITHHOLD}, case-insensitive exact match after
    strip - the known-dirty numeric '1.0'/'2.0'/'3.0' say-on-pay frequency
    values normalize to NULL with the raw preserved."""
    if raw is None:
        return None, None
    return raw, sources.CONFIG["vote_normalization"].get(raw.strip().upper())


def normalize_rec(raw):
    """managementRecommendation: the vote enum plus the values CONFIG lists as
    extra (NONE = the filer said there was no recommendation). NONE is an
    EXTRACTED value, not absent-in-source - cold-read round one (2026-08-29)
    found ten of them silently excluded from a published count because they
    normalised to NULL. Tri-valued as normalize_vote."""
    if raw is None:
        return None, None
    key = raw.strip().upper()
    enum = sources.CONFIG["vote_normalization"].get(key)
    if enum is None:
        enum = sources.CONFIG["mgmt_rec_extra_values"].get(key)
    return raw, enum


def assign_proposals(rows):
    """Group a filing's rows into proposals ACROSS <proxyTable> blocks.

    Verified 2026-08-29 on the Vanguard filing: 21,474 blocks, 29,890 lots,
    10,523 distinct proposals; one proposal spans 1-5 blocks and a block holds
    1-10 lots (Medtronic's auditor ratification: seven lots in three blocks).
    A reader asking "how did this fund vote on X" needs the lots of X together.

    proposal_no      1-based, first-appearance order in the document
    lot_index        1-based across the proposal's lots in document order;
                     0 for the single row a zero-lot block emits
    lots_in_proposal count of lot rows (lot_index >= 1) in the proposal
    Mutates rows in place; deterministic, so seq-keyed UPSERTs stay corrective.
    """
    # Cold-read round two (2026-08-30): the filing spells one company two ways
    # ("The Walt Disney Company" / "THE WALT DISNEY COMPANY"; the 0-share block
    # carries the upper-case one), and a key on the name as filed gave one
    # ballot item two proposal numbers. Normalise case, whitespace and trailing
    # punctuation on the text fields (Medtronic's auditor item was filed three
    # ways: ending ";", "." and nothing); the stored values stay verbatim.
    # THE ONE KEY: every published proposal count derives from the proposal_no
    # this function assigns, so the counts and the rule cannot diverge.
    def norm(v):
        if v is None:
            return None
        return " ".join(str(v).split()).upper().rstrip(".;:, ")

    def key(r):
        return (norm(r["issuer_name"]), r["cusip"], r["meeting_date"],
                norm(r["vote_description"]), norm(r["vote_source"]))

    key_of = {}
    counts = {}
    for r in rows:
        k = key(r)
        if k not in key_of:
            key_of[k] = len(key_of) + 1
            counts[k] = 0
        r["proposal_no"] = key_of[k]
        if r["how_voted_raw"] is None and r["mgmt_rec_raw"] is None and r.get("_zero_lot"):
            r["lot_index"] = 0
        else:
            counts[k] += 1
            r["lot_index"] = counts[k]
    for r in rows:
        r["lots_in_proposal"] = counts[key(r)]
        r.pop("_zero_lot", None)
    return len(key_of)


def to_float(raw, stats, key):
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        stats[key] += 1
        return None


def normalize_meeting_date(raw):
    """MM/DD/YYYY (the N-PX wire format) -> YYYY-MM-DD so that TEXT ordering is
    chronological (export orders category records by meeting_date). Anything
    that is not exactly MM/DD/YYYY is stored verbatim - never invented, never
    blanked."""
    if raw is None:
        return None
    m = MEETING_DATE_RE.match(raw)
    if m:
        return f"{m.group(3)}-{m.group(1)}-{m.group(2)}"
    return raw


# ---------------------------------------------------------------- parsing

def parse_filing(raw_path, stats, series_id=None):
    """One raw vote-document XML file -> (rows, localname histogram).

    iterparse keeps memory bounded (the verified target holds 21,474 records in
    ~18MB of XML). Rows carry every vote_records field except accession, seq,
    source_url, engine_run_id, extracted_at - the caller stamps those.
    Row order is document order, which is what makes seq deterministic.
    """
    histogram = Counter()
    rows = []
    for _event, elem in ET.iterparse(str(raw_path), events=("end",)):
        ln = localname(elem.tag)
        histogram[ln] += 1
        if ln != "proxyTable":
            continue

        # Part 2: a multi-series filing (iShares Trust: 29 series, 180 MB) is
        # scoped to the pinned series at extraction; the raw file keeps every
        # series. A block with no voteSeries is kept only when no pin is set.
        if series_id is not None:
            vs = direct_child_text(elem, "voteSeries")
            if (vs or "").strip().upper() != series_id.strip().upper():
                stats["skipped_other_series"] += 1
                elem.clear()
                continue
        base = {
            "issuer_name": direct_child_text(elem, "issuerName"),
            "cusip": direct_child_text(elem, "cusip"),
            "isin": direct_child_text(elem, "isin"),
            "meeting_date": normalize_meeting_date(
                direct_child_text(elem, "meetingDate")),
            # ALL categoryType values, document order. category_type (the
            # grouping key) stays the FIRST; categories_all preserves the rest -
            # verified live: records exist carrying two categories (e.g. a
            # shareholder climate proposal filed under both ENVIRONMENT OR
            # CLIMATE and OTHER SOCIAL ISSUES). '|'-joined, shown as a footnote
            # count on the page rather than double-counted in the rollup.
            "category_type": first_descendant_text(elem, "categoryType"),
            "categories_all": "|".join(
                t for t in (text_or_none(d) for d in elem.iter()
                            if localname(d.tag) == "categoryType")
                if t is not None) or None,
            # ISSUER vs SECURITY HOLDER - who proposed it. Stored verbatim.
            # The page splits "% FOR" by it; it is the only honest axis for
            # that, because managementRecommendation is a per-lot field that
            # tracks the lot in the filing we have (cold-read round one).
            "vote_source": direct_child_text(elem, "voteSource"),
            "vote_description": direct_child_text(elem, "voteDescription"),
            "shares_on_loan": to_float(
                direct_child_text(elem, "sharesOnLoan"), stats,
                "unparseable_shares"),
            "vote_series": direct_child_text(elem, "voteSeries"),
        }
        prop_shares = to_float(
            direct_child_text(elem, "sharesVoted"), stats, "unparseable_shares")

        vote_records = [d for d in elem.iter()
                        if localname(d.tag) == "voteRecord"]
        if not vote_records:
            # Zero voteRecord children -> one row, how-voted fields absent
            # (raw NULL) - absent-in-source, not unparseable.
            rows.append({**base, "shares_voted": prop_shares,
                         "how_voted_raw": None, "how_voted": None,
                         "mgmt_rec_raw": None, "mgmt_rec": None,
                         "_zero_lot": True})
        else:
            # Split votes: one row per voteRecord child, parent proposal
            # fields carried. A voteRecord-level sharesVoted (present on split
            # votes) is that row's own number; otherwise the proposal-level
            # figure is carried.
            for vr in vote_records:
                hv_raw, hv = normalize_vote(direct_child_text(vr, "howVoted"))
                mr_raw, mr = normalize_rec(
                    direct_child_text(vr, "managementRecommendation"))
                if hv_raw is not None and hv is None:
                    stats["unparseable_how_voted"] += 1
                vr_shares_raw = direct_child_text(vr, "sharesVoted")
                if vr_shares_raw is not None:
                    shares = to_float(vr_shares_raw, stats, "unparseable_shares")
                else:
                    shares = prop_shares
                rows.append({**base, "shares_voted": shares,
                             "how_voted_raw": hv_raw, "how_voted": hv,
                             "mgmt_rec_raw": mr_raw, "mgmt_rec": mr})
        stats["parsed_records"] += 1
        elem.clear()
    return rows, histogram


def print_structure_report(accession, raw_path, histogram, missing):
    """The loud failure the contract demands: never guessed rows, never a
    quiet zero."""
    print("", flush=True)
    print("=" * 70, flush=True)
    print(f"STRUCTURE REPORT - {accession}", flush=True)
    print(f"raw file: {raw_path}", flush=True)
    print("The parse did not match the expected N-PX vote-document structure.",
          flush=True)
    print("A FUND VOTING REPORT that parses to zero records is an ERROR, not",
          flush=True)
    print("an empty result (ingestion-pipeline trap 6.8): the document that",
          flush=True)
    print("was stored may not be the document that carries the votes, or the",
          flush=True)
    print("schema has changed. No guessed rows were emitted.", flush=True)
    print(f"expected localnames absent: "
          f"{missing if missing else '(none - zero records despite matches)'}",
          flush=True)
    print(f"distinct localnames seen: {len(histogram)}", flush=True)
    print("localname histogram (top 50 by count):", flush=True)
    for name, n in histogram.most_common(50):
        print(f"  {n:>8}  {name}", flush=True)
    print("=" * 70, flush=True)


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(
        description="EqualShares N-PX extraction: raw XML -> vote_records "
                    "(network-free; re-runnable over history)")
    ap.add_argument("--db", default=str(REPO_ROOT / "data" / "rollcall.db"),
                    help="sqlite database path (default: data/rollcall.db)")
    ap.add_argument("--print-fingerprint", action="store_true",
                    help="print the engine fingerprint (honouring "
                         "EXTRACT_CONFIG_PERTURB) and exit - no database access, "
                         "no writes. Gate G6's verification seam.")
    args = ap.parse_args()

    # The perturb env var is a TEST SEAM for --print-fingerprint only. A real,
    # writing extraction under it would mint a phantom engine and re-tag the
    # whole table (review finding 2026-08-28) - refuse loudly instead.
    if (not args.print_fingerprint
            and os.environ.get("EXTRACT_CONFIG_PERTURB") == "1"):
        log("ERROR: EXTRACT_CONFIG_PERTURB is set. That seam exists for "
            "--print-fingerprint (gate G6) only; refusing to run a writing "
            "extraction under a perturbed fingerprint. Unset it and re-run.")
        sys.exit(1)

    if args.print_fingerprint:
        code_fp = compute_code_fingerprint()
        cfg_hash = sources.config_hash()
        engine_run_id = hashlib.sha256(
            f"{code_fp}|{cfg_hash}".encode("utf-8")).hexdigest()[:16]
        print(f"engine_run_id={engine_run_id}")
        print(f"code_fingerprint={code_fp}")
        print(f"config_hash={cfg_hash}")
        return

    log(f"extract starting (db={args.db})")
    conn = store.connect(args.db)
    store.init_schema(conn)

    filings = store.list_filings(conn)
    if not filings:
        log("ERROR: zero filings in the store - run pipeline/run_ingest.py first")
        sys.exit(1)

    code_fp = compute_code_fingerprint()
    cfg_hash = sources.config_hash()
    engine_run_id = hashlib.sha256(
        f"{code_fp}|{cfg_hash}".encode("utf-8")).hexdigest()[:16]
    engine_version = f"0.1+{engine_run_id[:8]}"
    git_commit = git_commit_or_empty()
    store.ensure_engine_run(conn, engine_run_id, engine_version, code_fp,
                            cfg_hash, utcnow(), git_commit)
    # Trace-only backfill: fill an empty git_commit recorded before the code
    # was committed. Never part of the id (trap 6.2).
    store.update_engine_run_commit(conn, engine_run_id, git_commit)
    conn.commit()
    log(f"engine_run_id={engine_run_id} engine_version={engine_version}")
    log(f"  code_fingerprint={code_fp}")
    log(f"  config_hash={cfg_hash}")
    log(f"  git_commit={git_commit or '(none)'} (trace only - never part of the id)")

    grand = Counter()
    grand_categories = Counter()
    # Per-filing failures are collected and reported at the end (exit 1), so
    # one damaged filing cannot deadlock extraction of every OTHER filing
    # (review finding 2026-08-28). Each failure is still loud, and the run
    # still fails - it just fails after doing all the work it could.
    filing_failures = []
    for filing in filings:
        accession = filing["accession"]

        if not filing["index_url"]:
            log(f"ERROR: {accession}: filings.index_url is empty - every vote "
                f"record must carry the reader-facing receipt verbatim; "
                f"re-run run_ingest.py")
            filing_failures.append((accession, "empty index_url"))
            continue

        raw_path = Path(filing["raw_path"])
        if not raw_path.is_absolute():
            raw_path = REPO_ROOT / raw_path
        log(f"filing {accession}: parsing {raw_path}")
        if not raw_path.exists():
            log(f"ERROR: raw file missing: {raw_path} - re-run run_ingest.py")
            filing_failures.append((accession, "raw file missing"))
            continue

        digest = hashlib.sha256(raw_path.read_bytes()).hexdigest()
        if digest != filing["raw_sha256"]:
            log(f"ERROR: raw file sha256 mismatch for {accession}")
            log(f"  stored   {filing['raw_sha256']}")
            log(f"  computed {digest}")
            log("  the raw store is immutable; a mismatch means corruption or "
                "hand-editing - refusing to extract")
            filing_failures.append((accession, "raw sha256 mismatch"))
            continue

        stats = Counter()
        series_id = filing["series_id"] if "series_id" in filing.keys() else None
        if series_id:
            log(f"  scoped to series {series_id} ({filing['series_name'] or 'unnamed'})")
        try:
            rows, histogram = parse_filing(raw_path, stats, series_id)
        except ET.ParseError as e:
            log(f"ERROR: XML parse failure for {accession}: {e}")
            filing_failures.append((accession, f"XML parse failure: {e}"))
            continue

        missing = [n for n in EXPECTED_LOCALNAMES if histogram.get(n, 0) == 0]
        if not rows or missing:
            print_structure_report(accession, raw_path, histogram, missing)
            detail = ("zero records parsed" if not rows
                      else f"expected localnames absent: {', '.join(missing)}")
            log(f"ERROR: {accession}: structure assert failed ({detail})")
            filing_failures.append((accession, detail))
            continue

        n_proposals = assign_proposals(rows)
        now = utcnow()
        db_rows = []
        # seq = ordinal over emitted rows within the filing, in document
        # order - deterministic, which is what makes the UPSERT corrective.
        for seq, row in enumerate(rows, start=1):
            db_rows.append({**row,
                            "accession": accession,
                            "seq": seq,
                            # Dogfood finding 2: land the reader where the row
                            # can be FOUND - EDGAR's rendered vote table when
                            # it exists, else the filing index page. Both are
                            # EDGAR's own URLs stored verbatim at ingest.
                            "source_url": (filing["vote_doc_view_url"]
                                           or filing["index_url"]),
                            "engine_run_id": engine_run_id,
                            "extracted_at": now})

        store.upsert_vote_records(conn, db_rows)
        stale = store.delete_stale_vote_records(conn, accession, len(db_rows))
        conn.commit()
        if stale:
            log(f"  removed {stale} stale row(s) beyond seq {len(db_rows)} "
                f"(a previous parse emitted more rows)")

        cats = Counter(
            (r["category_type"] or "(no category)") for r in db_rows)
        log(f"  parsed blocks:  {stats['parsed_records']}"
            + (f" (skipped {stats['skipped_other_series']} blocks of other series)"
               if stats["skipped_other_series"] else ""))
        log(f"  emitted rows:   {len(db_rows)} "
            f"({sum(1 for r in db_rows if r['lot_index'] >= 1)} lots + "
            f"{sum(1 for r in db_rows if r['lot_index'] == 0)} zero-lot rows)")
        log(f"  proposals:      {n_proposals}")
        log(f"  unparseable how_voted: {stats['unparseable_how_voted']} "
            f"(raw kept, normalized NULL)")
        if stats["unparseable_shares"]:
            log(f"  unparseable share counts: {stats['unparseable_shares']} "
                f"(stored NULL)")
        log("  per-category tally:")
        for cat, n in cats.most_common():
            log(f"    {n:>7}  {cat}")

        grand["parsed_records"] += stats["parsed_records"]
        grand["unparseable_how_voted"] += stats["unparseable_how_voted"]
        grand["unparseable_shares"] += stats["unparseable_shares"]
        grand["emitted_rows"] += len(db_rows)
        grand_categories.update(cats)

    log("=" * 60)
    log(f"EXTRACT SUMMARY: {len(filings)} filing(s), "
        f"engine_run_id={engine_run_id}")
    if filing_failures:
        log("=" * 60)
        log(f"EXTRACT FAILURES: {len(filing_failures)} filing(s) could not be "
            f"extracted:")
        for acc, why in filing_failures:
            log(f"  {acc}: {why}")
        sys.exit(1)
    log(f"  parsed records: {grand['parsed_records']}")
    log(f"  emitted rows:   {grand['emitted_rows']}")
    log(f"  unparseable how_voted: {grand['unparseable_how_voted']}")
    if grand["unparseable_shares"]:
        log(f"  unparseable share counts: {grand['unparseable_shares']}")
    log("  per-category tally (all filings):")
    for cat, n in grand_categories.most_common():
        log(f"    {n:>7}  {cat}")
    conn.close()
    sys.exit(0)


if __name__ == "__main__":
    main()
