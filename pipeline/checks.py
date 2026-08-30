#!/usr/bin/env python3
"""checks.py - THE GATES for EqualShares "The Roll Call".

Usage:  python pipeline/checks.py [--skip-outage]

Eight deterministic gates. Each prints PASS/FAIL with extracted evidence -
counts and values, never just a child's exit code:

  G1 raw-integrity          filings exist; every raw file exists; sha256 + size match
  G2 coverage               every filing has > 0 vote_records (ingestion trap 6.8)
  G3 outage-distinguishable run_ingest vs unreachable hosts MUST exit 2 (trap 6.1)
  G4 terminal-audit         every terminal row carries a non-empty written reason
  G5 reparse                extract twice: identical count, zero dupes; corrupt one
                            row, re-extract restores it (proves UPSERT, kills
                            insert-ignore - trap 6.5)
  G6 provenance             zero orphan engine_run_ids; manifest ids recompute from
                            sha256(code_fp|config_hash)[:16]; EXTRACT_CONFIG_PERTURB=1
                            changes the id, unperturbed re-run does not; git_commit
                            ignored by construction (provenance traps 6.1/6.2)
  G7 export-consistency     site/data artifacts agree with the DB, exactly
  G8 anti-blend             rollup.json has NO top-level blended number

Exit 0 only if every gate passed. --skip-outage marks G3 SKIP (not a pass -
run it at least once before calling the build done).

G3 uses a throwaway --db in a temp dir. G5 mutates the real DB by design and
restores via re-extract, with a manual SQL restore as a safety net on failure.
G6's --print-fingerprint subprocesses never write. Stdlib only (Python 3.14).
"""

import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import traceback
from collections import Counter
from datetime import datetime
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent
ROOT = PIPELINE_DIR.parent
DB_PATH = ROOT / "data" / "rollcall.db"
SITE_DATA = ROOT / "site" / "data"
CATEGORY_DIR = SITE_DATA / "category"
EXTRACT = PIPELINE_DIR / "extract.py"
RUN_INGEST = PIPELINE_DIR / "run_ingest.py"
PY = sys.executable

UNCATEGORIZED = "UNCATEGORIZED"
VOTE_ENUM = ("FOR", "AGAINST", "ABSTAIN", "WITHHOLD")
REC_ENUM = VOTE_ENUM + ("NONE",)
SOURCE_KEYS = ("ISSUER", "SECURITY HOLDER")
CELL_KEYS = {"n_records", "n_lots", "n_proposals", "n_voted", "zero_share_lots", "for_lots",
             "for_pct", "thin"}
CATEGORY_KEYS = {"category", "slug", "n", "n_lots", "n_proposals", "n_proposals_shared",
                 "n_zero_share_lots", "votes", "shares_voted_total", "by_source"}
VERDICTS = ("board-view", "not-board-view", "insufficient")
# Any key carrying one of these names anywhere in the export is a blended or
# recommendation-derived headline trying to come back (cold-read round one).
FORBIDDEN_KEY = re.compile(r"with_mgmt|concordance|comparable|blend", re.I)
G5_SENTINEL = "G5-CORRUPTION-SENTINEL-DO-NOT-SHIP"
UNREACHABLE = "http://127.0.0.1:9"


class GateError(Exception):
    """A gate failure with a written reason - a controlled FAIL, not a crash."""


def log(msg=""):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def dbcon():
    if not DB_PATH.exists():
        raise GateError(f"database not found: {DB_PATH} - run ingest + extract first")
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    return con


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_raw_path(raw_path):
    p = Path(raw_path)
    return p if p.is_absolute() else ROOT / p


def sub_run(cmd, timeout, extra_env=None):
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("EXTRACT_CONFIG_PERTURB", None)  # never inherit the perturb seam by accident
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [str(c) for c in cmd],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=timeout,
    )


def print_tail(proc, n=12):
    for label, stream in (("stdout", proc.stdout), ("stderr", proc.stderr)):
        lines = (stream or "").strip().splitlines()
        if not lines:
            continue
        log(f"  -- child {label} (last {min(n, len(lines))} of {len(lines)} lines) --")
        for line in lines[-n:]:
            log(f"  | {line}")


def parse_engine_run_id(text):
    """Find the 16-hex engine_run_id in --print-fingerprint output. Prefers a
    labelled value; falls back to any standalone 16-hex token (\\b keeps the
    64-hex code_fingerprint/config_hash from matching)."""
    m = re.search(r"engine_run_id\W{0,5}([0-9a-f]{16})\b", text)
    if m:
        return m.group(1)
    tokens = re.findall(r"\b[0-9a-f]{16}\b", text)
    return tokens[0] if tokens else None


def engine_run_id_formula(code_fingerprint, config_hash, git_commit=""):
    """The contract's id: sha256(code_fingerprint + "|" + config_hash)[:16].
    git_commit is accepted and deliberately unused - trace metadata never keys
    behaviour (extractor-provenance trap 6.2). G6 calls this with two different
    commits and requires equality."""
    _ = git_commit
    return hashlib.sha256(
        f"{code_fingerprint}|{config_hash}".encode("utf-8")
    ).hexdigest()[:16]


def bucket(category_type):
    """LOCKSTEP copy of export_site.bucket - change both or G7 fails (the point)."""
    if category_type is None or str(category_type).strip() == "":
        return UNCATEGORIZED
    return category_type


