# AUDIT_LOG - EqualShares

Append-only audit trail for this repository. Read it before recommending or changing anything
substantive. Verdict vocabulary and file shape follow the standard's exemplar (Glizzness
`AUDIT_LOG.md`); dated audit *reports* may live under `docs/audits/` and are pointed at from here.

## How This File Works

- Append-only. Do not delete or rewrite prior entries; newest entry last.
- Every finding carries a verdict from exactly this set: `Open`, `Mitigated`, `Fixed`,
  `Accepted Risk`, `Obsolete`. When re-auditing, restate each prior finding with its current verdict
  and evidence.
- Cite file paths and function or gate names. Line numbers drift; if quoted, say which revision.
- When code changes in response to an audit, add a dated line under "Post-Audit Changes" naming
  the commit and which findings it addressed.
- No secrets, no raw data dumps. This repo holds none; keep it that way.

## Audit Entry Template

```markdown
## Audit YYYY-MM-DD - Short Title

### Scope
### Findings Status From Prior Audits
| Prior Finding | Status | Evidence |
| --- | --- | --- |
### Severity-Ranked Findings
#### Critical / High / Medium / Low
1. Finding title
   - Evidence:
   - Impact:
   - Trigger / proof:
   - Verdict:
### Sign-Off Position
### Post-Audit Changes
- YYYY-MM-DD: ...
```

---

## Audit 2026-08-28 - Adversarial review round, Build 001 (The Roll Call slice)

### Scope

The whole slice at commit `c9e2cb4` (pipeline, gates, site, SQL draft, README), reviewed by seven
refuters with per-finding verification (46 agents). 39 findings raised: 30 confirmed, 9 refuted.
The itemised record is the body of commit `4846c4f` (`git show -s --format=%B 4846c4f`); this entry
carries the verdicts.

### Findings Status From Prior Audits

None - first audit of this repo.

### Severity-Ranked Findings

#### Critical

1. The publication was not in the repo.
   - Evidence: `.gitignore` had an unanchored `data/` pattern that also matched `site/data/`, while
     the same file's first line claimed `site/data` was committed. CI regenerated the files before
     every check, so no gate could see it.
   - Impact: every deploy would have published an empty `site/data/`; every check green.
   - Trigger / proof: `git check-ignore -q site/data/meta.json` returned 0 at `c9e2cb4`.
   - Verdict: **Fixed** (`4846c4f`: `/data/` anchored; gate G10 `g10_publication_committed` in
     `pipeline/checks.py` asks git directly). Re-checkable: `python tools/verify_claims.py` C8.

#### High

2. A terminal retirement of the current filing could read as a quiet day (trap 6.1 re-entering
   through the terminal table).
   - Verdict: **Fixed** (`listings` table persists the source-listed expected set per run; gate G9
     `g9_listing_coverage` requires the newest listed filing to be extracted).
3. The export step computed every published number but sat outside the behaviour fingerprint.
   - Verdict: **Fixed** (`export_site.py` added to `FINGERPRINT_FILES` in `pipeline/extract.py`).
4. The rollup's OTHER column conflated Unparseable and Absent and contradicted the totals.
   - Verdict: **Fixed** (separate columns; tri-valued honesty on the page).
5. No shadow/promotion path for the extractor (extractor-provenance section 5.4).
   - Verdict: **Accepted Risk** - deferred until the extractor is first rewritten; the raw store +
     UPSERT keeps any bad re-parse recoverable. Recorded in `README.md` Known limitations (1).
6. `max_filings: 1` over a multi-series trust is an unstable pointer.
   - Verdict: **Accepted Risk** - the page always says which series it shows; fix lands with
     multi-filing support. Recorded in `README.md` Known limitations (2).

#### Medium and Low

7-30. The remaining confirmed findings (identity mismatch now fails the source; N-PX/A accepted;
   skip counts clear on success; CRLF-stable fingerprint; perturb env var refuses a writing run;
   per-filing failures collect and exit 1; category files cross-check the rollup count; last click
   wins; vote-document link wording; meta shape guard; footer claim; `serve_local.py` parses
   `_headers`; SQL draft gains `vote_source`/`categories_all`, lockstep bucketing, tri-split
   counters, a rows-not-status probe; README gate table G1-G10).
   - Verdict: **Fixed** (`4846c4f`), each with the gate or file named in the commit body.

31-39. Nine findings refuted with evidence - not findings. Listed only so the count reconciles.

### Sign-Off Position

All ten gates pass at `4846c4f` (fingerprint `01db0923e67186ec`). Two Accepted Risks are recorded
in the README with their triggers. No Open findings.

