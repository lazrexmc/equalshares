"""Orchestrate FETCH ONLY - no parsing (extract.py is the separate, network-free
pass; that split is the point of the ingestion-pipeline module: re-parsing never
re-fetches 20MB).

Per source: its own try/except (a dead source is recorded, never a crash), 3
in-run retries with linear backoff, then skip.attempt_count += 1; at
max_skip_count the accession retires to terminal WITH a written reason. Raw
bytes land at data/raw/<accession>_<docname> with their sha256 in the filings
row.

EXIT CODES (a quiet day and an outage MUST be different codes - trap 6.1, the
most confirmed trap on this machine: a run where every source failed once
exited 0 and the cron stayed green while the feed dried up forever):
  0 = every source ok
  1 = partial (some failed, some ok)
  2 = EVERY source failed (outage)

Test seam for the outage gate: --base-url-data / --base-url-archives pointed at
an unreachable host must produce exit 2.

Usage:
  python pipeline/run_ingest.py
  python pipeline/run_ingest.py --db data/rollcall.db
  python pipeline/run_ingest.py --base-url-data http://127.0.0.1:9 --base-url-archives http://127.0.0.1:9
"""

import sys

# First thing: Windows consoles default to cp1252 and die on the first
# non-ASCII byte in an issuer name.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import argparse
import hashlib
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

_PIPELINE_DIR = Path(__file__).resolve().parent
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

import edgar_npx
import store
from sources import (CONFIG, DEFAULT_BASE_URL_ARCHIVES, DEFAULT_BASE_URL_DATA,
                     SOURCES)

REPO_ROOT = _PIPELINE_DIR.parent
RAW_DIR = REPO_ROOT / "data" / "raw"

# Adapters are per source TYPE, not per site. An unknown type is recorded as
# no-adapter in the run summary - never a crash (quarantine at the dispatcher).
ADAPTERS = {
    "edgar-npx": edgar_npx,
}


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def with_retries(desc, fn):
    """retry_attempts tries with linear backoff sleep(2 * attempt); re-raises
    the last error after the final attempt."""
    attempts = CONFIG["retry_attempts"]
    last = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as e:
            last = e
            log(f"  attempt {attempt}/{attempts} failed for {desc}: {e}")
            if attempt < attempts:
                backoff = 2 * attempt
                log(f"  backing off {backoff}s")
                time.sleep(backoff)
    raise last


def safe_filename(name):
    """Filesystem-safe basename for the raw file (the docname comes from a
    remote SGML header - never trust it as a path)."""
    return "".join(
        c if (c.isalnum() or c in "._-") else "_" for c in Path(name).name)


def already_ingested(conn, accession):
    """True when the filings row exists AND the raw file is on disk with a
    matching sha256. The raw store is immutable: never re-fetch to re-parse."""
    row = store.get_filing(conn, accession)
    if row is None:
        return False
    raw_path = Path(row["raw_path"])
    if not raw_path.is_absolute():
        raw_path = REPO_ROOT / raw_path
    if not raw_path.exists():
        log(f"  {accession}: filings row exists but raw file missing "
            f"({raw_path}) - refetching")
        return False
    digest = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    if digest != row["raw_sha256"]:
        log(f"  {accession}: raw file sha256 mismatch against filings row - refetching")
        return False
    return True


