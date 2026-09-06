"""The ONLY module that touches sqlite (ingestion-pipeline module section 5).

Schema init (authoritative DDL from the contract), upserts for filers/filings,
vote_records UPSERT on (accession, seq), skip escalation + terminal retirement,
ingest_runs logging. WAL mode, busy_timeout.

RE-PARSE RULE: vote_records writes are INSERT ... ON CONFLICT(accession, seq)
DO UPDATE. Insert-ignore silently discards corrections and fails gate G5
(ingestion-pipeline trap 6.5 / extractor-provenance trap 6.8 - three sightings
on this machine; the entire point of re-parsing is that better output replaces
the old).

Commit discipline: callers own transaction boundaries and call conn.commit();
the two exceptions are start_ingest_run/finish_ingest_run, which commit
internally so a crashed run still leaves a visible started-but-never-finished
row.
"""

import sqlite3
from pathlib import Path

# Authoritative DDL (contract). CREATE TABLE IF NOT EXISTS so init is re-runnable.
SCHEMA = [
    """CREATE TABLE IF NOT EXISTS filers(
        cik TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        registrant_type TEXT,
        added_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS filings(
        accession TEXT PRIMARY KEY,
        cik TEXT NOT NULL REFERENCES filers(cik),
        form TEXT NOT NULL,
        period_of_report TEXT,
        filed_at TEXT,
        series_name TEXT,
        series_id TEXT,
        primary_doc TEXT,
        vote_doc_name TEXT,
        vote_doc_type TEXT,
        vote_doc_url TEXT,
        vote_doc_view_url TEXT,
        vote_doc_view_status TEXT,
        index_url TEXT,
        raw_path TEXT NOT NULL,
        raw_sha256 TEXT NOT NULL,
        raw_bytes INTEGER NOT NULL,
        fetched_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS vote_records(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        accession TEXT NOT NULL REFERENCES filings(accession),
        seq INTEGER NOT NULL,
        issuer_name TEXT,
        cusip TEXT,
        isin TEXT,
        meeting_date TEXT,
        category_type TEXT,
        vote_description TEXT,
        shares_voted REAL,
        shares_on_loan REAL,
        how_voted_raw TEXT,
        how_voted TEXT,
        mgmt_rec_raw TEXT,
        mgmt_rec TEXT,
        vote_series TEXT,
        vote_source TEXT,
        categories_all TEXT,
        proposal_no INTEGER,
        lot_index INTEGER,
        lots_in_proposal INTEGER,
        source_url TEXT NOT NULL,
        engine_run_id TEXT NOT NULL,
        extracted_at TEXT NOT NULL,
        UNIQUE(accession, seq))""",
    """CREATE TABLE IF NOT EXISTS engine_runs(
        engine_run_id TEXT PRIMARY KEY,
        engine_version TEXT NOT NULL,
        code_fingerprint TEXT NOT NULL,
        config_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        git_commit TEXT)""",
    """CREATE TABLE IF NOT EXISTS skip(
        accession TEXT PRIMARY KEY,
        attempt_count INTEGER NOT NULL,
        last_attempt TEXT,
        last_error TEXT)""",
    """CREATE TABLE IF NOT EXISTS terminal(
        accession TEXT PRIMARY KEY,
        reason TEXT NOT NULL,
        retired_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS ingest_runs(
        run_id INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at TEXT,
        finished_at TEXT,
        exit_status INTEGER,
        sources_total INTEGER,
        sources_ok INTEGER,
        sources_failed INTEGER,
        notes TEXT)""",
    """CREATE TABLE IF NOT EXISTS listings(
        run_id INTEGER NOT NULL,
        source_id TEXT NOT NULL,
        accession TEXT NOT NULL,
        form TEXT,
        period_of_report TEXT,
        filed_at TEXT,
        seen_at TEXT NOT NULL,
        PRIMARY KEY(run_id, accession))""",
]


