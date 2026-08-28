#!/usr/bin/env python3
"""checks.py — THE GATES for EqualShares "The Roll Call".

Usage:  python pipeline/checks.py [--skip-outage]

Eight deterministic gates. Each prints PASS/FAIL with extracted evidence —
counts and values, never just a child's exit code:

  G1 raw-integrity          filings exist; every raw file exists; sha256 + size match
  G2 coverage               every filing has > 0 vote_records (ingestion trap 6.8)
  G3 outage-distinguishable run_ingest vs unreachable hosts MUST exit 2 (trap 6.1)
  G4 terminal-audit         every terminal row carries a non-empty written reason
  G5 reparse                extract twice: identical count, zero dupes; corrupt one
                            row, re-extract restores it (proves UPSERT, kills
                            insert-ignore — trap 6.5)
  G6 provenance             zero orphan engine_run_ids; manifest ids recompute from
                            sha256(code_fp|config_hash)[:16]; EXTRACT_CONFIG_PERTURB=1
                            changes the id, unperturbed re-run does not; git_commit
                            ignored by construction (provenance traps 6.1/6.2)
  G7 export-consistency     site/data artifacts agree with the DB, exactly
  G8 anti-blend             rollup.json has NO top-level blended number

Exit 0 only if every gate passed. --skip-outage marks G3 SKIP (not a pass —
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
G5_SENTINEL = "G5-CORRUPTION-SENTINEL-DO-NOT-SHIP"
UNREACHABLE = "http://127.0.0.1:9"


class GateError(Exception):
    """A gate failure with a written reason — a controlled FAIL, not a crash."""


def log(msg=""):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def dbcon():
    if not DB_PATH.exists():
        raise GateError(f"database not found: {DB_PATH} — run ingest + extract first")
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
    git_commit is accepted and deliberately unused — trace metadata never keys
    behaviour (extractor-provenance trap 6.2). G6 calls this with two different
    commits and requires equality."""
    _ = git_commit
    return hashlib.sha256(
        f"{code_fingerprint}|{config_hash}".encode("utf-8")
    ).hexdigest()[:16]


def bucket(category_type):
    """LOCKSTEP copy of export_site.bucket — change both or G7 fails (the point)."""
    if category_type is None or str(category_type).strip() == "":
        return UNCATEGORIZED
    return category_type


def slugify(category):
    """LOCKSTEP copy of export_site.slugify."""
    return re.sub(r"[^a-z0-9]+", "-", category.lower()).strip("-")


def record_sort_key(rec):
    """LOCKSTEP with export_site.record_sort_key, over the JSON dict shape."""
    md = rec.get("meeting_date")
    issuer = rec.get("issuer_name")
    return (md is not None, md or "", issuer is not None, issuer or "", rec.get("seq", 0))


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
        return False, "filings table is empty — nothing was ingested"
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
        else "a filing with ZERO records — trap 6.8: the parsed document may not be the vote-bearing one"
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
    log(f"  exit code: {proc.returncode}  (0=quiet day, 1=partial, 2=total outage — MUST be 2 here)")
    print_tail(proc)
    if proc.returncode == 2:
        return True, "total outage exits 2 — distinguishable from a quiet day"
    if proc.returncode == 0:
        return False, "exit 0 against unreachable hosts — trap 6.1 is LIVE: an outage reads as a quiet day"
    return False, f"exit {proc.returncode}, expected 2 (every-source-failed must be its own code)"


