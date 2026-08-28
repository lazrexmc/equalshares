"""SEPARATE extraction pass - network-free by construction (no urllib import).

Reads filings rows + raw XML files, parses namespace-agnostically (match on
localname, strip namespace), emits one vote_records row per voteRecord child
(split votes; parent proposal fields carried), tri-valued normalization
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
FINGERPRINT_FILES = ["extract.py", "edgar_npx.py", "store.py"]

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
        h.update((_PIPELINE_DIR / name).read_bytes())
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

def parse_filing(raw_path, stats):
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
            # ISSUER vs SECURITY HOLDER - who proposed it. Stored verbatim; the
            # concordance caveat on the page depends on it (the filing's own
            # managementRecommendation field reads inverted on shareholder
            # proposals relative to the board's actual stance).
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
                         "mgmt_rec_raw": None, "mgmt_rec": None})
        else:
            # Split votes: one row per voteRecord child, parent proposal
            # fields carried. A voteRecord-level sharesVoted (present on split
            # votes) is that row's own number; otherwise the proposal-level
            # figure is carried.
            for vr in vote_records:
                hv_raw, hv = normalize_vote(direct_child_text(vr, "howVoted"))
                mr_raw, mr = normalize_vote(
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
    conn.commit()
    log(f"engine_run_id={engine_run_id} engine_version={engine_version}")
    log(f"  code_fingerprint={code_fp}")
    log(f"  config_hash={cfg_hash}")
    log(f"  git_commit={git_commit or '(none)'} (trace only - never part of the id)")

    grand = Counter()
    grand_categories = Counter()
    for filing in filings:
        accession = filing["accession"]

        if not filing["index_url"]:
            log(f"ERROR: {accession}: filings.index_url is empty - every vote "
                f"record must carry the reader-facing receipt verbatim; "
                f"re-run run_ingest.py")
            sys.exit(1)

        raw_path = Path(filing["raw_path"])
        if not raw_path.is_absolute():
            raw_path = REPO_ROOT / raw_path
        log(f"filing {accession}: parsing {raw_path}")
        if not raw_path.exists():
            log(f"ERROR: raw file missing: {raw_path} - re-run run_ingest.py")
            sys.exit(1)

        digest = hashlib.sha256(raw_path.read_bytes()).hexdigest()
        if digest != filing["raw_sha256"]:
            log(f"ERROR: raw file sha256 mismatch for {accession}")
            log(f"  stored   {filing['raw_sha256']}")
            log(f"  computed {digest}")
            log("  the raw store is immutable; a mismatch means corruption or "
                "hand-editing - refusing to extract")
            sys.exit(1)

        stats = Counter()
        try:
            rows, histogram = parse_filing(raw_path, stats)
        except ET.ParseError as e:
            log(f"ERROR: XML parse failure for {accession}: {e}")
            sys.exit(1)

        missing = [n for n in EXPECTED_LOCALNAMES if histogram.get(n, 0) == 0]
        if not rows or missing:
            print_structure_report(accession, raw_path, histogram, missing)
            detail = ("zero records parsed" if not rows
                      else f"expected localnames absent: {', '.join(missing)}")
            log(f"ERROR: {accession}: structure assert failed ({detail})")
            sys.exit(1)

        now = utcnow()
        db_rows = []
        # seq = ordinal over emitted rows within the filing, in document
        # order - deterministic, which is what makes the UPSERT corrective.
        for seq, row in enumerate(rows, start=1):
            db_rows.append({**row,
                            "accession": accession,
                            "seq": seq,
                            "source_url": filing["index_url"],
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
        log(f"  parsed records: {stats['parsed_records']}")
        log(f"  emitted rows:   {len(db_rows)}")
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