def connect(db_path):
    """Open (creating parent dirs as needed) with WAL + busy_timeout + FKs on."""
    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_schema(conn):
    for stmt in SCHEMA:
        conn.execute(stmt)
    conn.commit()
    # Additive migration (2026-08-29, cold-read round one): a store created
    # before proposal grouping existed lacks these columns. ADD COLUMN is the
    # only ALTER SQLite needs here; values are filled by the next extract.
    have = {row[1] for row in conn.execute("PRAGMA table_info(vote_records)")}
    for col in ("proposal_no INTEGER", "lot_index INTEGER",
                "lots_in_proposal INTEGER"):
        if col.split()[0] not in have:
            conn.execute(f"ALTER TABLE vote_records ADD COLUMN {col}")
    # Part 2 (2026-08-30): the pinned series of a multi-series filing.
    have_f = {row[1] for row in conn.execute("PRAGMA table_info(filings)")}
    if "series_id" not in have_f:
        conn.execute("ALTER TABLE filings ADD COLUMN series_id TEXT")
    # 2026-09-06: whether EDGAR's viewer actually renders this filing. Half the receipts were
    # 404s inside a 200 because nothing recorded the difference.
    if "vote_doc_view_status" not in have_f:
        conn.execute("ALTER TABLE filings ADD COLUMN vote_doc_view_status TEXT")
    conn.commit()


# ---------------------------------------------------------------- filers/filings

def upsert_filer(conn, cik, name, registrant_type, added_at):
    """added_at records the FIRST appearance and is never overwritten."""
    conn.execute(
        """INSERT INTO filers(cik, name, registrant_type, added_at)
           VALUES(?, ?, ?, ?)
           ON CONFLICT(cik) DO UPDATE SET
             name = excluded.name,
             registrant_type = excluded.registrant_type""",
        (cik, name, registrant_type, added_at))


def upsert_filing(conn, f):
    """f is a dict carrying every filings column. A refetch overwrites the row
    (raw_path/raw_sha256/raw_bytes/fetched_at move with the new raw file)."""
    conn.execute(
        """INSERT INTO filings(accession, cik, form, period_of_report, filed_at,
             series_name, series_id, primary_doc, vote_doc_name, vote_doc_type, vote_doc_url,
             vote_doc_view_url, index_url, raw_path, raw_sha256, raw_bytes, fetched_at)
           VALUES(:accession, :cik, :form, :period_of_report, :filed_at,
             :series_name, :series_id, :primary_doc, :vote_doc_name, :vote_doc_type, :vote_doc_url,
             :vote_doc_view_url, :index_url, :raw_path, :raw_sha256, :raw_bytes, :fetched_at)
           ON CONFLICT(accession) DO UPDATE SET
             cik = excluded.cik,
             form = excluded.form,
             period_of_report = excluded.period_of_report,
             filed_at = excluded.filed_at,
             series_name = excluded.series_name,
             series_id = excluded.series_id,
             primary_doc = excluded.primary_doc,
             vote_doc_name = excluded.vote_doc_name,
             vote_doc_type = excluded.vote_doc_type,
             vote_doc_url = excluded.vote_doc_url,
             vote_doc_view_url = excluded.vote_doc_view_url,
             index_url = excluded.index_url,
             raw_path = excluded.raw_path,
             raw_sha256 = excluded.raw_sha256,
             raw_bytes = excluded.raw_bytes,
             fetched_at = excluded.fetched_at""",
        f)


def update_filing_series(conn, accession, series_id, series_name):
    """Part 2: record the pinned series on an already-ingested filing."""
    conn.execute(
        "UPDATE filings SET series_id = ?, series_name = COALESCE(?, series_name) "
        "WHERE accession = ?", (series_id, series_name, accession))


def update_filing_view_status(conn, accession, status):
    """Record what EDGAR's viewer actually returns for this filing (2026-09-06). Written on every
    link refresh, including when the answer is that it does not render."""
    conn.execute("UPDATE filings SET vote_doc_view_status = ? WHERE accession = ?",
                 (status, accession))


def update_filing_links(conn, accession, vote_doc_view_url, series_name):
    """Cheap link/series refresh for an already-ingested filing (no raw
    re-download). Only fills values that are present; never blanks a stored
    value with None (absent-in-source stays whatever was known)."""
    # The never-blank rule has one deliberate exception (2026-09-06): a viewer URL that no longer
    # renders must be cleared, or a broken receipt survives every refresh that finds it broken.
    conn.execute("UPDATE filings SET vote_doc_view_url = ? WHERE accession = ?",
                 (vote_doc_view_url, accession))
    if series_name:
        conn.execute(
            "UPDATE filings SET series_name = ? WHERE accession = ? "
            "AND (series_name IS NULL OR series_name = '')",
            (series_name, accession))