def process_source(conn, source, base_url_data, base_url_archives):
    """One source, wrapped by the caller in its own try/except.
    Returns (ok: bool, note: str)."""
    sid = source["id"]
    adapter = ADAPTERS.get(source["type"])
    if adapter is None:
        log(f"source {sid}: no-adapter for type '{source['type']}' - "
            f"quarantined, not a crash")
        return False, "no-adapter"

    try:
        listing = with_retries(
            f"{sid} submissions listing",
            lambda: adapter.list_filings(source, base_url_data))
    except Exception as e:
        log(f"source {sid}: FAILED to list filings: {e}")
        return False, f"listing failed: {e}"

    entity_name = listing["entity_name"] or source.get("name", "")
    if source.get("name") and entity_name and \
            source["name"].upper() != entity_name.upper():
        # Trap 6.6: confirm source identity against real output (r/CoMo was
        # Como, Italy). A CIK typo would surface right here.
        log(f"  WARNING: configured name '{source['name']}' != EDGAR entity "
            f"name '{entity_name}' - confirm source identity before trusting "
            f"this data")
    log(f"source {sid}: entity '{entity_name}', "
        f"{len(listing['filings'])} filing(s) selected")

    ingested = already = retired = failed = 0
    for filing in listing["filings"]:
        accession = filing["accession"]

        reason = store.get_terminal_reason(conn, accession)
        if reason:
            log(f"  {accession}: terminal (reason: {reason}) - skipping")
            retired += 1
            continue

        if already_ingested(conn, accession):
            log(f"  {accession}: already ingested, raw sha256 verified - "
                f"skipping fetch")
            already += 1
            continue

        try:
            result = with_retries(
                f"{sid} {accession}",
                lambda f=filing: adapter.fetch_filing(source, f, base_url_archives))
        except Exception as e:
            failed += 1
            attempts = store.record_skip(conn, accession, str(e)[:500], utcnow())
            log(f"  {accession}: FAILED after in-run retries "
                f"(skip attempt_count now {attempts}): {e}")
            if attempts >= CONFIG["max_skip_count"]:
                why = (f"retired after {attempts} failed ingest runs; "
                       f"last error: {str(e)[:300]}")
                store.retire_terminal(conn, accession, why, utcnow())
                log(f"  {accession}: RETIRED to terminal - {why}")
            conn.commit()
            continue

        raw = result.pop("raw")
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        doc_name = safe_filename(result["vote_doc_name"])
        raw_path = RAW_DIR / f"{accession}_{doc_name}"
        raw_path.write_bytes(raw)
        sha = hashlib.sha256(raw).hexdigest()
        rel_path = raw_path.relative_to(REPO_ROOT).as_posix()

        store.upsert_filer(conn, source["cik"], entity_name or source["name"],
                           source.get("registrant_type"), utcnow())
        store.upsert_filing(conn, {
            "accession": accession,
            "cik": source["cik"],
            "form": result["form"],
            "period_of_report": result["period_of_report"],
            "filed_at": result["filed_at"],
            "series_name": result["series_name"],
            "primary_doc": result["primary_doc"],
            "vote_doc_name": result["vote_doc_name"],
            "vote_doc_type": result["vote_doc_type"],
            "vote_doc_url": result["vote_doc_url"],
            "index_url": result["index_url"],
            "raw_path": rel_path,
            "raw_sha256": sha,
            "raw_bytes": len(raw),
            "fetched_at": utcnow(),
        })
        conn.commit()
        ingested += 1
        log(f"  {accession}: ingested {len(raw):,} bytes -> {rel_path} "
            f"(sha256 {sha[:16]}...)")
        if result["series_name"]:
            log(f"  {accession}: series '{result['series_name']}'")

    note = (f"ingested={ingested} already={already} retired={retired} "
            f"failed={failed}")
    return failed == 0, note


def main():
    ap = argparse.ArgumentParser(
        description="EqualShares N-PX ingest: fetch raw vote documents "
                    "(fetch only - extraction is a separate pass)")
    ap.add_argument("--base-url-data", default=DEFAULT_BASE_URL_DATA,
                    help="override data.sec.gov (test seam for the outage gate)")
    ap.add_argument("--base-url-archives", default=DEFAULT_BASE_URL_ARCHIVES,
                    help="override www.sec.gov (test seam for the outage gate)")
    ap.add_argument("--db", default=str(REPO_ROOT / "data" / "rollcall.db"),
                    help="sqlite database path (default: data/rollcall.db)")
    args = ap.parse_args()

    started = utcnow()
    log(f"run_ingest starting (db={args.db})")
    log(f"  base-url-data={args.base_url_data}  "
        f"base-url-archives={args.base_url_archives}")

    conn = store.connect(args.db)
    store.init_schema(conn)
    run_id = store.start_ingest_run(conn, started)

    enabled = [s for s in SOURCES if s.get("enabled")]
    outcomes = []
    for source in enabled:
        try:
            ok, note = process_source(
                conn, source, args.base_url_data, args.base_url_archives)
        except Exception as e:
            # Every source is wrapped: a dead source is recorded in the
            # summary and never kills the run.
            traceback.print_exc()
            ok, note = False, f"unhandled: {e}"
        outcomes.append((source["id"], ok, note))

    total = len(enabled)
    ok_n = sum(1 for _, ok, _ in outcomes if ok)
    failed_n = total - ok_n

    # A quiet day and an outage MUST be different exit codes (trap 6.1).
    if total == 0:
        exit_status = 2
        log("ERROR: zero enabled sources - nothing could possibly succeed. "
            "This is a configuration failure, not a quiet day.")
    elif failed_n == 0:
        exit_status = 0
    elif ok_n == 0:
        exit_status = 2
    else:
        exit_status = 1

    log("=" * 60)
    log(f"RUN SUMMARY: {total} source(s), {ok_n} ok, {failed_n} failed "
        f"-> exit {exit_status}")
    for sid, ok, note in outcomes:
        log(f"  {sid}: {'ok' if ok else 'FAILED'} ({note})")
    if exit_status == 2 and total > 0:
        log("  EVERY source failed - outage (exit 2), NOT a quiet day")

    notes = "; ".join(
        f"{sid}={'ok' if ok else 'failed'}({note})"
        for sid, ok, note in outcomes) or "no enabled sources"
    store.finish_ingest_run(conn, run_id, utcnow(), exit_status, total, ok_n,
                            failed_n, notes)
    conn.close()
    sys.exit(exit_status)


if __name__ == "__main__":
    main()
