# EqualShares - TODO

*The Roll Call: fund proxy votes made readable, with receipts. Built through RapidForge
(`F:\RapidForge`) - the method home. `README.md` explains the build; this file is the live state.*

---

## RESUME HERE

**Live state as of 2026-09-03 21:27 CDT (from `date` on this machine). This block outranks every other document in this repo.**

- **LIVE at https://equalshares.pages.dev/ - rung two, eight fund series on one page,** verified at the
  origin byte for byte (`tools/verify_deploy.py`, 44 markers). Rung three (a real reader) has not been
  claimed; five peer sessions read it in three cold-read rounds and Lance found the two defects that
  mattered (AUDIT_LOG 2026-08-30, "Measured, not felt").
- **What is on the page:** one page per fund series from its N-PX filing (picker in the header,
  `#filing=<accession>&category=<slug>` in the address bar) and a compare section with the same SEC
  category across all eight: Vanguard 500, Vanguard Morningstar Value, iShares Core S&P 500, SPDR
  Portfolio S&P 500, Fidelity 500 Index, T. Rowe Price Equity Index 500, Schwab S&P 500 Index, Growth
  Fund of America (Capital Group, active, the contrast). Every cell is that filing's own number;
  nothing is added across filings or categories (gate G8).
- **2026-09-03, two instrument defects of the same family, both fixed.** (a) The
  `managementRecommendation` test could not fail for a filing whose proposals report one lot each -
  a one-lot proposal cannot contradict itself - so Fidelity and T. Rowe were cleared on a maximum
  achievable score of 1 against a floor of 5, and the page printed it as a finding. The testable
  population is now computed, published as `proposals_testable`, and the verdict below the floor is
  `insufficient`; no filing now claims a clearance. (b) Gate G4 had printed PASS since day one over
  an empty `terminal` table. A gate whose eligible population is empty now returns **N/A - did not
  run**, and the summary refuses the all-pass headline. Exit code unchanged: not running is not
  failing. The general form, which EventFinds then found four of its ten gates in: a check whose
  failure condition needs a population must publish that population and say "did not run" rather
  than "passed" when it is too small.