def slugify(category):
    """LOCKSTEP copy of export_site.slugify."""
    return re.sub(r"[^a-z0-9]+", "-", category.lower()).strip("-")


def source_bucket(vote_source):
    """LOCKSTEP copy of export_site.source_bucket."""
    if vote_source is None or str(vote_source).strip() == "":
        return "ABSENT"
    v = str(vote_source).strip().upper()
    return v if v in SOURCE_KEYS else "OTHER"


def record_sort_key(r):
    """LOCKSTEP copy of export_site.record_sort_key - reads the JSON back, so the
    grouping fields may be absent (then they sort first, which G7 flags anyway)."""
    return (
        r.get("meeting_date") is not None,
        r.get("meeting_date") or "",
        r.get("issuer_name") is not None,
        r.get("issuer_name") or "",
        r.get("proposal_no") if r.get("proposal_no") is not None else -1,
        r.get("lot_index") if r.get("lot_index") is not None else -1,
        r.get("seq"),
    )


def pct(num, den):
    return round(100 * num / den, 1) if den else None


def cell_from_rows(rs, thin_n):
    """LOCKSTEP copy of export_site.source_cell over DB rows: the denominator is lots with a
    readable vote AND shares above zero; zero-share lots are counted beside it."""
    lots = [r for r in rs if (r["lot_index"] or 0) >= 1]
    readable = [r for r in lots if r["how_voted"] in VOTE_ENUM]
    voted = [r for r in readable if r["shares_voted"] is None or r["shares_voted"] > 0]
    for_lots = sum(1 for r in voted if r["how_voted"] == "FOR")
    return {"n_records": len(rs), "n_lots": len(lots),
            "n_proposals": len({r["proposal_no"] for r in rs}),
            "n_voted": len(voted),
            "zero_share_lots": sum(1 for r in readable if r["shares_voted"] == 0),
            "for_lots": for_lots,
            "for_pct": pct(for_lots, len(voted)), "thin": len(voted) < thin_n}


def crosstab_rows(rs):
    """LOCKSTEP copy of export_site.crosstab over DB rows."""
    out = {}
    for r in rs:
        if r["how_voted"] in VOTE_ENUM and r["mgmt_rec"] in REC_ENUM:
            k = f"{r['how_voted']}/{r['mgmt_rec']}"
            out[k] = out.get(k, 0) + 1
    return out