### Post-Audit Changes

- 2026-08-28: `df0c576` - dogfood finding 1 (a cold reader could not tell what the page was). Not
  an audit finding; the class the gates cannot see. Three sentences added, no numbers typed.
- 2026-08-28: `cc24368` - dogfood finding 2 (receipts landed on the index page, not the row; EDGAR
  `index.json` omits documents the index page lists). Fingerprint rotated to `b13f9c5877e362ce`.
- 2026-08-29: `acbd2bb` - live at https://equalshares.pages.dev/, verified at the origin. Host
  semantics: an unknown path returns 200, not 404 (no `404.html`). Verdict on that:
  **Accepted Risk** - cosmetic on a single-page site with no deep links; recorded, not fixed.
- 2026-08-29: the cross-project standard adopted (`CLAUDE.md` Deviations). `tools/verify_claims.py`
  and `tools/verify_deploy.py` added as the re-runnable evidence for the claims above.

## Audit 2026-08-29 - Cold-read round one (four independent readers)

### Scope

The live page at `acbd2bb`, read as strangers by four peer sessions (Glizzness, LinkedUmp,
VisibleGov, Phoenix), each in a real browser with one category opened, per
`docs/COLD_READ_PROTOCOL.md`. Reports in `CHATLOG.md`; every finding checked in
`data/rollcall.db` and the raw XML before a disposition (spec section 2).

### Findings Status From Prior Audits

| Prior Finding | Status | Evidence |
| --- | --- | --- |
| 2026-08-28 #5 shadow/promotion path | Accepted Risk (unchanged) | README Known limitations (1) |
| 2026-08-28 #6 `max_filings: 1` unstable pointer | Accepted Risk, fix designed | spec Part 2, `series_match` |

### Severity-Ranked Findings

#### High

- F3 A row was never defined; the same proposal appears several times with different votes.
  Cause: an N-PX block holds 1-10 lots, a proposal spans 1-5 blocks; one series throughout.
  Verdict: **Fixed** (2026-08-30: `proposal_no` / `lot_index` / `lots_in_proposal` per record,
  lots grouped in the drill-down, totals hold records / lots / proposals apart; G7 recomputes).
- F4 "% with mgmt recommendation" read backwards on shareholder-proposal categories. Cause: the
  field is per lot and tracks the lot (0 of 1,433 shareholder lots agree; varies inside ISSUER
  items too). Verdict: **Fixed** (headline dropped; "% FOR" split by `voteSource` with numerator
  and denominator; `meta.mgmt_rec_semantics` computed per filing; G8 forbids
  `with_mgmt|concordance|comparable|blend` keys anywhere).
- F6 Every row's receipt is the same filing-level URL. Verdict: **Fixed** as far as the source
  allows (N-PX has no per-row anchor): the row's ordinal, proposal number and search terms are
  visible beside the link; the How-to-read block says there is one receipt per filing.

#### Medium

- F5 "Comparable" excluded 10 records silently (raw `NONE` normalised to NULL). Verdict:
  **Fixed** (`NONE` is a kept value; "Comparable" retired).
- F7 Truncated SHA; unexplained engine run. Verdict: **Fixed** (full hash; definitions inline).
- F8 Undefined terms. Verdict: **Fixed** (How-to-read block; no numbers in it).
- F14 "88 unparseable" and "1 absent" with no way to see which. Verdict: **Fixed** (field-state
  filter in the drill-down: unparseable / absent / zero-share / split).

#### Low

- F9 Intro overstated ("every mutual fund ... every meeting"). Verdict: **Fixed** (reworded).
- F10 Pager not found. Verdict: **Fixed** (pager hidden when one page, shown top and bottom with
  a ruled top; status names the page).
- F11 Category placement looked like the site's choice. Verdict: **Fixed** (labelled as filed).
- F12 Zero-share lots unexplained. Verdict: **Accepted as filed** with a definition line and a
  filter; 2,845 lots.
- F13 The XSL-viewer URL looked constructed. Verdict: **No change needed** (stored at ingest from
  the filing index page); the footer and provenance box now say where it came from.

### Sign-Off Position

Part 1 of `docs/superpowers/specs/2026-08-29-multi-filing-and-contrast-set-design.md` built
2026-08-30: ten gates pass (G7 200 checks, G8 over 14 artifacts), `tools/verify_claims.py` passes,
rendered under the production CSP with zero console messages. Engine run `2e9a5a7bbe8a2d86`.
Round two of the protocol is requested on the corrected page.

### Post-Audit Changes

- 2026-08-30: Part 1 shipped (this entry). The next entry is round two's report.