# ---------------------------------------------------------------- G4 --------
def g4_terminal_audit():
    con = dbcon()
    rows = con.execute(
        "SELECT accession, reason, retired_at FROM terminal ORDER BY accession"
    ).fetchall()
    con.close()
    if not rows:
        log("  terminal table is empty (nothing retired) — vacuously clean")
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
        return False, f"row ({accession}, seq {seq}) VANISHED after re-extract — worse than insert-ignore"
    value = row["how_voted_raw"]
    log(f"  after corrective extract: how_voted_raw={value!r} (expected {original!r})")
    if value == original:
        return True, (
            f"idempotent (run1==run2=={c2}, 0 dupes) and corrective "
            f"(sentinel overwritten back to {original!r} — UPSERT proven)"
        )
    if value == G5_SENTINEL:
        _restore_g5(accession, seq, original)
        return False, "sentinel SURVIVED re-extract — insert-ignore is discarding corrections (trap 6.5); manually restored"
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
        log("  [FAIL] EXTRACT_CONFIG_PERTURB=1 did NOT change engine_run_id — config is not in the fingerprint")
        ok = False
    else:
        log("  [ok] perturbed config -> different engine_run_id")
    if again != baseline:
        log("  [FAIL] unperturbed re-run changed engine_run_id — the fingerprint is unstable")
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
    meta_path = SITE_DATA / "meta.json"
    rollup_path = SITE_DATA / "rollup.json"
    for p in (meta_path, rollup_path):
        if not p.exists():
            raise GateError(f"missing artifact: {p} — run export_site.py first")
    meta = load_json(meta_path)
    rollup = load_json(rollup_path)

    checks = []

    def chk(ok_, label, detail):
        checks.append(bool(ok_))
        log(f"  [{'ok' if ok_ else 'FAIL'}] {label}: {detail}")

    acc = meta.get("filing", {}).get("accession")
    chk(bool(acc), "meta.filing.accession present", repr(acc))
    if not acc:
        return False, "meta.json has no filing.accession — cannot scope the DB comparison"

    thin_n = meta.get("thin_n")
    chk(isinstance(thin_n, int), "meta.thin_n is an integer", repr(thin_n))

    con = dbcon()
    db_filing = con.execute(
        "SELECT raw_sha256 FROM filings WHERE accession = ?", (acc,)
    ).fetchone()
    rows = con.execute(
        "SELECT seq, category_type, how_voted, how_voted_raw, mgmt_rec "
        "FROM vote_records WHERE accession = ?",
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

    db_total = len(rows)
    db_counts = Counter(bucket(r["category_type"]) for r in rows)
    db_comparable = sum(
        1 for r in rows if r["how_voted"] is not None and r["mgmt_rec"] is not None
    )
    db_unparseable = sum(
        1 for r in rows if r["how_voted_raw"] is not None and r["how_voted"] is None
    )

    cats = rollup.get("categories")
    chk(
        isinstance(cats, list) and len(cats) > 0,
        "rollup.categories is a non-empty list",
        f"type={type(cats).__name__}, len={len(cats) if isinstance(cats, list) else 'n/a'}",
    )
    if not isinstance(cats, list):
        return False, "rollup.json malformed — categories is not a list"

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
        chk(slug == slugify(name or ""), f"slug rule for {name!r}", f"slug={slug!r}")
        dbn = db_counts.get(name, 0)
        chk(n == dbn, f"rollup n for {name!r}", f"rollup={n} db={dbn}")
        votes = c.get("votes") or {}
        vote_sum = sum(votes.get(k, 0)
                       for k in (*VOTE_ENUM, "UNPARSEABLE", "ABSENT"))
        chk(vote_sum == n, f"votes sum to n for {name!r}", f"sum={vote_sum} n={n}")
        nc, wm = c.get("n_comparable"), c.get("with_mgmt")
        if isinstance(nc, int) and isinstance(wm, int):
            expect_pct = round(100 * wm / nc, 1) if nc else None
            chk(
                c.get("with_mgmt_pct") == expect_pct,
                f"with_mgmt_pct formula for {name!r}",
                f"stated={c.get('with_mgmt_pct')} recomputed={expect_pct}",
            )
            if isinstance(thin_n, int):
                chk(
                    c.get("thin") == (nc < thin_n),
                    f"thin flag for {name!r}",
                    f"n_comparable={nc} thin_n={thin_n} thin={c.get('thin')}",
                )
        else:
            chk(False, f"n_comparable/with_mgmt types for {name!r}", f"n_comparable={nc!r} with_mgmt={wm!r}")

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
                1
                for r in recs
                if not (isinstance(r.get("source_url"), str) and r["source_url"].strip())
            )
            chk(bad_urls == 0, f"non-empty source_url in {slug}.json", f"{bad_urls} empty of {len(recs)}")
            keys = [record_sort_key(r) for r in recs]
            chk(keys == sorted(keys), f"record ordering in {slug}.json", "meeting_date, issuer_name, seq")

    on_disk = {p.name for p in CATEGORY_DIR.glob("*.json")} if CATEGORY_DIR.exists() else set()
    stale = sorted(on_disk - expected_files)
    chk(not stale, "no stale category files on disk", f"stale={stale}")

    totals = meta.get("totals") or {}
    chk(totals.get("records") == db_total, "meta totals.records == DB", f"meta={totals.get('records')} db={db_total}")
    chk(totals.get("categories") == len(cats), "meta totals.categories == rollup", f"meta={totals.get('categories')} rollup={len(cats)}")
    chk(
        totals.get("comparable_records") == db_comparable,
        "meta totals.comparable_records == DB",
        f"meta={totals.get('comparable_records')} db={db_comparable}",
    )
    chk(
        totals.get("unparseable_how_voted") == db_unparseable,
        "meta totals.unparseable_how_voted == DB",
        f"meta={totals.get('unparseable_how_voted')} db={db_unparseable}",
    )
    chk(sum_n == totals.get("records"), "sum(category n) == totals.records", f"sum={sum_n} records={totals.get('records')}")

    failed = checks.count(False)
    return failed == 0, (
        f"all {len(checks)} consistency checks passed"
        if failed == 0
        else f"{failed} of {len(checks)} consistency checks FAILED"
    )


# ---------------------------------------------------------------- G8 --------
def g8_anti_blend():
    rollup_path = SITE_DATA / "rollup.json"
    if not rollup_path.exists():
        raise GateError(f"missing artifact: {rollup_path} — run export_site.py first")
    rollup = load_json(rollup_path)
    top = sorted(rollup.keys())
    log(f"  top-level keys: {top}")
    ok = set(top) == {"categories"}
    if not ok:
        offenders = [k for k in top if k != "categories"]
        log(f"  [FAIL] unexpected top-level key(s): {offenders} — a blended cross-category number has no home here")
    else:
        log("  [ok] only top-level key is 'categories' — no blended number anywhere")
    cats = rollup.get("categories") or []
    inside = sum(
        1 for c in cats if isinstance(c, dict) and "with_mgmt" in c and "with_mgmt_pct" in c
    )
    log(f"  categories carrying per-category with_mgmt/with_mgmt_pct: {inside} of {len(cats)}")
    if not cats or inside != len(cats):
        ok = False
        log("  [FAIL] concordance must live inside categories[] — and ONLY there")
    return ok, (
        "only per-category concordance; no top-level blend"
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

    log("EqualShares gates — evidence-based PASS/FAIL; exit 0 only on all-pass")
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
        log(f"{gid} {status} — {summary}")
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
        log("note: a SKIPped gate is not evidence — run without --skip-outage before shipping")
    sys.exit(0 if n_fail == 0 else 1)


if __name__ == "__main__":
    main()