def walk_keys(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            here = f"{path}.{k}" if path else k
            yield here
            yield from walk_keys(v, here)
    elif isinstance(obj, list):
        for n, v in enumerate(obj):
            yield from walk_keys(v, f"{path}[{n}]")


def load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise GateError(f"{path} is not valid JSON: {e}")


# ---------------------------------------------------------------- G1 --------
def g1_raw_integrity():
    con = dbcon()
    filings = con.execute(
        "SELECT accession, raw_path, raw_sha256, raw_bytes FROM filings ORDER BY accession"
    ).fetchall()
    con.close()
    if not filings:
        return False, "filings table is empty - nothing was ingested"
    log(f"  filings rows: {len(filings)}")
    ok = True
    for f in filings:
        p = resolve_raw_path(f["raw_path"])
        if not p.exists():
            log(f"  [FAIL] {f['accession']}: raw file missing at {p} (raw_path={f['raw_path']!r})")
            ok = False
            continue
        size = p.stat().st_size
        digest = sha256_file(p)
        good = (size == f["raw_bytes"]) and (digest == f["raw_sha256"])
        log(
            f"  [{'ok' if good else 'FAIL'}] {f['accession']}: {p.name}  "
            f"bytes stored={f['raw_bytes']} actual={size}  "
            f"sha256 stored={f['raw_sha256'][:12]}.. recomputed={digest[:12]}.."
        )
        if not good:
            ok = False
    return ok, (
        f"{len(filings)} filing(s); every raw file present with matching sha256 and size"
        if ok
        else "raw store integrity broken (see lines above)"
    )


# ---------------------------------------------------------------- G2 --------
def g2_coverage():
    con = dbcon()
    rows = con.execute(
        """
        SELECT f.accession, COUNT(v.id) AS n
          FROM filings f LEFT JOIN vote_records v ON v.accession = f.accession
         GROUP BY f.accession ORDER BY f.accession
        """
    ).fetchall()
    con.close()
    if not rows:
        return False, "filings table is empty"
    ok = True
    for r in rows:
        log(f"  [{'ok' if r['n'] > 0 else 'FAIL'}] {r['accession']}: {r['n']} vote_records")
        if r["n"] == 0:
            ok = False
    total = sum(r["n"] for r in rows)
    return ok, (
        f"every filing extracted (total {total} records)"
        if ok
        else "a filing with ZERO records - trap 6.8: the parsed document may not be the vote-bearing one"
    )


# ---------------------------------------------------------------- G3 --------
def g3_outage(skip):
    if skip:
        log("  skipped by --skip-outage")
        return None, "skipped by --skip-outage (run without the flag before shipping)"
    if not RUN_INGEST.exists():
        raise GateError(f"missing {RUN_INGEST}")
    tmpdir = Path(tempfile.mkdtemp(prefix="eqs-g3-outage-"))
    scratch_db = tmpdir / "outage-scratch.db"
    cmd = [
        PY, RUN_INGEST, "--db", scratch_db,
        "--base-url-data", UNREACHABLE, "--base-url-archives", UNREACHABLE,
    ]
    log(f"  run_ingest vs unreachable hosts ({UNREACHABLE}), throwaway db: {scratch_db}")
    try:
        proc = sub_run(cmd, timeout=300)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    log(f"  exit code: {proc.returncode}  (0=quiet day, 1=partial, 2=total outage - MUST be 2 here)")
    print_tail(proc)
    if proc.returncode == 2:
        return True, "total outage exits 2 - distinguishable from a quiet day"
    if proc.returncode == 0:
        return False, "exit 0 against unreachable hosts - trap 6.1 is LIVE: an outage reads as a quiet day"
    return False, f"exit {proc.returncode}, expected 2 (every-source-failed must be its own code)"


# ---------------------------------------------------------------- G4 --------
def g4_terminal_audit():
    con = dbcon()
    rows = con.execute(
        "SELECT accession, reason, retired_at FROM terminal ORDER BY accession"
    ).fetchall()
    con.close()
    if not rows:
        log("  terminal table is empty (nothing retired) - vacuously clean")
        return True, "0 terminal rows"
    ok = True
    for r in rows:
        reason = (r["reason"] or "").strip()
        log(
            f"  [{'ok' if reason else 'FAIL'}] {r['accession']} "
            f"retired_at={r['retired_at']} reason={r['reason']!r}"
        )
        if not reason:
            ok = False
    return ok, (
        f"{len(rows)} terminal row(s), all with written reasons"
        if ok
        else "a failure was retired without being understood (empty reason)"
    )


# ---------------------------------------------------------------- G5 --------
def _run_extract(label):
    if not EXTRACT.exists():
        raise GateError(f"missing {EXTRACT}")
    log(f"  running extract.py ({label}) ...")
    proc = sub_run([PY, EXTRACT], timeout=900)
    if proc.returncode != 0:
        print_tail(proc)
        raise GateError(f"extract.py exited {proc.returncode} on the {label} run")
    return proc


def _restore_g5(accession, seq, original):
    con = dbcon()
    con.execute(
        "UPDATE vote_records SET how_voted_raw = ? WHERE accession = ? AND seq = ?",
        (original, accession, seq),
    )
    con.commit()
    con.close()
    log(f"  manually restored how_voted_raw={original!r} for ({accession}, seq {seq})")


def g5_reparse():
    con = dbcon()
    c0 = con.execute("SELECT COUNT(*) FROM vote_records").fetchone()[0]
    con.close()
    log(f"  vote_records before: {c0}")

    _run_extract("first")
    con = dbcon()
    c1 = con.execute("SELECT COUNT(*) FROM vote_records").fetchone()[0]
    con.close()

    _run_extract("second")
    con = dbcon()
    c2 = con.execute("SELECT COUNT(*) FROM vote_records").fetchone()[0]
    dupes = con.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT accession, seq FROM vote_records
             GROUP BY accession, seq HAVING COUNT(*) > 1)
        """
    ).fetchone()[0]
    target = con.execute(
        """
        SELECT accession, seq, how_voted_raw FROM vote_records
         ORDER BY (how_voted_raw IS NULL), accession, seq LIMIT 1
        """
    ).fetchone()
    con.close()
    log(f"  counts: run1={c1} run2={c2}; duplicate (accession,seq) pairs: {dupes}")
    if c1 != c2 or dupes != 0:
        return False, f"re-extract not idempotent (run1={c1}, run2={c2}, dupes={dupes})"
    if target is None:
        return False, "no vote_records exist to test correction on"

    accession, seq, original = target["accession"], target["seq"], target["how_voted_raw"]
    con = dbcon()
    con.execute(
        "UPDATE vote_records SET how_voted_raw = ? WHERE accession = ? AND seq = ?",
        (G5_SENTINEL, accession, seq),
    )
    con.commit()
    con.close()
    log(f"  corrupted ({accession}, seq {seq}): how_voted_raw {original!r} -> {G5_SENTINEL!r}")

    try:
        _run_extract("corrective")
    except GateError as e:
        _restore_g5(accession, seq, original)
        return False, f"corrective extract failed ({e}); corruption manually restored"

    con = dbcon()
    row = con.execute(
        "SELECT how_voted_raw FROM vote_records WHERE accession = ? AND seq = ?",
        (accession, seq),
    ).fetchone()
    con.close()
    if row is None:
        return False, f"row ({accession}, seq {seq}) VANISHED after re-extract - worse than insert-ignore"
    value = row["how_voted_raw"]
    log(f"  after corrective extract: how_voted_raw={value!r} (expected {original!r})")
    if value == original:
        return True, (
            f"idempotent (run1==run2=={c2}, 0 dupes) and corrective "
            f"(sentinel overwritten back to {original!r} - UPSERT proven)"
        )
    if value == G5_SENTINEL:
        _restore_g5(accession, seq, original)
        return False, "sentinel SURVIVED re-extract - insert-ignore is discarding corrections (trap 6.5); manually restored"
    _restore_g5(accession, seq, original)
    return False, f"re-extract wrote {value!r}, expected {original!r}; manually restored"


# ---------------------------------------------------------------- G6 --------
def _fingerprint_run(perturb):
    if not EXTRACT.exists():
        raise GateError(f"missing {EXTRACT}")
    extra = {"EXTRACT_CONFIG_PERTURB": "1"} if perturb else None
    proc = sub_run([PY, EXTRACT, "--print-fingerprint"], timeout=120, extra_env=extra)
    if proc.returncode != 0:
        print_tail(proc)
        raise GateError(f"extract.py --print-fingerprint exited {proc.returncode} (perturb={perturb})")
    rid = parse_engine_run_id((proc.stdout or "") + "\n" + (proc.stderr or ""))
    if rid is None:
        print_tail(proc)
        raise GateError("no 16-hex engine_run_id found in --print-fingerprint output")
    return rid


def g6_provenance():
    con = dbcon()
    orphans = con.execute(
        """
        SELECT COUNT(*) FROM vote_records vr
          LEFT JOIN engine_runs er ON er.engine_run_id = vr.engine_run_id
         WHERE er.engine_run_id IS NULL
        """
    ).fetchone()[0]
    runs = con.execute(
        "SELECT engine_run_id, code_fingerprint, config_hash, git_commit FROM engine_runs"
    ).fetchall()
    con.close()

    ok = True
    log(f"  [{'ok' if orphans == 0 else 'FAIL'}] orphan engine_run_ids in vote_records: {orphans} (manifest rows: {len(runs)})")
    if orphans != 0:
        ok = False

    for r in runs:
        computed = engine_run_id_formula(r["code_fingerprint"], r["config_hash"])
        match = computed == r["engine_run_id"]
        log(
            f"  [{'ok' if match else 'FAIL'}] manifest {r['engine_run_id']}: "
            f"sha256(code_fp|config_hash)[:16] recomputes to {computed}"
        )
        if not match:
            ok = False

    baseline = _fingerprint_run(perturb=False)
    perturbed = _fingerprint_run(perturb=True)
    again = _fingerprint_run(perturb=False)
    log(f"  fingerprints: baseline={baseline} perturbed={perturbed} unperturbed-re-run={again}")
    if perturbed == baseline:
        log("  [FAIL] EXTRACT_CONFIG_PERTURB=1 did NOT change engine_run_id - config is not in the fingerprint")
        ok = False
    else:
        log("  [ok] perturbed config -> different engine_run_id")
    if again != baseline:
        log("  [FAIL] unperturbed re-run changed engine_run_id - the fingerprint is unstable")
        ok = False
    else:
        log("  [ok] unperturbed re-run -> same engine_run_id (stable)")

    ref_fp = runs[0]["code_fingerprint"] if runs else "code-fingerprint-reference"
    ref_ch = runs[0]["config_hash"] if runs else "config-hash-reference"
    id_a = engine_run_id_formula(ref_fp, ref_ch, git_commit="a" * 40)
    id_b = engine_run_id_formula(ref_fp, ref_ch, git_commit="b" * 40)
    log(
        f"  [{'ok' if id_a == id_b else 'FAIL'}] git_commit ignored by construction: "
        f"id(commit A)={id_a} id(commit B)={id_b}"
    )
    if id_a != id_b:
        ok = False

    return ok, (
        "provenance is a behaviour fingerprint, not trace metadata"
        if ok
        else "provenance gate failed (see lines above)"
    )


# ---------------------------------------------------------------- G7 --------
def g7_export_consistency():
    """Every published number recomputes from the DB: category counts, the
    vote distribution, the by_source cells (numerator AND denominator), the
    proposal/lot grouping per record, the totals (records, lots and proposals
    held apart - RapidForge review note 3), and the managementRecommendation
    semantics block. LOCKSTEP with export_site.py."""
    meta_path = SITE_DATA / "meta.json"
    rollup_path = SITE_DATA / "rollup.json"
    for p in (meta_path, rollup_path):
        if not p.exists():
            raise GateError(f"missing artifact: {p} - run export_site.py first")
    meta = load_json(meta_path)
    rollup = load_json(rollup_path)

    checks = []

    def chk(ok_, label, detail):
        checks.append(bool(ok_))
        log(f"  [{'ok' if ok_ else 'FAIL'}] {label}: {detail}")

    acc = meta.get("filing", {}).get("accession")
    chk(bool(acc), "meta.filing.accession present", repr(acc))
    if not acc:
        return False, "meta.json has no filing.accession - cannot scope the DB comparison"

    thin_n = meta.get("thin_n")
    chk(isinstance(thin_n, int), "meta.thin_n is an integer", repr(thin_n))
    sys.path.insert(0, str(PIPELINE_DIR))
    from sources import CONFIG  # noqa: PLC0415
    chk(thin_n == CONFIG.get("thin_n"), "meta.thin_n == CONFIG thin_n",
        f"meta={thin_n} config={CONFIG.get('thin_n')}")
    chk(meta.get("config") == {"thin_n": CONFIG.get("thin_n")},
        "meta.config names exactly the typed constants", f"meta={meta.get('config')!r}")

    con = dbcon()
    db_filing = con.execute(
        "SELECT raw_sha256 FROM filings WHERE accession = ?", (acc,)
    ).fetchone()
    rows = con.execute(
        "SELECT seq, category_type, how_voted, how_voted_raw, mgmt_rec, vote_source, "
        "vote_series, proposal_no, lot_index, lots_in_proposal, shares_voted, categories_all, "
        "cusip, issuer_name FROM vote_records WHERE accession = ?",
        (acc,),
    ).fetchall()
    con.close()

    chk(db_filing is not None, "meta filing exists in DB", acc)
    if db_filing is not None:
        chk(
            db_filing["raw_sha256"] == meta["filing"].get("raw_sha256"),
            "meta filing.raw_sha256 matches DB",
            f"meta={meta['filing'].get('raw_sha256')!r}",
        )
    ungrouped = sum(1 for r in rows if r["proposal_no"] is None or r["lot_index"] is None
                    or r["lots_in_proposal"] is None)
    chk(ungrouped == 0, "every DB row carries proposal grouping", f"{ungrouped} ungrouped")
    series = sorted({r["vote_series"] for r in rows if r["vote_series"]})
    chk(len(series) == 1 and meta["filing"].get("series_id") == series[0],
        "one series per filing, published",
        f"db={series} meta={meta['filing'].get('series_id')!r}")

    db_total = len(rows)
    db_counts = Counter(bucket(r["category_type"]) for r in rows)
    lots_per_proposal = Counter(r["proposal_no"] for r in rows if (r["lot_index"] or 0) >= 1)
    cats_of_proposal = {}
    for r in rows:
        cats_of_proposal.setdefault(r["proposal_no"], set()).add(bucket(r["category_type"]))

    cats = rollup.get("categories")
    chk(
        isinstance(cats, list) and len(cats) > 0,
        "rollup.categories is a non-empty list",
        f"type={type(cats).__name__}, len={len(cats) if isinstance(cats, list) else 'n/a'}",
    )
    if not isinstance(cats, list):
        return False, "rollup.json malformed - categories is not a list"

    names = [c.get("category") for c in cats]
    chk(len(names) == len(set(names)), "category names unique in rollup", f"{len(names)} entries")
    missing = sorted(set(db_counts) - set(names))
    extra = sorted(set(names) - set(db_counts))
    chk(not missing, "no DB category missing from rollup", f"missing={missing}")
    chk(not extra, "no rollup category absent from DB", f"extra={extra}")

    sum_n = 0
    expected_files = set()
    for c in cats:
        name, slug, n = c.get("category"), c.get("slug"), c.get("n")
        sum_n += n if isinstance(n, int) else 0
        expected_files.add(f"{slug}.json")
        chk(set(c.keys()) == CATEGORY_KEYS, f"category keys for {name!r}",
            f"extra={sorted(set(c.keys()) - CATEGORY_KEYS)} "
            f"missing={sorted(CATEGORY_KEYS - set(c.keys()))}")
        chk(slug == slugify(name or ""), f"slug rule for {name!r}", f"slug={slug!r}")
        rs = [r for r in rows if bucket(r["category_type"]) == name]
        chk(n == len(rs), f"rollup n for {name!r}", f"rollup={n} db={len(rs)}")
        db_lots = sum(1 for r in rs if (r["lot_index"] or 0) >= 1)
        props_here = {r["proposal_no"] for r in rs}
        db_props = len(props_here)
        chk(c.get("n_lots") == db_lots and c.get("n_proposals") == db_props,
            f"lots/proposals for {name!r}",
            f"rollup lots={c.get('n_lots')} props={c.get('n_proposals')} "
            f"db lots={db_lots} props={db_props}")
        db_shared = sum(1 for pn in props_here if len(cats_of_proposal[pn]) > 1)
        db_zero = sum(1 for r in rs if (r["lot_index"] or 0) >= 1 and r["shares_voted"] == 0)
        chk(c.get("n_proposals_shared") == db_shared and c.get("n_zero_share_lots") == db_zero,
            f"shared proposals / zero-share lots for {name!r}",
            f"rollup shared={c.get('n_proposals_shared')} zero={c.get('n_zero_share_lots')} "
            f"db shared={db_shared} zero={db_zero}")
        votes = c.get("votes") or {}
        vote_sum = sum(votes.get(k, 0) for k in (*VOTE_ENUM, "UNPARSEABLE", "ABSENT"))
        chk(vote_sum == n, f"votes sum to n for {name!r}", f"sum={vote_sum} n={n}")
        for k in VOTE_ENUM:
            dbk = sum(1 for r in rs if r["how_voted"] == k)
            if votes.get(k) != dbk:
                chk(False, f"votes.{k} for {name!r}", f"rollup={votes.get(k)} db={dbk}")
        bs = c.get("by_source") or {}
        chk(all(k in bs for k in SOURCE_KEYS)
            and set(bs) <= set(SOURCE_KEYS) | {"OTHER", "ABSENT"},
            f"by_source keys for {name!r}", f"{sorted(bs)}")
        for key, cell in bs.items():
            want = cell_from_rows(
                [r for r in rs if source_bucket(r["vote_source"]) == key], thin_n)
            same = isinstance(cell, dict) and set(cell) == CELL_KEYS and cell == want
            chk(same, f"by_source[{key}] for {name!r}",
                f"{want['for_lots']}/{want['n_voted']} FOR" if same
                else f"stated={cell} recomputed={want}")

        fpath = CATEGORY_DIR / f"{slug}.json"
        if not fpath.exists():
            chk(False, f"category file for {name!r}", f"missing {fpath}")
            continue
        cat = load_json(fpath)
        recs = cat.get("records")
        chk(
            cat.get("category") == name and cat.get("slug") == slug and cat.get("n") == n,
            f"category file header for {name!r}",
            f"category={cat.get('category')!r} slug={cat.get('slug')!r} n={cat.get('n')}",
        )
        chk(
            isinstance(recs, list) and len(recs) == n,
            f"record count in {slug}.json",
            f"len={len(recs) if isinstance(recs, list) else 'n/a'} n={n}",
        )
        if isinstance(recs, list):
            bad_urls = sum(
                1 for r in recs
                if not (isinstance(r.get("source_url"), str) and r["source_url"].strip())
            )
            chk(bad_urls == 0, f"non-empty source_url in {slug}.json",
                f"{bad_urls} empty of {len(recs)}")
            keys = [record_sort_key(r) for r in recs]
            chk(keys == sorted(keys), f"record ordering in {slug}.json",
                "meeting_date, issuer_name, proposal_no, lot_index, seq")
            bad_group = sum(
                1 for r in recs
                if not (isinstance(r.get("proposal_no"), int)
                        and isinstance(r.get("lot_index"), int)
                        and r.get("lots_in_proposal")
                        == lots_per_proposal.get(r.get("proposal_no"), 0)))
            chk(bad_group == 0, f"proposal grouping in {slug}.json",
                f"{bad_group} records disagree with the DB's lots-per-proposal")
            bad_rec = sum(1 for r in recs
                          if r.get("mgmt_rec") is not None and r.get("mgmt_rec") not in REC_ENUM)
            chk(bad_rec == 0, f"mgmt_rec enum in {slug}.json", f"{bad_rec} outside {REC_ENUM}")
            bad_other = sum(
                1 for r in recs
                if r.get("other_categories") != sorted(
                    cats_of_proposal.get(r.get("proposal_no"), set()) - {name}))
            chk(bad_other == 0, f"other_categories in {slug}.json",
                f"{bad_other} records disagree with the DB's categories per proposal")

    on_disk = {p.name for p in CATEGORY_DIR.glob("*.json")} if CATEGORY_DIR.exists() else set()
    stale = sorted(on_disk - expected_files)
    chk(not stale, "no stale category files on disk", f"stale={stale}")

    totals = meta.get("totals") or {}
    want_totals = {
        "records": db_total,
        "lots": sum(1 for r in rows if (r["lot_index"] or 0) >= 1),
        "zero_lot_rows": sum(1 for r in rows if (r["lot_index"] or 0) == 0),
        "proposals": len({r["proposal_no"] for r in rows}),
        "proposals_in_multiple_categories": sum(
            1 for cs in cats_of_proposal.values() if len(cs) > 1),
        "issuers": len({r["cusip"] for r in rows if r["cusip"]}),
        "issuer_name_spellings": len({r["issuer_name"] for r in rows if r["issuer_name"]}),
        "categories": len(cats),
        "unparseable_how_voted": sum(
            1 for r in rows if r["how_voted_raw"] is not None and r["how_voted"] is None),
        "absent_how_voted": sum(1 for r in rows if r["how_voted_raw"] is None),
        "zero_share_lots": sum(
            1 for r in rows if (r["lot_index"] or 0) >= 1 and r["shares_voted"] == 0),
        "multi_category_records": sum(
            1 for r in rows if (r["categories_all"] or "").find("|") != -1),
    }
    for k, v in want_totals.items():
        chk(totals.get(k) == v, f"meta totals.{k} == DB", f"meta={totals.get(k)} db={v}")
    chk(set(totals) == set(want_totals), "meta totals carries exactly the expected keys",
        f"extra={sorted(set(totals) - set(want_totals))}")
    chk(totals.get("lots", 0) + totals.get("zero_lot_rows", 0) == totals.get("records"),
        "lots + zero-lot rows == records (held apart, never one number)",
        f"{totals.get('lots')} + {totals.get('zero_lot_rows')} == {totals.get('records')}")
    chk(sum_n == totals.get("records"), "sum(category n) == totals.records",
        f"sum={sum_n} records={totals.get('records')}")

    # managementRecommendation semantics - recomputed, threshold-free rule LOCKSTEP
    sem = meta.get("mgmt_rec_semantics") or {}
    lots_all = [r for r in rows if (r["lot_index"] or 0) >= 1]
    with_any_rec = [r for r in lots_all if r["mgmt_rec"] in VOTE_ENUM]
    by_prop = {}
    for r in with_any_rec:
        by_prop.setdefault(r["proposal_no"], set()).add(r["mgmt_rec"])
    mixed = {pn for pn, vals in by_prop.items() if len(vals) > 1}
    sh = [r for r in lots_all if source_bucket(r["vote_source"]) == "SECURITY HOLDER"]
    with_rec = [r for r in sh if r["how_voted"] in VOTE_ENUM and r["mgmt_rec"] in VOTE_ENUM]
    agree = sum(1 for r in with_rec if r["how_voted"] == r["mgmt_rec"])
    if len(with_any_rec) < (thin_n or 0):
        verdict = "insufficient"
    elif len(mixed) >= (thin_n or 0):
        verdict = "not-board-view"
    else:
        verdict = "board-view"
    want_sem = {"lots_with_recommendation": len(with_any_rec),
                "proposals_with_recommendation": len(by_prop),
                "proposals_with_mixed_recommendation": len(mixed),
                "crosstab_shareholder_lots": crosstab_rows(sh),
                "crosstab_management_lots": crosstab_rows(
                    [r for r in lots_all if source_bucket(r["vote_source"]) == "ISSUER"]),
                "shareholder_lots": len(sh),
                "shareholder_lots_with_recommendation": len(with_rec),
                "agreeing": agree, "agreement": f"{agree}/{len(with_rec)}",
                "agreement_pct": pct(agree, len(with_rec)),
                "verdict": verdict, "headline_allowed": verdict == "board-view"}
    for k, v in want_sem.items():
        chk(sem.get(k) == v, f"meta mgmt_rec_semantics.{k}",
            f"meta={sem.get(k)!r} recomputed={v!r}")
    ex = sem.get("example_mixed_proposal")
    if mixed:
        ex_ok = (isinstance(ex, dict) and ex.get("proposal_no") in mixed
                 and ex.get("lots") == lots_per_proposal.get(ex.get("proposal_no"))
                 and sorted(ex.get("recommendations") or []) == sorted(by_prop[ex.get("proposal_no")]))
        chk(ex_ok, "meta mgmt_rec_semantics.example_mixed_proposal is a real mixed proposal",
            f"{ex!r}"[:160])
    else:
        chk(ex is None, "no example when no proposal is mixed", f"{ex!r}")

    failed = checks.count(False)
    return failed == 0, (
        f"all {len(checks)} consistency checks passed"
        if failed == 0
        else f"{failed} of {len(checks)} consistency checks FAILED"
    )


# ---------------------------------------------------------------- G8 --------
def g8_anti_blend():
    """No blended cross-category number, no recommendation-derived headline.
    Walks every published artifact for forbidden key names, holds rollup.json
    to exactly one top-level key, holds every category to exactly the contract
    keys (a category-level percentage would blend proposers), and requires the
    semantics block to say why no concordance headline exists."""
    rollup_path = SITE_DATA / "rollup.json"
    meta_path = SITE_DATA / "meta.json"
    for p in (rollup_path, meta_path):
        if not p.exists():
            raise GateError(f"missing artifact: {p} - run export_site.py first")
    rollup = load_json(rollup_path)
    meta = load_json(meta_path)
    ok = True
    top = sorted(rollup.keys())
    log(f"  top-level keys: {top}")
    if set(top) != {"categories"}:
        ok = False
        log(f"  [FAIL] unexpected top-level key(s): {[k for k in top if k != 'categories']} "
            "- a blended cross-category number has no home here")
    else:
        log("  [ok] only top-level key is 'categories' - no blended number anywhere")

    artifacts = {"rollup.json": rollup, "meta.json": meta}
    for p in (sorted(CATEGORY_DIR.glob("*.json")) if CATEGORY_DIR.exists() else []):
        artifacts[f"category/{p.name}"] = load_json(p)
    hits = []
    for name, obj in artifacts.items():
        for path in walk_keys(obj):
            leaf = path.rsplit(".", 1)[-1]
            if FORBIDDEN_KEY.search(leaf):
                hits.append(f"{name}:{path}")
    log(f"  forbidden key names ({FORBIDDEN_KEY.pattern}) across {len(artifacts)} artifacts: {len(hits)}")
    if hits:
        ok = False
        for h in hits[:10]:
            log(f"  [FAIL] {h}")

    cats = rollup.get("categories") or []
    bad_cat = [c.get("category") for c in cats
               if not isinstance(c, dict) or set(c.keys()) != CATEGORY_KEYS]
    bad_cell = [c.get("category") for c in cats if isinstance(c, dict) and any(
        not isinstance(cell, dict) or set(cell) != CELL_KEYS
        for cell in (c.get("by_source") or {}).values())]
    log(f"  categories with exactly the contract keys: {len(cats) - len(bad_cat)} of {len(cats)}")
    if not cats or bad_cat or bad_cell:
        ok = False
        log(f"  [FAIL] categories off-contract: {bad_cat}; cells off-contract: {bad_cell}")

    sem = meta.get("mgmt_rec_semantics") or {}
    verdict = sem.get("verdict")
    log(f"  mgmt_rec_semantics: mixed={sem.get('proposals_with_mixed_recommendation')} "
        f"agreement={sem.get('agreement')} -> {verdict!r}, "
        f"headline_allowed={sem.get('headline_allowed')!r}")
    if verdict not in VERDICTS:
        ok = False
        log("  [FAIL] meta.mgmt_rec_semantics.verdict missing or unknown")
    if sem.get("headline_allowed") is not (verdict == "board-view"):
        ok = False
        log("  [FAIL] headline_allowed must be true only for a board-view verdict")
    return ok, (
        "per-category only; no forbidden key anywhere; semantics block present"
        if ok
        else "anti-blend rule violated"
    )


# ---------------------------------------------------------------- main ------
def g9_listing_coverage():
    """The denominator gate (review finding 2026-08-28). The source-listed
    expected set is persisted per run in `listings`; the NEWEST listed
    accession per source must actually be in `filings` with vote_records - a
    terminal retirement or silent miss of the newest filing must FAIL here,
    never read as a quiet day."""
    con = dbcon()
    try:
        run = con.execute("SELECT MAX(run_id) AS r FROM listings").fetchone()
    except Exception as e:
        con.close()
        return False, f"listings table missing ({e}) - re-run run_ingest.py"
    if run is None or run["r"] is None:
        con.close()
        return False, "listings table empty - re-run run_ingest.py"
    rid = run["r"]
    ok = True
    details = []
    for s in con.execute(
            "SELECT DISTINCT source_id FROM listings WHERE run_id = ?",
            (rid,)).fetchall():
        sid = s["source_id"]
        newest = con.execute(
            "SELECT accession FROM listings WHERE run_id = ? AND source_id = ? "
            "ORDER BY (filed_at IS NULL), filed_at DESC, accession DESC LIMIT 1",
            (rid, sid)).fetchone()
        acc = newest["accession"]
        have = con.execute(
            "SELECT 1 FROM filings WHERE accession = ?", (acc,)).fetchone()
        nrec = con.execute(
            "SELECT COUNT(*) AS n FROM vote_records WHERE accession = ?",
            (acc,)).fetchone()["n"]
        why = con.execute(
            "SELECT reason FROM terminal WHERE accession = ?", (acc,)).fetchone()
        good = bool(have) and nrec > 0
        term = " TERMINAL({})".format(why["reason"]) if why else ""
        line = "{}: newest listed {} in_filings={} vote_records={}{}".format(
            sid, acc, bool(have), nrec, term)
        log("  [{}] {}".format("ok" if good else "FAIL", line))
        details.append(line)
        ok = ok and good
    con.close()
    if ok:
        return True, "newest listed filing extracted for every source (run {})".format(rid)
    return False, "; ".join(details)


def g10_publication_committed():
    """Regression guard for the critical review finding (2026-08-28): an
    unanchored data/ gitignore pattern silently ignored site/data/ - the
    ENTIRE publication payload - while export_site.py regenerated it before
    every check, so nothing automated could ever see the miss. Ask git
    directly."""
    import subprocess as sp
    probe = sp.run(["git", "check-ignore", "-q", "site/data/meta.json"],
                   cwd=str(ROOT), capture_output=True)
    not_ignored = probe.returncode != 0
    log("  [{}] git check-ignore site/data/meta.json -> exit {} "
        "(0 = IGNORED = the publication would deploy empty)".format(
            "ok" if not_ignored else "FAIL", probe.returncode))
    tracked = sp.run(["git", "ls-files", "site/data/"],
                     cwd=str(ROOT), capture_output=True, text=True)
    n_tracked = len([l for l in tracked.stdout.splitlines() if l.strip()])
    log("  tracked publication files: {} (0 acceptable only before the "
        "first commit of a fresh export)".format(n_tracked))
    if not not_ignored:
        return False, "site/data is GITIGNORED - the publication cannot deploy"
    return True, "site/data not ignored; {} file(s) tracked".format(n_tracked)

def main():
    parser = argparse.ArgumentParser(description="EqualShares deterministic gates")
    parser.add_argument(
        "--skip-outage",
        action="store_true",
        help="skip G3 (the run_ingest outage subprocess); it must still run at least once before the build is called done",
    )
    args = parser.parse_args()

    log("EqualShares gates - evidence-based PASS/FAIL; exit 0 only on all-pass")
    log(f"repo root: {ROOT}")
    log(f"database : {DB_PATH}")

    gates = [
        ("G1", "raw-integrity", g1_raw_integrity),
        ("G2", "coverage", g2_coverage),
        ("G3", "outage-distinguishable", lambda: g3_outage(args.skip_outage)),
        ("G4", "terminal-audit", g4_terminal_audit),
        ("G5", "reparse-idempotent-and-corrective", g5_reparse),
        ("G6", "provenance", g6_provenance),
        ("G7", "export-consistency", g7_export_consistency),
        ("G8", "anti-blend", g8_anti_blend),
        ("G9", "listing-coverage", g9_listing_coverage),
        ("G10", "publication-committed", g10_publication_committed),
    ]

    results = []
    for gid, name, fn in gates:
        log("")
        log(f"=== {gid} {name} ===")
        try:
            passed, summary = fn()
        except GateError as e:
            log(f"  {e}")
            passed, summary = False, str(e)
        except subprocess.TimeoutExpired as e:
            log(f"  child process timed out: {e}")
            passed, summary = False, "subprocess timeout"
        except Exception:
            for line in traceback.format_exc().splitlines():
                log(f"  {line}")
            passed, summary = False, "unhandled exception (see traceback above)"
        status = "SKIP" if passed is None else ("PASS" if passed else "FAIL")
        log(f"{gid} {status} - {summary}")
        results.append((gid, name, status, summary))

    log("")
    log("=" * 70)
    log(f"{'GATE':<5} {'NAME':<36} RESULT")
    log("-" * 70)
    for gid, name, status, _summary in results:
        log(f"{gid:<5} {name:<36} {status}")
    log("=" * 70)
    n_pass = sum(1 for r in results if r[2] == "PASS")
    n_fail = sum(1 for r in results if r[2] == "FAIL")
    n_skip = sum(1 for r in results if r[2] == "SKIP")
    verdict = "PASS" if n_fail == 0 else "FAIL"
    log(f"OVERALL: {verdict}  ({n_pass} passed, {n_fail} failed, {n_skip} skipped)")
    if n_skip:
        log("note: a SKIPped gate is not evidence - run without --skip-outage before shipping")
    sys.exit(0 if n_fail == 0 else 1)


if __name__ == "__main__":
    main()