def get_filing(conn, accession):
    return conn.execute(
        "SELECT * FROM filings WHERE accession = ?", (accession,)).fetchone()


def list_filings(conn):
    return conn.execute(
        "SELECT * FROM filings ORDER BY filed_at DESC, accession").fetchall()


# ---------------------------------------------------------------- vote_records

def upsert_vote_records(conn, rows):
    """UPSERT on (accession, seq) - NEVER insert-ignore. A re-parse with a better
    extractor must overwrite what the old one wrote, or the re-parse is a no-op
    and gate G5 fails. rows is an iterable of dicts with exactly the columns
    below (the id autoincrement is untouched on conflict-update)."""
    conn.executemany(
        """INSERT INTO vote_records(accession, seq, issuer_name, cusip, isin,
             meeting_date, category_type, vote_description, shares_voted,
             shares_on_loan, how_voted_raw, how_voted, mgmt_rec_raw, mgmt_rec,
             vote_series, vote_source, categories_all, proposal_no, lot_index,
             lots_in_proposal, source_url, engine_run_id, extracted_at)
           VALUES(:accession, :seq, :issuer_name, :cusip, :isin,
             :meeting_date, :category_type, :vote_description, :shares_voted,
             :shares_on_loan, :how_voted_raw, :how_voted, :mgmt_rec_raw, :mgmt_rec,
             :vote_series, :vote_source, :categories_all, :proposal_no, :lot_index,
             :lots_in_proposal, :source_url, :engine_run_id, :extracted_at)
           ON CONFLICT(accession, seq) DO UPDATE SET
             issuer_name = excluded.issuer_name,
             cusip = excluded.cusip,
             isin = excluded.isin,
             meeting_date = excluded.meeting_date,
             category_type = excluded.category_type,
             vote_description = excluded.vote_description,
             shares_voted = excluded.shares_voted,
             shares_on_loan = excluded.shares_on_loan,
             how_voted_raw = excluded.how_voted_raw,
             how_voted = excluded.how_voted,
             mgmt_rec_raw = excluded.mgmt_rec_raw,
             mgmt_rec = excluded.mgmt_rec,
             vote_series = excluded.vote_series,
             vote_source = excluded.vote_source,
             categories_all = excluded.categories_all,
             proposal_no = excluded.proposal_no,
             lot_index = excluded.lot_index,
             lots_in_proposal = excluded.lots_in_proposal,
             source_url = excluded.source_url,
             engine_run_id = excluded.engine_run_id,
             extracted_at = excluded.extracted_at""",
        rows)


def delete_stale_vote_records(conn, accession, max_seq):
    """A corrected parser can emit FEWER rows than the previous run; rows beyond
    the new max seq are stale output of the old extractor and must not linger.
    seq is deterministic (document order), so this is safe. Returns rows deleted."""
    cur = conn.execute(
        "DELETE FROM vote_records WHERE accession = ? AND seq > ?",
        (accession, max_seq))
    return cur.rowcount


def count_vote_records(conn, accession):
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM vote_records WHERE accession = ?",
        (accession,)).fetchone()
    return row["n"]


# ---------------------------------------------------------------- provenance

def ensure_engine_run(conn, engine_run_id, engine_version, code_fingerprint,
                      config_hash, created_at, git_commit):
    """Inserted if absent. One row per unique behaviour fingerprint, not per
    invocation: an identical fingerprint means identical behaviour, so an
    existing row is left untouched and created_at records the FIRST appearance
    of this behaviour. (Insert-ignore is correct HERE and only here.)"""
    conn.execute(
        """INSERT OR IGNORE INTO engine_runs(engine_run_id, engine_version,
             code_fingerprint, config_hash, created_at, git_commit)
           VALUES(?, ?, ?, ?, ?, ?)""",
        (engine_run_id, engine_version, code_fingerprint, config_hash,
         created_at, git_commit))


