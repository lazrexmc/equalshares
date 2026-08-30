# EqualShares - TODO

*The Roll Call: fund proxy votes made readable, with receipts. Built through RapidForge
(`F:\RapidForge`) - the method home. `README.md` explains the build; this file is the live state.*

---

## RESUME HERE

**Live state as of 2026-08-29 (23:30 CDT). This block outranks every other document in this repo.**

- **LIVE at https://equalshares.pages.dev/ - rung two** (built, deployed, verified at the origin).
  Rung three is Lance using it and reporting. Two dogfood findings so far, both fixed (`df0c576`
  cold-reader intro, `cc24368` receipts land on EDGAR's rendered vote table).
- **The one open owner decision is CLOSED: stay static, $0.** Lance, 2026-08-29, on the EventFinds
  Build 002 form, verbatim: "13. C for now" (relayed by `rapidforge-79`; recorded in
  `F:/RapidForge/docs/INTERRUPTIONS.md`). The draft migration stays unapplied by his word.
- **Standard adopted 2026-08-29** on Lance's word in this session: `CLAUDE.md` points at
  `F:/RapidForge/docs/PROJECT_STANDARD.md` and declares deviations; `CHATLOG.md`,
  `PLAYBOOK_DELTA.md`, `AUDIT_LOG.md`, `REBUILD.md`, `tools/verify_claims.py`,
  `tools/verify_deploy.py` added. Measure: `python F:/RapidForge/tools/verify_standard.py`.
- **Cold-read order:** `CLAUDE.md` -> this block -> `README.md` -> `PLAYBOOK_DELTA.md` -> the spec above.
- **Standing prompt (re-arm after any session limit; Lance 2026-08-29: timers restart the previous
  prompt 60 s after the limit expires):** process unprocessed peer messages (verify in the data
  first); build Part 1 of the spec only once RapidForge has approved it; otherwise keep
  `verify_claims` and `verify_deploy` green and say "no change". Heartbeat job in this session:
  `637b15c4`, every 30 min, session-only, expires 2026-09-05.
- **Expected failures: none.** Any instrument FAIL is real from here. (`checks.py` G3 needs the
  network; `--skip-outage` marks it SKIP, which is not a pass.)

## WAITING ON LANCE

- Nothing. Section 8 of the spec lists four assumptions he can override; the build does not wait on them.

## NOW

- [ ] **Spec review by RapidForge**, then build: `docs/superpowers/specs/2026-08-29-multi-filing-and-contrast-set-design.md`.
      Part 1 = reader fixes F3-F13 (the concordance headline goes; rows are vote lots; NONE is a
      value; visible find-it-by; definitions). Part 2 = multi-filing, `series_match`, compare view, G11.
- [x] ~~**Dogfood** (rung three)~~ - redirected by Lance 2026-08-29 ("proceed considerable without me
      dogfooding"). Cold-read round one done by three peers (`docs/COLD_READ_PROTOCOL.md`); findings
      F3-F13 dispositioned in the spec. Rung three still means real users; unchanged.
- [x] ~~**Cloudflare Pages connect**~~ - DONE 2026-08-29. LIVE at https://equalshares.pages.dev/
      Root `site`, output empty (the pairing `deploy-runbook` trap 6.1 warns about - Lance checked
      the wizard against the runbook before saving). Verified at the ORIGIN with curl, then in a
      browser: CSP + nosniff + referrer-policy applied by Pages, JSON served as `application/json`,
      anti-blend holds in the served payload, receipts resolve, category drill-down 200. Zero
      console errors under the production CSP. Rung two reached.
- [x] ~~**Where does the publication database live?**~~ - CLOSED 2026-08-29, stay static ("13. C
      for now"). See RESUME HERE.
- [x] ~~**Self-catalogue sweep**~~ - sent to `rapidforge-79` 2026-08-29 23:34 CDT: `pipeline/sources.py`,
      `.github/workflows/ingest.yml`, `site/_headers`, `tools/verify_claims.py`, `tools/verify_deploy.py`
      have no `MODULE_DIRECTORY.md` row. The registry verifies and catalogues.

## BUILD QUEUE

- [ ] **More filers.** The pipeline is one config line per source. Big Three + contrast set
      (Fidelity, T. Rowe, Capital Group, a large pension) - decision 3. Each is a `SOURCES` entry;
      the IM *notice* reports enumerate a filer's fund registrants for free (DRYRUN_001 finding 4).
- [ ] **Multi-filing support** - replaces the `max_filings: 1` unstable pointer (README, deferred
      review finding 2). A trust files one N-PX per fund series; the page must say which, or show all.
- [ ] **Shadow/promotion path** for the extractor - build it the first time the extractor is
      actually rewritten (extractor-provenance 5.4; deferred review finding 1).
- [ ] **Concordance by `voteSource`** on the category table - the 85.6% / 0.0% split belongs in the
      rollup, not only in a footnote.
- [ ] **Rule 15 sweep of code comments and UI strings**, per file, on each file's next real edit
      (`checks.py`, `serve_local.py`, `export_site.py`, `site/js/*.js`). `export_site.py` is inside
      the behaviour fingerprint, so do it alongside a real change, never alone.

## INBOX (captured, not chased)

- **THE LARGER GOAL - Lance, 2026-08-28, verbatim:** *"Equalshares has a larger goal, if it can
  have enough funds to become the major voting entity in Blackrock vanguard and state street,
  equalshares could redistribute the wealth through the same processes these entities run now,
  their system would be used against them to drain them and make the playing field level for all."*
  **Lance, moments later:** *"Well if voters choose too"* - the redistribution happens only if the
  shareholders choose it. That makes the goal consent-based: EqualShares enables the choice; it
  never makes it. Captured as stated, not reworded. Two notes recorded alongside it, for Lance to weigh:
  - **It sits against locked decision 1** (`RapidForge/ProjectContext.md` section 4: *activate, not
    accumulate - no pooled fund, no custody, no token; '40 Act / Howey / money-transmitter
    exposure*). Decision 1 is the **v1 route**, not a verdict on the larger goal. Re-opening it is
    Lance's call, not the build's.
  - **The lever that already exists needs participation, not capital.** The Big Three each run
    pass-through "voting choice" programs that let fund investors direct how their shares are voted.
    An organizer of *existing* shareholders' voting rights reaches voting power without pooling
    assets or registering a fund - which is the "activate" path decision 1 chose, and is the same
    system used from inside. Verify current program terms before building on them (class B).
  The Roll Call is step one on that road either way: nobody can direct a vote they cannot see.

- **2026-08-28, Lance - system-wide comparison: a CORE CAPABILITY, not the ultimate goal.**
  The goal is transparency - show how funds voted the shares they hold, with receipts. Comparison
  via the graphs is how that transparency becomes *useful*: put many funds' Roll Calls side by side
  so a shareholder can see how *different* funds voted the *same* proposals and directors (the
  contrast-set thesis, decision 3). The instrument draws no conclusion; the reader compares.
  Layers, in order of reach:
  1. **Cross-filer comparison** of identical proposals and director elections - more `SOURCES`
     entries, same pipeline. Crosstab by `voteSource` first (today's finding).
  2. **Director-name resolution across issuers**, so one director's elections can be compared across
     the companies they serve - a data structure, not a verdict. Entity resolution already exists:
     `VisibleGov/src/lib/person-identity.js`. The free-text name parser will be rewritten -> the
     shadow path becomes necessary here.
  3. **DEF 14A enrichment** - full proposal text, proponent, outcome - correctly parked by
     DRYRUN_001; layer 3 waits on it.
  Every edge carries a receipt; the reader compares. Thesis-forward, instrument-backed (decision 4).
- Concordance semantics vary by filer convention on shareholder proposals - verify per filer
  before any cross-filer comparison is published.
- 50 multi-category records: consider counting under every category with a disclosure, once a
  second filer makes the choice matter.
