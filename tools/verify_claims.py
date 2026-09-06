#!/usr/bin/env python
"""verify_claims.py - derive every counted claim in this repo's live documents from data, code or
git, and fail on drift (PROJECT_STANDARD rule 2: a counted claim in prose is derived by a script or
deleted). Stdlib only. Exit 0 only when every check passes.

  python tools/verify_claims.py
  python tools/verify_claims.py --json

Checks:
  C1 gates        README's gate table lists exactly the gate ids checks.py runs; each README name
                  is a prefix of the real name (README says checks.py's output is the authority).
  C2 filing       README's CIK / accession / period / filed date equal site/data/meta.json.
  C3 director%    README's "~NN% director elections" equals round(director n / total records)
                  from site/data/rollup.json and meta.json.
  C4 ascii        Rule 15: no em/en dashes, arrows, curly quotes or emoji in live documents and
                  the served site/index.html.
  C5 pointers     Rule 11: every F:/RapidForge path cited in the live documents exists on disk,
                  and every bare module/doc name in CLAUDE.md resolves.
  C6 resume       TODO.md's first H2 is '## RESUME HERE', it carries an 'as of YYYY-MM-DD', and
                  that date is NOT OLDER than the last commit. Currency added 2026-09-03: the
                  date-exists half passed while the block sat six commits and three days behind,
                  which is an instrument reporting green without checking the thing it is named for.
  C7 origin       README's ## Live URL equals tools/verify_deploy.py ORIGIN.
  C8 committed    site/data is tracked and not ignored (mirrors gate G10 without the database).
  C9 filings      README's spelled-out filing count equals the number of filings in index.json.
                  Added 2026-09-02: "eight fund series" was a counted claim in prose that no check
                  derived, which is standard rule 2's own failure mode sitting in the front door.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
RAPIDFORGE = Path("F:/RapidForge")
# Every LIVE markdown document in the repo. Dated design records under
# docs/superpowers/specs/ are deliberately absent: they are history, true as of their
# filename date, and rule 3 says history is never rewritten. Added 2026-09-02 after the
# documentation-currency pass found COLD_READ_PROTOCOL.md - a procedure in force - outside
# this list, so C4 and C5 had never once read it.
LIVE_DOCS = ["CLAUDE.md", "README.md", "TODO.md", "PLAYBOOK_DELTA.md", "AUDIT_LOG.md",
             "REBUILD.md", "CHATLOG.md", "docs/COLD_READ_PROTOCOL.md", "docs/FINDINGS.md"]
SERVED_DOCS = ["site/index.html"]
NON_ASCII_PUNCT = {
    "\u2013": "en dash", "\u2014": "em dash", "\u2192": "arrow",
    "\u2018": "curly quote", "\u2019": "curly quote", "\u201c": "curly quote", "\u201d": "curly quote",
}
EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def c1_gates():
    real = re.findall(r'\("(G\d+)", "([a-z0-9-]+)",', read("pipeline/checks.py"))
    doc = re.findall(r"^\| (G\d+) ([a-z0-9-]+) \|", read("README.md"), re.M)
    if not real or not doc:
        return False, "could not parse gate lists"
    if [g for g, _ in real] != [g for g, _ in doc]:
        return False, f"ids differ: checks.py {[g for g, _ in real]} vs README {[g for g, _ in doc]}"
    bad = [(g, d, r) for (g, r), (_, d) in zip(real, doc) if not r.startswith(d)]
    if bad:
        return False, f"README name is not a prefix of the real name: {bad}"
    return True, f"{len(real)} gates, ids and names agree"


def readme_filing():
    """Part 2: the README names one accession; its meta.json lives under filings/<acc>/."""
    readme = read("README.md")
    m = re.search(r"accession\s+(\d{10}-\d{2}-\d{6})", readme)
    if not m:
        raise ValueError("README names no accession")
    idx = json.loads(read("site/data/index.json"))
    row = next((r for r in idx.get("filings", []) if r.get("accession") == m.group(1)), None)
    if row is None:
        raise ValueError(f"README accession {m.group(1)} is not in site/data/index.json")
    return row, readme


def c2_filing():
    row, readme = readme_filing()
    meta = json.loads(read(f"site/data/{row['dir']}/meta.json"))
    want = {
        "CIK": meta["filer"]["cik"], "accession": meta["filing"]["accession"],
        "period": meta["filing"]["period_of_report"], "filed": meta["filing"]["filed_at"],
    }
    missing = [k for k, v in want.items() if v not in readme]
    if missing:
        return False, f"README lacks meta.json values for {missing}: {want}"
    return True, f"filing identity {want['accession']} agrees"


def c3_director_share():
    row, _ = readme_filing()
    rollup = json.loads(read(f"site/data/{row['dir']}/rollup.json"))
    meta = json.loads(read(f"site/data/{row['dir']}/meta.json"))
    de = next((c for c in rollup["categories"] if c["slug"] == "director-elections"), None)
    if de is None:
        return False, "rollup.json has no director-elections category"
    derived = round(100 * de["n"] / meta["totals"]["records"])
    m = re.search(r"~(\d+)% director elections", read("README.md"))
    if not m:
        return False, "README has no '~NN% director elections' claim"
    if int(m.group(1)) != derived:
        return False, f"README says ~{m.group(1)}%, derived {derived}% ({de['n']}/{meta['totals']['records']})"
    return True, f"~{derived}% director elections ({de['n']}/{meta['totals']['records']})"


def c4_ascii():
    hits = []
    for rel in LIVE_DOCS + SERVED_DOCS:
        p = ROOT / rel
        if not p.exists():
            continue
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            for ch, name in NON_ASCII_PUNCT.items():
                if ch in line:
                    hits.append(f"{rel}:{n} {name}")
            if EMOJI.search(line):
                hits.append(f"{rel}:{n} emoji")
    if hits:
        return False, f"{len(hits)} rule-15 hit(s): " + "; ".join(hits[:8]) + (" ..." if len(hits) > 8 else "")
    return True, f"{len(LIVE_DOCS + SERVED_DOCS)} documents plain ASCII punctuation"


def c5_pointers():
    bad, count = [], 0
    path_re = re.compile(r"F:[\\/]RapidForge[\\/][A-Za-z0-9_.\\/\-]+")
    for rel in LIVE_DOCS:
        p = ROOT / rel
        if not p.exists():
            continue
        for m in path_re.findall(p.read_text(encoding="utf-8")):
            cited = m.rstrip(".,;:)`*").replace("\\", "/")
            count += 1
            if not Path(cited).exists():
                bad.append(f"{rel}: {cited}")
    # bare module / doc names in CLAUDE.md's read order
    for name in re.findall(r"`([a-z0-9-]+\.md)`", read("CLAUDE.md")):
        count += 1
        candidates = [ROOT / name, RAPIDFORGE / "modules" / name, RAPIDFORGE / "docs" / name, RAPIDFORGE / name]
        if not any(c.exists() for c in candidates):
            bad.append(f"CLAUDE.md: {name} (not in repo, modules/, docs/ or RapidForge root)")
    if bad:
        return False, f"{len(bad)} rotted pointer(s): " + "; ".join(bad)
    return True, f"{count} pointers resolve"


def c6_resume():
    todo = read("TODO.md")
    h2 = re.findall(r"^## (.+)$", todo, re.M)
    if not h2 or h2[0].strip() != "RESUME HERE":
        return False, f"first H2 is {h2[0] if h2 else None!r}, not 'RESUME HERE'"
    block = todo.split("## RESUME HERE", 1)[1].split("\n## ", 1)[0]
    m = re.search(r"as of (\d{4}-\d{2}-\d{2})", block)
    if not m:
        return False, "RESUME HERE has no 'as of YYYY-MM-DD'"
    stamped = m.group(1)
    last = subprocess.run(["git", "log", "-1", "--date=short", "--format=%ad"],
                          cwd=ROOT, capture_output=True, text=True).stdout.strip()
    if last and stamped < last:
        return False, (f"RESUME HERE says {stamped} but the last commit is {last}: the live state "
                       f"predates the repo, so a cold reader would miss everything since")
    return True, f"RESUME HERE dated {stamped}, not older than the last commit ({last or 'none'})"


def c7_origin():
    live = read("README.md").split("## Live", 1)
    if len(live) < 2:
        return False, "README has no ## Live section"
    m = re.search(r"https?://[^\s)*`]+", live[1])
    vd = re.search(r'^ORIGIN = "([^"]+)"', read("tools/verify_deploy.py"), re.M)
    if not m or not vd:
        return False, "could not find the Live URL or verify_deploy ORIGIN"
    if m.group(0).rstrip("/") != vd.group(1).rstrip("/"):
        return False, f"README Live {m.group(0)} != verify_deploy ORIGIN {vd.group(1)}"
    return True, f"live origin {vd.group(1)}"


def c8_committed():
    tracked = subprocess.run(["git", "ls-files", "site/data"], cwd=ROOT, capture_output=True, text=True)
    files = [l for l in tracked.stdout.splitlines() if l.strip()]
    if not files:
        return False, "git tracks nothing under site/data"
    ign = subprocess.run(["git", "check-ignore", "-q", "site/data/index.json"], cwd=ROOT)
    if ign.returncode == 0:
        return False, "site/data/index.json is gitignored (the G10 defect)"
    return True, f"{len(files)} publication files tracked, not ignored"


WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven",
         8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve"}


def c9_filings():
    """README says how many fund series are published; index.json is the authority. A count in
    prose is derived or deleted (standard rule 2)."""
    n = len(json.loads(read("site/data/index.json")).get("filings", []))
    word = WORDS.get(n)
    if word is None:
        return False, f"{n} filings: past the spelled-out range this check knows"
    readme = read("README.md")
    phrase = f"{word} fund series"
    if phrase.lower() not in readme.lower():
        return False, (f"index.json has {n} filings; README does not say {phrase!r} "
                       f"(a counted claim in prose must agree with the data)")
    return True, f"README says {phrase!r}; index.json has {n}"


CHECKS = [("C1", "gates", c1_gates), ("C2", "filing", c2_filing), ("C3", "director%", c3_director_share),
          ("C4", "ascii", c4_ascii), ("C5", "pointers", c5_pointers), ("C6", "resume", c6_resume),
          ("C7", "origin", c7_origin), ("C8", "committed", c8_committed), ("C9", "filings", c9_filings)]


def main():
    ap = argparse.ArgumentParser(description="derive the live documents' claims and fail on drift")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    results = []
    for cid, name, fn in CHECKS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"
        results.append({"id": cid, "name": name, "ok": ok, "detail": detail})
    failed = [r for r in results if not r["ok"]]
    if a.json:
        print(json.dumps({"results": results, "failed": len(failed)}, indent=2))
        return 1 if failed else 0
    print("\nverify_claims - live documents vs data, code and git\n")
    for r in results:
        print(f"  {'PASS' if r['ok'] else 'FAIL'}  {r['id']} {r['name']:<10} {r['detail']}")
    print(f"\n  {len(failed)} failing check(s)." if failed else "\n  ALL PASS - every counted claim derives.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