def update_engine_run_commit(conn, engine_run_id, git_commit):
    """Trace-only backfill: an engine first fingerprinted BEFORE its code was
    committed carries git_commit='' forever under insert-ignore. Filling an
    empty trace with the now-known commit adds information and changes no
    behaviour - the commit is never part of the id (trap 6.2)."""
    if git_commit:
        conn.execute(
            """UPDATE engine_runs SET git_commit = ?
               WHERE engine_run_id = ? AND (git_commit IS NULL OR git_commit = '')""",
            (git_commit, engine_run_id))


# ---------------------------------------------------------------- skip/terminal

def get_skip_attempts(conn, accession):
    row = conn.execute(
        "SELECT attempt_count FROM skip WHERE accession = ?", (accession,)).fetchone()
    return row["attempt_count"] if row else 0


def record_skip(conn, accession, error, at):
    """One increment per failed RUN (in-run retries happen upstream).
    Returns the new attempt_count so the caller can decide on retirement."""
    conn.execute(
        """INSERT INTO skip(accession, attempt_count, last_attempt, last_error)
           VALUES(?, 1, ?, ?)
           ON CONFLICT(accession) DO UPDATE SET
             attempt_count = skip.attempt_count + 1,
             last_attempt = excluded.last_attempt,
             last_error = excluded.last_error""",
        (accession, at, error))
    return get_skip_attempts(conn, accession)


def clear_skip(conn, accession):
    """A successful ingest clears the skip ledger for that accession - review
    finding 2026-08-28: without this, stale counts from OLD transient failures
    accumulate, and one new failure can retire an accession that only ever
    failed transiently."""
    conn.execute("DELETE FROM skip WHERE accession = ?", (accession,))


def record_listing(conn, run_id, source_id, filings, seen_at):
    """Persist what the source LISTED this run - the expected set. This is the
    denominator the coverage gates need: without it, a filing that retires to
    terminal simply vanishes from every check (trap 6.1 re-entering through the
    terminal table - review finding 2026-08-28)."""
    conn.executemany(
        """INSERT OR REPLACE INTO listings(run_id, source_id, accession, form,
             period_of_report, filed_at, seen_at)
           VALUES(?, ?, ?, ?, ?, ?, ?)""",
        [(run_id, source_id, f["accession"], f.get("form"),
          f.get("period_of_report"), f.get("filed_at"), seen_at)
         for f in filings])


def get_terminal_reason(conn, accession):
    row = conn.execute(
        "SELECT reason FROM terminal WHERE accession = ?", (accession,)).fetchone()
    return row["reason"] if row else None


def retire_terminal(conn, accession, reason, retired_at):
    """A retirement without a written reason is a failure retired without being
    understood - the terminal-table audit (ingestion-pipeline gate 7.4) fails on
    it, so refuse it here at the only door."""
    if not (reason or "").strip():
        raise ValueError(
            "terminal retirement requires a non-empty written reason "
            "(ingestion-pipeline acceptance check 7.4)")
    conn.execute(
        """INSERT INTO terminal(accession, reason, retired_at)
           VALUES(?, ?, ?)
           ON CONFLICT(accession) DO UPDATE SET
             reason = excluded.reason,
             retired_at = excluded.retired_at""",
        (accession, reason.strip(), retired_at))


# ---------------------------------------------------------------- ingest_runs

def start_ingest_run(conn, started_at):
    """Insert-at-start / update-at-finish, so a crashed run leaves a visible
    row with finished_at NULL instead of vanishing."""
    cur = conn.execute(
        "INSERT INTO ingest_runs(started_at) VALUES(?)", (started_at,))
    conn.commit()
    return cur.lastrowid


def finish_ingest_run(conn, run_id, finished_at, exit_status, sources_total,
                      sources_ok, sources_failed, notes):
    conn.execute(
        """UPDATE ingest_runs SET
             finished_at = ?, exit_status = ?, sources_total = ?,
             sources_ok = ?, sources_failed = ?, notes = ?
           WHERE run_id = ?""",
        (finished_at, exit_status, sources_total, sources_ok, sources_failed,
         notes, run_id))
    conn.commit()