- **Seven locked rules, not five** (`CLAUDE.md`; two added 2026-08-30 on Lance's word): the five
  originals plus **one identity function** (`assign_proposals` decides what a proposal is and every
  published count derives from its `proposal_no`) and **no headline rests on a filed field until a
  computed check on that filer passes** (G8 refuses `headline_allowed` unless the verdict is
  `board-view`; Fidelity and T. Rowe pass, the other six do not).
- **How it is built (the rules that hold):** a row is a vote lot; the proposal key lives in ONE
  function (`pipeline/extract.py` `assign_proposals`: case, spacing and trailing punctuation ignored)
  and every count derives from it; `managementRecommendation` is judged per filing by a computed,
  threshold-free test (proposals whose own lots carry more than one value) published in each
  `meta.json` as `mgmt_rec_semantics` and gated: Fidelity and T. Rowe are a board's view, the other
  six are not; no page renders a concordance headline. Sources are pinned to a fund by SEC series id
  (`pipeline/sources.py`; ids from https://www.sec.gov/files/company_tickers_mf.json), extraction is
  scoped to the pinned series, a no-match FAILS the source. Layout: `site/data/index.json`,
  `filings/<accession>/`, `compare.json`. Eleven gates (`pipeline/checks.py`; G7 2,041 checks, G11
  index-coverage); `tools/verify_claims.py` 8/8; `tools/verify_deploy.py`.
- **Run it:** `python pipeline/run_ingest.py` (EDGAR, series walks, ~600 MB raw) -> `extract.py` ->
  `export_site.py` -> `checks.py` -> `ROLLCALL_PORT=8766 python pipeline/serve_local.py` (8765 may be
  held by another project). Push to master deploys; then `python tools/verify_deploy.py`.
- **Settled with the registry 2026-08-30, so nobody re-opens it:** this repo's rule-3 scoping was
  adopted as PROJECT_STANDARD 3a (strike through where the READER needs the correction visible -
  README does, one entry - and rewrite the rule file to current fact); the stale-deviation finding
  landed as an extension of standard rule 8 rather than a new rule; the one-identity-function rule
  is filed LOCAL, not federal; and standard rule 9 is declared UNRESOLVED here - eleven gates read a
  626 MB gitignored store, so a stranger cannot re-run them from a clone without ingesting first.
- **Next slice, when someone picks it up:** (a) a cold read of the compare view by a reader who has
  not seen the page (`docs/COLD_READ_PROTOCOL.md`); (b) the shadow/promotion path, only when the
  extractor is actually rewritten; (c) proposal-level cross-filer joins (spec section 3, out of scope
  until the description-text match rate across filers is measured - the data is on disk now).
- **Where the why lives:** `CHATLOG.md` (every exchange, clock-timed), the spec at
  `docs/superpowers/specs/2026-08-29-multi-filing-and-contrast-set-design.md` (sections 1-15),
  `AUDIT_LOG.md` (three rounds with verdicts), `PLAYBOOK_DELTA.md` (Lessons 1-10). The registry's
  rows about this repo were audited and corrected at RapidForge `a4695a5`.
- **Standing prompt (re-arm after any session limit; Lance 2026-08-29):** process unprocessed peer
  messages (verify in the data first); keep `verify_claims` and `verify_deploy` green; say "no change"
  when nothing moved. The heartbeat cron dies with the session; re-create it (every 30 min, idle only).
- **Time rule (Lance 2026-08-30):** every time written here comes from `date` on this machine, with
  its zone; commit times from `git log --date=iso`; a zoneless time in a message is unknown.
- **Expected failures: none.** Any instrument FAIL is real from here.

## WAITING ON LANCE

- **Round four, thirty seconds, one sentence and nothing else:** open https://equalshares.pages.dev/
  and *name the single number here you would repeat to someone else.* (RapidForge's question; the
  readers who found the confusions are spent, and you are the one person who will ever actually
  repeat a number from this page. Also in RapidForge's morning handoff, worded the same, so you meet
  it once.)
- Section 8 of the spec lists four assumptions you can override; the build does not wait on them.

## NOW

- [x] ~~**Spec review by RapidForge**~~ - approved 2026-08-30 with four notes, all applied (spec section 11).
- [x] ~~**Part 1 - reader fixes F3-F14**~~ - BUILT 2026-08-30: rows are vote lots with published grouping;
      the concordance headline is gone; "% FOR" split by proposer with denominators;
      `mgmt_rec_semantics` stored and gated; How-to-read block; visible finders; field-state filter.
      Ten gates, claims 8/8, zero console messages under the production CSP.
- [x] ~~**Cold-read round two**~~ - five reports plus Lance's own (the clipped table, fixed first,
      `218d425`). All dispositioned in spec section 12 and BUILT as Part 1.1 on 2026-08-30: one proposal
      key (8,906), zero-share lots out of the denominators, the threshold-free recommendation test,
      `meta.config`, the glossary cut to three terms. AUDIT_LOG 2026-08-30.
- [x] ~~**Cold-read round three**~~ - five rendered reads; dispositioned (AUDIT_LOG 2026-08-30 round
      three) and BUILT as Part 1.2 on 2026-08-30: the headline table fits or says it scrolls; a clean
      example for the recommendation test; every gap a reader found between two numbers now has both
      numbers named.
- [ ] **Round four** is Lance's (WAITING ON LANCE above); held there on RapidForge's call, exclusions kept.
- [ ] **Cold-read of the compare view** (a new page shape) once readers exist who have not seen it.
- [x] ~~**Part 2 - multi-filing**~~ - BUILT 2026-08-30 (spec section 14): four filings pinned by series id,
      picker + routing + compare view, G11, eleven gates, verified at the origin.
- [ ] **Part 2 - multi-filing**: `series_match` per source, three Big Three sources (iShares Trust
      0001100663, SPDR SERIES TRUST 0001064642, Vanguard 500 Index series), `site/data/index.json`
      + per-filing dirs + `compare.json`, gate G11 index-coverage, picker and compare view.
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

- [x] ~~**Big Three**~~ - DONE 2026-08-30 (Part 2): Vanguard 500, iShares Core S&P 500, SPDR Portfolio
      S&P 500, each one `SOURCES` entry pinned by series id.
- [x] ~~**Contrast set**~~ - DONE 2026-08-30 (Part 2.1): Fidelity 500 Index, T. Rowe Price Equity Index
      500, Schwab S&P 500 Index, Growth Fund of America (active, Capital Group). The pension half of
      decision 3 has no N-PX source (pensions file no vote records) - recorded, not built.
- [x] ~~**Multi-filing support**~~ - DONE 2026-08-30 (Part 2). Pinned by series id; the page lists every
      filing and compares the same category across them.
- [ ] **Shadow/promotion path** for the extractor - build it the first time the extractor is
      actually rewritten (extractor-provenance 5.4; deferred review finding 1).
- [x] ~~**Concordance by `voteSource`**~~ - superseded 2026-08-30: the concordance headline is gone
      (Part 1) and "% FOR" is split by `voteSource` in every category cell and in the compare view.
- [ ] **Rule 15 sweep of code comments and UI strings**, per file, on each file's next real edit
      (`checks.py`, `serve_local.py`, `export_site.py`, `site/js/*.js`). `export_site.py` is inside
      the behaviour fingerprint, so do it alongside a real change, never alone.

## INBOX (captured, not chased)

- **The findings and the frame now live in `docs/FINDINGS.md`** (2026-09-06), not in this inbox:
  Fidelity voted FOR 0 of 149 social and environmental shareholder lots in BOTH directions (116
  proponent-side and 9 ESG-critical, the latter quoted verbatim), while voting FOR 34 of 340
  shareholder items overall - so "blanket no to shareholder voice" is false and checkable-wrong.
  The engine of the story is the contrast: Fidelity 0% vs iShares 40.3% on climate, over 490
  companies the two funds both hold. Nothing published yet; re-derive on the live page first.

- **2026-09-03, a freshness gap no gate can see.** G9 compares the store against the LAST INGEST
  RUN's `listings`, so it can never notice that EDGAR lists a newer filing than the one published.
  N-PX is annual: when these eight filers file again, the site's implicit "this is the fund's
  latest filing" goes false with the calendar, nothing in the repo changes, and eleven gates stay
  green. A freshness check must reach the network, so it belongs beside `verify_deploy` rather
  than inside `checks.py`. Found by rapidforge-d8's prompt that a gate which only warns is not a
  gate; verified here before recording.

- **2026-08-30, from peers on reconnect, take or leave:** (EventFinds) write the export's JSON pair
  via tmp + os.replace so a failed second write cannot leave a mismatched set, and construct the page
  inside the init try so a missing script reaches the error box rather than a blank 200 (here: a
  failing ES-module import of data.js/receipts.js would blank the page before main() runs).
  (Glizzness) verify_deploy canonical is at sha 0ffcee70 with a NO-LOCAL verdict for a marker
  missing locally and edge-rewrite reversal (email obfuscation, managed robots.txt); markers derived
  from the publish tree, which this repo already does from index.json.

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