## Audit 2026-08-30 - Cold-read round two (five readers) and the owner's own read

### Scope

The Part 1 page at `f30eb0c`, read by Glizzness, league, LinkedUmp, VisibleGov and Phoenix per
`docs/COLD_READ_PROTOCOL.md` (four in a real browser; league from the served files; VisibleGov
could not open EDGAR's table: 403 to its fetch), plus Lance's own report of the clipped table.
Every finding checked in `data/rollcall.db` and the raw before a disposition (CHATLOG, spec
section 12). RapidForge re-ran the data claims independently and caught a mixed-key report.

### Findings Status From Prior Audits

| Prior Finding | Status | Evidence |
| --- | --- | --- |
| Round one F3-F14 | Fixed (unchanged), except as re-opened below | AUDIT 2026-08-29 |

### Severity-Ranked Findings

#### High

- **Owner:** the drill-down table clipped at "Mgmt rec" with no visible scrollbar at laptop width.
  Cause: 1,654 px of table in an 1,110 px container; overlay scrollbars invisible until touched.
  Verdict: **Fixed** (`218d425`, verified at the origin 00:20 CDT; PLAYBOOK_DELTA Lesson 8).
- R3 One ballot item under two proposal numbers (Disney, Coca-Cola, Constellation, Medtronic).
  Cause: the key used text as filed; the filing spells one company and one item several ways.
  Verdict: **Fixed** (2026-08-30: one key function normalises case, spacing and trailing
  punctuation; 10,523 -> 8,906 proposals; Medtronic is one proposal of seven lots).
- R2 Lots of one proposal missing from a category list ("2 of 3", no "1 of 3"); Proposals column
  summed above the total. Cause: 495 proposals (under the one key) have lots filed under more
  than one category. Verdict: **Fixed** (each record names the other categories; a filter lists
  them; the column note states the rule and the counts; `totals.proposals_in_multiple_categories`).
- R4 Zero-share lots inside "FOR of voted lots". Verdict: **Fixed** (denominator = lots with a
  readable vote and shares above zero; zero-share lots published per cell and per category).
- R5 The 50% threshold was an assumption presented as the test; a perfect zero looked like a
  vocabulary mismatch (league, retracted after the crosstab). Verdict: **Fixed** (threshold
  removed; the test is the count of proposals carrying more than one recommendation value across
  their own lots, 4,594 of 8,904, with an example and the vote-by-recommendation crosstab
  published; the agreement rate stays as evidence).
- **Mixed-key report** (RapidForge): 198 and 5,022 were as-filed-key numbers quoted beside a
  normalised-key 8,990. Verdict: **Fixed** (every count derives from one `proposal_no`; the
  published numbers are 495 and 4,594; PLAYBOOK_DELTA Lesson 9).

#### Medium

- R1 heading vs pager under a filter: **Fixed** (heading follows the filter).
- R6 typed constants under a "none are typed" claim: **Fixed** (`meta.config`, a Configuration
  row, the claim narrowed; one constant remains).
- R7 "Mgmt rec FOR" on a row read as the board's wish: **Fixed** (column header and cell titles
  carry the filing's verdict).
- R10 no proposer filter: **Fixed** (management / shareholder / elsewhere filters).

#### Low

- R8 whose numbering; one link per lot: **Fixed** as far as the source allows (labelled this
  page's; EDGAR has no per-lot anchor). R9 wording and definitions ("-", ABSTAIN as filed,
  fractional shares, engine id changes, companies count 318 by CUSIP in 622 spellings):
  **Fixed**. R11 glossary length and the "four strangers" sentence: **Fixed** (three terms first,
  the rest collapsed; the correction note moved beside the provenance claim). R12 whose numbers:
  **Fixed** (a subject line under the fund name).

### Sign-Off Position

Part 1.1 built 2026-08-30: ten gates pass (G7 233 checks), `tools/verify_claims.py` passes,
rendered under the production CSP via serve_local.py in Playwright with zero console messages: DEI drill-down with the elsewhere filter (21 of 23), the verdict in the Mgmt rec header, lot notes naming the other categories, the table fitting its container. Engine run `e3b050bc2353357b`. Round three of the protocol is the next check.

### Post-Audit Changes

- 2026-08-30: Part 1.1 shipped (this entry).

## Audit 2026-08-30 - Cold-read round three (five readers, all rendered)

### Scope

The Part 1.1 page at `0041014`, read by Glizzness (929 px), LinkedUmp (914 px), Phoenix
(929 px), league (1280 px, third read), VisibleGov (1920 px). Every finding checked in the store
before a disposition (CHATLOG). Fixed as Part 1.2.

### Severity-Ranked Findings

#### High

- The headline category table was 2,273 px wide at 929 px and carried no scroll hint: three
  columns visible, the vote columns and both "% FOR" columns off-screen (three readers). Cause:
  no-wrap header notes of 390-418 px each. Verdict: **Fixed** (headers wrap, notes drop to their
  own line, cells tighten; a worded hint above the table whenever it still overflows).
- The recommendation test's example was a say-on-pay FREQUENCY item, the one proposal type whose
  ballot vocabulary is not FOR/AGAINST (league). Verdict: **Fixed** (the example rule is now: a
  category with no unparseable votes, then the most lots; American Express, 8 lots; G7 asserts the
  pick; the link opens exactly those lots).
- Two footnotes read as contradicting ("counted in each" vs "nothing is counted twice"; records vs
  lots) (VisibleGov, league). Verdict: **Fixed** (one explanation: proposals are counted per
  category, lots never twice; the tag note reworded as lots).

#### Medium

- Per-cell zero-share counts summed to 2,836 against 2,845 (LinkedUmp). Cause: 9 zero-share lots
  have no readable vote. Verdict: **Fixed** (both halves published and stated; the Lots column
  shows each category's zero-share count in brackets).
- 8,906 vs 8,904 (league, VisibleGov). Cause: 2 proposals carry no recommendation on any lot.
  Verdict: **Fixed** (stated in the test sentence; `proposals_without_recommendation` published).
- 495 vs 510 (Phoenix). Verdict: **Fixed** (`extra_category_entries` published and explained:
  some proposals sit in three or four categories).
- Medtronic's lots arrived 4-7 before 1-3 (Phoenix). Cause: the sort compared issuer names as
  filed. Verdict: **Fixed** (sort compares names case-insensitively; lockstep in G7).
- Two FOR numbers per row unexplained (league). Verdict: **Fixed** (the For header says "all
  lots"; each cell names its zero-share FOR lots; the footnote says why the column runs ahead).
- "0% (0 of 1)" printed as a percentage on a thin cell (league). Verdict: **Fixed** (thin cells
  show counts only).
- Lists wanted behind 622 spellings and 4,594 mixed proposals; no link to the data file
  (Glizzness, LinkedUmp). Verdict: **Fixed** (`issuers.json` with a collapsed on-demand list;
  a "mixed recommendation" filter per category with per-category counts; a link to meta.json).
- The lot cell read as one run-on string; the Mgmt rec header was a sentence (LinkedUmp).
  Verdict: **Fixed** (two facts separated; header shortened).
- "Show all 21,846 records" beside Lots 21,845 (VisibleGov). Verdict: **Fixed** (the row's label
  names lots).
- Per-category proposal counts changed between visits with nothing on the page reconciling the
  runs (Glizzness, VisibleGov). Verdict: **Accepted with a statement** (the heading says "by this
  page's rule"; the rule is in the glossary; the engine run changes with it; the page carries no
  history by design).

#### Low

- No totals row (league). Verdict: **Accepted Risk, stated** (a blended row would mostly measure
  director elections; the footnote says so and points at the provenance box).
- The three hashes are traceable but not usable (VisibleGov). Verdict: **Accepted** (they are for
  the reader who recomputes; the SHA-256 is the actionable one).
- The seven-lot pattern on shareholder proposals is unexplained by the filing (LinkedUmp).
  Verdict: **Accepted as filed** (the glossary says the filing does not say what divides lots).

### Sign-Off Position

Part 1.2 built 2026-08-30: ten gates pass (G7 251 checks), `tools/verify_claims.py` passes,
rendered under the production CSP via serve_local.py in Playwright with zero console messages: the headline table equals its container at 1366 px and shows the worded hint at 929 px (1,021 px in 857); the example link opens all 7 Medtronic lots in lot order; the spellings list loads 299 companies on demand. Engine run `e3b050bc2353357b`. Round four is a different question (RapidForge): which number
would a reader quote, and is it the one we would want quoted - asked of readers who have not seen
the page.

### Post-Audit Changes

- 2026-08-30: Part 1.2 shipped (this entry).

### Measured, not felt (2026-08-30)

Across three cold-read rounds, five instrumented readers found the confusions (fourteen in round
one, twelve in round two, fourteen in round three) and none of the two defects that mattered most
to a reader in front of the page: the clipped drill-down table (Lance, an hour after a
console-clean render passed) and, before that, the cold-reader intro and the receipts landing on a
document list (Lance, dogfood findings 1 and 2). Round four therefore goes to the owner, one
sentence, no framing. Recorded so the protocol's limit is a fact in this log, not a memory.
