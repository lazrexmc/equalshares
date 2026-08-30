# Multi-filing and the contrast set - design

**Date:** 2026-08-29 (late, CDT). **Status:** approved by RapidForge 2026-08-30 with four notes (section 11); Part 1 BUILT 2026-08-30; Part 2 next. Originally: DRAFT for RapidForge review before any code
(the method: specs first, gameplan to the registry, build on its reply). Owner assumptions are in
section 8 for Lance to override; nothing here needs his hands to build.

## 1. Why now

Lance, 2026-08-29, verbatim: *"I feel like there's enough peers now that this project should be
able to proceed considerable without me dogfooding stuff I don't really know much about."*

So the build queue proceeds, and the cold-reader test moved to the peer sessions. Three reports
came back within the hour (Glizzness, LinkedUmp, VisibleGov; each rendered the live page in a real
browser and opened a category). They converge, and they change the order of work: the current page
has reader-facing defects that would carry straight into a multi-filing page. Part 1 fixes them;
Part 2 is the queue item this spec was opened for (README deferred finding 2, BUILD QUEUE items 1-2).

## 2. What the cold reads found, and what the data says

Every finding was checked against `data/rollcall.db` and the raw XML before it got a disposition.
Two of the readers' diagnoses were wrong about the cause and right about the symptom; both are
recorded as findings anyway (the symptom is what a stranger sees).

| # | Finding (readers) | What the data says | Disposition |
|---|---|---|---|
| F3 | "Several series merged into one list": the same Cisco / Coca-Cola / Disney proposal appears 2-4 times with different share counts and different votes; "one fund, one year" looks false | Every row carries the same `voteSeries` (`S000002840`); it IS one fund. The filing has 21,474 `<proxyTable>` blocks and 29,890 `<voteRecord>` lots, each lot with its own `howVoted`, `sharesVoted` and `managementRecommendation`; one block (STERIS plc, a withdrawn resolution) has zero lots and is the page's one absent row, which is why the page says 29,891. Grouping blocks by (issuer, CUSIP, meeting, description, source) gives 10,523 distinct proposals: a proposal spans 1-5 blocks (5,700 span two) and a block holds 1-10 lots. A row is a **vote lot**, not a proposal (Phoenix counted the raw independently and matched) | Say so. Define "record = one lot"; count proposals and lots separately everywhere; group lots under their proposal in the drill-down. The split lots are themselves a finding worth showing: they are the fund voting blocks of its shares differently, which is what a pass-through voting program looks like in the filing (TODO inbox, "the lever that already exists") |
| F4 | "% with mgmt recommendation" is read backwards: ENVIRONMENT, HUMAN RIGHTS, DEI show 0%, and a stranger reads "opposed management every time" when the rows show the fund voting AGAINST shareholder proposals | `managementRecommendation` sits inside each lot and tracks the lot: Coca-Cola director election, lots ABSTAIN/AGAINST/FOR carry rec AGAINST/AGAINST/FOR - a board does not recommend AGAINST its own nominee. On SECURITY HOLDER items agreement is 0 of 1,433; on ISSUER items 24,270 of 28,359, and it varies inside ISSUER items too (Medtronic's auditor ratification: seven lots, recs FOR/FOR/AGAINST/AGAINST/AGAINST/FOR/FOR, tracking each lot's vote). The field does not mean "the board's recommendation" in this filing, and the current footnote's caveat is too narrow: it names shareholder items only | **Drop the concordance headline.** No statistic derived from `managementRecommendation` is published as a headline for any filer until that filer's field semantics are checked (the check: agreement rate on SECURITY HOLDER items; a field that is the board's view cannot be 0%). Replace with "% FOR" split by `voteSource` (management items / shareholder items), each with n and the thin flag. The as-filed recommendation stays visible in the drill-down rows, labelled as filed |
| F5 | "Comparable" is undefined and excludes 10 records with no explanation (CORPORATE GOVERNANCE 1,330 vs 1,322; SHAREHOLDER RIGHTS 168 vs 166) | The 10 have `managementRecommendation` = `NONE` in the raw, normalised to NULL. `NONE` is an extracted value meaning "no recommendation", not absent-in-source; conflating them broke the tri-valued rule | Keep `NONE` as a normalised value. "Comparable" retires with the concordance column |
| F6 | Every row's receipt is the same URL - the 17.7 MB rendered table; "a receipt for every row" is one receipt for all rows | True. N-PX has no per-record anchor or identifier; the rendered view is the closest EDGAR gets | Say it plainly: one receipt per filing, and each row tells you where to look. Show the row's ordinal in the filing (`record 12,345 of 29,891`) and its proposal number, plus the find-it-by text (issuer, CUSIP, meeting date) **visibly**, not only in a title attribute (VisibleGov's "Roll call 283" pattern) |
| F7 | "Raw SHA-256 2299061d3fe3..." is truncated and unverifiable; "Engine run b13f9c5877e362ce" links to nothing and is unexplained | Both are stored in full in `meta.json` | Full hash in a copyable code element; one-line definitions beside both |
| F8 | Undefined terms: Absent in source, Unparseable, Withhold vs Against, the proxy year (July-June never stated), who EqualShares is, whether "% with mgmt" means agreed | All definable from the data and the SEC form | A "How to read this" block, one place, every term. Computed numbers stay computed; the block contains no numbers |
| F9 | Intro overstates: "Every mutual fund votes the shares it holds ... at every company meeting, every year" (bond and money-market funds hold no voting shares) | Correct | Reword: funds that hold voting shares vote them |
| F10 | "Show all 266 records" rendered 100 rows with no visible way to the rest | The pager exists (`PAGE_SIZE = 100`, prev/next below the table); the reader did not find it | Pager above the table as well as below; page status in the heading |
| F11 | Category placement (a Cisco DEI item under ENVIRONMENT OR CLIMATE) cannot be told apart from the site's own choice | Categories are `categoryType` as filed; multi-category records are counted under their first | Label: "SEC category, as filed by the fund" |
| F12 | Lots of 0 shares, unexplained | 2,845 lots report `sharesVoted` = 0 | Shown as filed, with a definition line: a zero lot is the fund reporting that a voting block held no shares at that meeting |
| F14 | "88 unparseable how-voted values" and "1 absent in source": nothing says which records | 88 lots with raw `1.0`/`2.0`/`3.0`/`ONE YEAR` (say-on-pay frequency answers) and the one zero-lot STERIS block | A field-state filter in the drill-down (all / unparseable / absent) so every count on the category table is a list a reader can open |
| F13 | The row link's `xslNPX-INFO-TABLE_X01/proxytable.xml` path looks constructed | It is stored at ingest from the filing index page (`cc24368`), never built at render time | No change to the mechanism; the receipts note names where the URL came from |

## 3. Scope

- **Part 1 - reader fixes** on the current page (F3-F14). Ships first, on its own commit, so the
  second cold-read round reads a corrected page before Part 2 changes its shape.
- **Part 2 - multi-filing**: the site shows every filing in the store, a reader picks one by
  identity (accession), and a compare view puts the same category side by side across filings.
  Three sources: the Big Three, each through its S&P 500 index fund.
- **Out of scope**, with the trigger that re-opens each: the proposal-level cross-filer join
  ("how did each fund vote on *this* proposal") waits until two filers' data are on disk and the
  description-text match rate is measured; the contrast set (Fidelity, T. Rowe, Capital Group, a
  pension) waits until the Big Three run end to end (DRYRUN_001 open question 2, decided here as
  "after"); DEF 14A enrichment stays parked; the Supabase path stays drafted and unapplied.

## 4. Part 1 design

**Extractor (`pipeline/extract.py`).** `NONE` becomes a normalised value of `mgmt_rec` (enum
`{FOR, AGAINST, ABSTAIN, WITHHOLD, NONE}`); the raw is kept as now. A `proposal_key` (accession,
issuer_name, cusip, meeting_date, vote_description, vote_source) and `lot_index` / `lots_in_proposal`
are computed per row. Behaviour change, so `engine_run_id` rotates and the store is re-extracted;
the rule-15 sweep of `extract.py` and `export_site.py` rides in the same commit (PLAYBOOK_DELTA
Lesson 5).

**Exporter (`pipeline/export_site.py`).** Per category: `n_lots`, `n_proposals`, the vote
distribution as now (FOR / AGAINST / ABSTAIN / WITHHOLD / UNPARSEABLE / ABSENT), and
`by_source: {ISSUER: {n_lots, n_proposals, for_lots, for_pct, thin}, SECURITY_HOLDER: {...}}`.
Removed: `with_mgmt`, `with_mgmt_pct`, `n_comparable`. Per record: `ordinal` (the row's position
in the filing), `proposal_no`, `lot_index`, `lots_in_proposal`, `mgmt_rec` as filed. `meta.json`
gains `filing.series_id` (from `voteSeries`) and `totals.proposals`.

**Gates (`pipeline/checks.py`).** G7 recomputes the new fields. G8 additionally fails on any key
matching `with_mgmt*` or `concordance*` anywhere in the export, and on any `by_source` block that
carries a blended number. Gate count stays ten; `tools/verify_claims.py` C1 keeps the README table
honest.

**Site (`site/index.html`, `site/js/rollcall.js`).** The "How to read this" block (F8, F9, F11,
F12); category table columns become Lots, Proposals, FOR / AGAINST / ABSTAIN / WITHHOLD /
Unparseable / Absent, "% FOR on management items (n)", "% FOR on shareholder items (n)", thin flags
per cell; drill-down groups lots under their proposal with the ordinal and the visible find-it-by
line (F6); pager above and below (F10); full SHA and definitions in the provenance box (F7). The
intro's "one fund, one year" stays, now true by definition: one series, one proxy year, with the
series named next to the trust.

**README / AUDIT_LOG.** Gate table unchanged in count; AUDIT_LOG "Post-Audit Changes" gets the
dogfood round with F3-F13 and their verdicts.

## 5. Part 2 design

**Sources (`pipeline/sources.py`).** A `series_match` field per source selects one filing among a
registrant's per-series N-PX filings by the series name captured from the filing index page
(`cc24368`). If no listed filing's series matches, the source **fails**; it never falls back to
"newest". This retires the unstable pointer (README deferred finding 2) by pinning to an identity,
not to recency.

| Source id | Registrant (verified on EDGAR 2026-08-29) | `series_match` | Latest N-PX |
|---|---|---|---|
| `npx:vanguard-index-funds` | VANGUARD INDEX FUNDS, CIK 0000036405 (108 per-series filings, 2026-08-27) | `Vanguard 500 Index Fund` | period 2026-06-30 |
| `npx:ishares-trust` | iSHARES TRUST, CIK 0001100663 (7 filings, 2026-08-28) | `iShares Core S&P 500 ETF` | period 2026-06-30 |
| `npx:spdr-series-trust` | SPDR SERIES TRUST, CIK 0001064642 (8 filings, 2026-08-14) | `SPDR Portfolio S&P 500 ETF` | period 2026-06-30 |

Not SPDR S&P 500 ETF Trust (CIK 0000884394): a unit investment trust whose last N-PX is from 2004.
The exact series strings are confirmed against each registrant's filing index pages at ingest; the
identity check fails the source on a mismatch, loudly.

**Store.** No schema change. `filings` already keys on accession; the current Morningstar Value
Index filing stays (UPSERT, never delete) and remains visible in the index - four filings, honest.

**Export layout.** `site/data/index.json` lists every filing in the store (`accession`, `cik`,
`filer_name`, `series_name`, `series_id`, `period_of_report`, `filed_at`, `engine_run_id`, `dir`),
ordered by filer name then series name, never by recency. `site/data/filings/<accession>/`
holds `meta.json`, `rollup.json`, `category/<slug>.json` in the Part 1 shape. `site/data/compare.json`
holds `categories[]`, each with `filings[]` of per-category cells (`n_lots`, `n_proposals`, the
distribution, `by_source`, `thin`). No per-filing total, no cross-category number, no cross-filing
number: G8 extends to `compare.json`. The top-level `meta.json` / `rollup.json` / `category/` go
away (one source of truth); `tools/verify_deploy.py` markers move to `index.json` and one filing dir.

**Site.** Load `index.json`; select by `#filing=<accession>` or the first row in index order;
a native `<select>` picker names filer + series + period; the existing page renders the selected
filing. A "Compare" section renders when the index holds two or more filings: categories as rows,
filings as columns, each cell "% FOR on shareholder items (n)" and "% FOR on management items (n)"
with thin flags, linking to `#filing=<acc>&category=<slug>`. With one filing it says, in a sentence,
that comparison needs two (failure is not emptiness).

**Gates.** G2 / G9 already run per source. G7 recomputes every filing dir and `compare.json`. G8
covers `compare.json`. New **G11 index-coverage**: every filing in the store has an index row and a
dir, every index row has a dir, and no dir lacks a row (a stale dir would deploy as a ghost filing).
README gate table becomes eleven; C1 enforces it.

**Budget.** Raw store ~20 MB per filing, three or four filings; EDGAR politeness unchanged; the
parked workflow is untouched.

## 6. Honesty checks that hold across both parts

- Per category only. No number aggregates across categories, and none across filings.
- "% FOR" is a distribution of the fund's own votes by who proposed the item. It claims nothing
  about what any board wanted. The page says so in the How-to-read block.
- `thin` per cell, `thin_n` from CONFIG (in the fingerprint).
- Every published number recomputes from `vote_records` under a fingerprinted run (G6, G7).
- Receipts verbatim; the ordinal and find-it-by text are derived from stored fields, never fetched.

## 7. Testing and verification

`pipeline/checks.py` (ten, then eleven gates); `tools/verify_claims.py`; `tools/verify_deploy.py`
after each push; a browser render under the production CSP via `serve_local.py` (Playwright is
available in this session; zero console errors is the bar, as at `acbd2bb`); then a **second
cold-read round** by the same readers against the corrected page, following `docs/COLD_READ_PROTOCOL.md`.
Findings from that round are processed the same way: verified in the data, dispositioned, logged.

## 8. Assumptions for Lance to override

1. Big Three first, each through its S&P 500 index fund, so the compare view compares like with
   like; the contrast set comes after the three run end to end.
2. The concordance headline is dropped, not relabelled: the field it rests on does not mean what
   the header says in the one filing we have, and there is no honest label for a number a reader
   will quote backwards.
3. One series per registrant, pinned by name; more series are one config line each, later.
4. The already-ingested Morningstar Value Index filing stays in the store and the index.

## 9. Build order

1. Part 1: extractor + exporter + gates, re-extract, export, ten gates green, site changes, browser
   check, commit (rule-15 sweep of the touched pipeline files included), push, `verify_deploy`.
2. Second cold-read round on the corrected page. Findings dispositioned before Part 2 starts.
3. Part 2: `series_match` + three sources, ingest (identity and series checks), extract, export
   layout, G11, site picker + compare, browser check, commit, push, `verify_deploy`, third read.
4. Deposit: what this taught that the registry does not hold (section 10).

## 10. Deposit candidates (sent to RapidForge with this spec)

- **An N-PX row is a vote lot, not a proposal**, and `managementRecommendation` is per lot. Any
  N-PX consumer that counts rows as proposals, or reads that field as the board's view, is wrong
  on the first filer it meets. Belongs beside the EDGAR client in `ingestion-pipeline`.
- **A filed field's name is not its meaning.** Check a field's semantics per source before any
  headline rests on it; the check is a computed one (here: agreement on shareholder items).
  A `static-publication-site` trap.
- **The cold-read protocol** (`docs/COLD_READ_PROTOCOL.md`): five independent strangers against one
  page, four questions, findings verified in the data before disposition.

## 11. Review notes from RapidForge (2026-08-30) and how Part 1 applied them

1. **Denominator beside the number.** Every "% FOR" cell publishes `for_lots` and `n_voted` and
   the page renders "23.8% (63 of 265)". The semantics line states both 1,439 shareholder lots and
   the 1,433 with a recommendation.
2. **Semantics check as a stored fact.** `meta.mgmt_rec_semantics` (agreement `0/1433`, verdict
   `tracks-lot`, `headline_allowed: false`, threshold from CONFIG so it is in the fingerprint);
   G7 recomputes it, G8 requires it.
3. **What the ordinal counts.** `record N of 29,891` counts rows (lots plus zero-lot rows);
   `totals` carries `records`, `lots`, `zero_lot_rows` and `proposals` separately and G7 asserts
   `lots + zero_lot_rows == records`.
4. **G11 and `catalogue_drift`.** Noted for Part 2's gate docstring.

## 12. Part 1.1 - round two findings (2026-08-30), bounded, before Part 2

Round two (Glizzness, league, LinkedUmp, VisibleGov; reports and the data checks in CHATLOG)
found defects in Part 1 itself. Each verified in the store. Dispositions, all shipping together:

| # | Finding | Data | Change |
|---|---|---|---|
| R1 | Heading count and pager count disagree under a filter | UI | heading follows the filter |
| R2 | Lots of one proposal "2 of 3" with no "1 of 3" in the list; Proposals column sums to 10,721 vs 10,523 | under the one key, 495 proposals have lots in more than one category; a proposal is counted in each category it touches | each record carries the categories its sibling lots fall in; the lot cell says "lot 1 is under ENVIRONMENT OR CLIMATE"; `totals.proposals_in_multiple_categories` published and explained beside the column |
| R3 | Same ballot item under two proposal numbers | the key used the issuer name as filed; the filing spells one company two ways; the 0-share block carries the upper-case spelling | one key function normalises case, whitespace and trailing punctuation on issuer, description and proposer: 10,523 -> 8,906; the page says what the count counts |
| R4 | Zero-share lots inside "FOR of voted lots" | 2,845 zero-share lots (1,425 FOR); DEI shareholder cell 4 of 23 | denominator = lots with a readable vote AND shares > 0, labelled "of lots that voted shares"; zero-share lots published per cell and per category |
| R5 | The 50% threshold is an assumption presented as the test; a perfect zero looks like a vocabulary mismatch | both sides normalised from identical raw spellings; exact mirror on shareholder lots (AGAINST/FOR 819, FOR/AGAINST 408, ABSTAIN/AGAINST 206); under the one key 4,594 of 8,904 proposals carry different values on different lots; all 4,204 ABSTAIN lots carry AGAINST | `mgmt_rec_semantics` publishes the crosstab (shareholder and management lots) and `proposals_with_mixed_recommendation`; the verdict rule becomes: mixed-recommendation proposals at or above `thin_n` -> not the board's view; the 50% constant is removed entirely; reader-facing words replace "tracks-lot" |
| R6 | `thin_n` and `min_board_view_pct` are typed constants under a "none are typed" claim | true | `meta.config` publishes both; the provenance box shows a "Configuration" row; the claim reads "computed from the filing; two thresholds are configuration, shown here" |
| R7 | "Mgmt rec FOR" on a row still reads as the board's wish | UI | the column header and cell titles carry the filing's verdict, computed |
| R8 | "proposal #45" - whose numbering; one link to THIS lot | this page's; EDGAR has no per-lot anchor | labelled "this page's"; done in the table fix |
| R9 | "zero-lot rows" vs "zero-share lots" conflated; "-" undefined; ABSTAIN unexplained; fractional shares; engine-run id changed silently; no companies count | as filed; 318 CUSIPs | reworded totals; definitions for "-", ABSTAIN as filed, fractional shares as filed, id changes with code or config; `totals.issuers` (distinct CUSIP) |
| R10 | No Show option for shareholder / management items | UI | two more filters; the semantics line points at them |
| R11 | Glossary too long before the first number; "Four strangers" sentence | UI | three terms first, the rest collapsed (`<details>`); the sentence moves to one line beside the provenance claim |
| R12 | Header numbers read as the registrant's | UI | one line: the numbers below are the series', not the registrant's |

Extractor change (R3) rotates the fingerprint; the store is re-extracted. G7 recomputes every
new field; G8's forbidden keys unchanged. `verify_claims` C3 is unaffected (it uses record counts).

**Built 2026-08-30.** RapidForge's review of the data claims added one requirement, applied: one key
function, every count derived from it, and the counts re-derived before publication (Lesson 9).
Engine run `e3b050bc2353357b`; rendered under the production CSP via serve_local.py in Playwright with zero console messages: DEI drill-down with the elsewhere filter (21 of 23), the verdict in the Mgmt rec header, lot notes naming the other categories, the table fitting its container.

## 13. Part 1.2 - round three findings (2026-08-30), bounded, before Part 2

Five rendered reads of the Part 1.1 page (viewports 914 to 1920 px). Dispositions in
`AUDIT_LOG.md` (2026-08-30, round three). The changes: the headline table fits or says it
scrolls; the recommendation test's example comes from a category with no unparseable votes and
its link opens exactly those lots (a "one proposal only" filter); one explanation of proposals
versus lots replaces two footnotes; zero-share lots are split into readable (what the cells
count) and not; `proposals_without_recommendation`, `extra_category_entries`,
`issuers_with_multiple_spellings`, per-category `n_proposals_mixed_recommendation` and per-cell
`for_zero_share_lots` published and recomputed by G7; `site/data/issuers.json` lists every
spelling as filed (G7 recomputes it, verify_deploy checks it at the origin); lots sort in lot
order within a proposal regardless of the name's case; thin cells carry no percentage.

Engine run `e3b050bc2353357b`; rendered under the production CSP via serve_local.py in Playwright with zero console messages: the headline table equals its container at 1366 px and shows the worded hint at 929 px (1,021 px in 857); the example link opens all 7 Medtronic lots in lot order; the spellings list loads 299 companies on demand.

**Round four** asks a different question, from RapidForge: the one number a reader would quote
to someone else, and whether it is the one we would want quoted. Readers who have not seen the
page, where any exist.

## 14. Part 2 - built 2026-08-30

Built as section 5 with two changes the data forced:

1. **Multi-series filings.** Vanguard files one N-PX per series; iShares Trust files 29 series
   in one N-PX (180 MB) and SPDR SERIES TRUST 45 in one (106 MB). `enumerate_index_html` now
   returns every series row; the pin is the series **id** (`series_id` in SOURCES; names change
   year to year, ids do not; `series_match` is the name-fragment fallback); `filings.series_id` is
   stored; extraction is scoped to the pinned series (the raw file keeps every series); the export
   unit is (filing, series). SPDR's S&P 500 fund is "State Street(R) SPDR(R) Portfolio S&P 500(R)
   ETF" (S000006983), not findable by the name I had guessed.
2. **Case-sensitive EDGAR paths.** iShares lists `BRDWLB_0001100663_2026.xml`; the adapter's
   lowercased document key produced a 404. Original-case names are used for URLs now.

Layout as designed: `index.json` (ordered by filer then series, never recency), `filings/<acc>/`
in the Part 1.2 shape, `compare.json` with copied per-category cells. Gates: G7 per filing plus
index and compare recomputation (1,011 checks over four filings), G8 over every artifact including
a cross-filing aggregate-key ban, G11 index-coverage. `verify_deploy` derives per-filing markers
from the local index; `verify_claims` finds the README's filing through the index. The site: a
filing picker in the header, `#filing=<accession>&category=<slug>` routing, and the compare
section (categories as rows, filings as columns, each cell that filing's own numbers). The old
Morningstar Value Index filing stays in the store and the index, as section 8 assumed.

Engine run `f97e5b26827a3e1d`; rendered under the production CSP via serve_local.py in Playwright with zero console messages: four filings in the picker, a 12-category compare table, and a compare cell that switched to the SPDR filing and opened its director elections by hash. First cross-fund read, director elections, % FOR of lots that
voted shares on management items: iShares Core S&P 500 80% (4,794 of 5,995), SPDR Portfolio S&P
500 73.3% (4,514 of 6,159), Vanguard 500 74% (19,994 of 27,004), Vanguard Morningstar Value 71%
(13,992 of 19,701). Every number is that filing's own; the reader compares.

## 15. Part 2.1 - the contrast set, built 2026-08-30

Decision 3's contrast set, as far as N-PX reaches. Series ids came from the SEC's own
mutual-fund ticker file (`company_tickers_mf.json`: FXAIX, PREIX, SWPPX, AGTHX), registrant names
from each CIK's submissions JSON (the identity check compares against them). Added: Fidelity 500
Index Fund (FIDELITY CONCORD STREET TRUST, S000006027), T. Rowe Price Equity Index 500 Fund
(T. Rowe Price Index Trust, Inc., S000002089), Schwab S&P 500 Index Fund (SCHWAB CAPITAL TRUST,
S000005911; not in decision 3, added because it is the fourth large S&P 500 index fund and one
config line), and The Growth Fund of America (GROWTH FUND OF AMERICA, S000009228; Capital Group;
active, the contrast). **A public pension is not here and cannot be:** pensions do not file N-PX
vote records (since 2024 institutional managers file say-on-pay votes only), so that half of
decision 3 has no N-PX source. Recorded, not built.

Ingested in one run of seven sources, every series matched by id on the first or second index page read: Fidelity 500 Index Fund (138 MB, 22 series in the filing), T. Rowe Price Equity Index 500 Fund (45 MB, 6 series), Schwab S&P 500 Index Fund (88 MB, 12 series), Growth Fund of America (3 MB, 1 series). Extraction scoped to each pinned series: 110,666 rows across eight filings. The recommendation test then did what it was built for: Fidelity's and T. Rowe's filings carry zero self-contradicting proposals and are judged a board's view by evidence (headline_allowed true), while Vanguard's, iShares', SPDR's, Schwab's (12) and Growth Fund of America's (18) are not. Engine run `f97e5b26827a3e1d`; 8 filings on the page; rendered under the production CSP via serve_local.py in Playwright with zero console messages: eight filings in the picker, a 13-category by 8-filing compare table that says in words that it scrolls, the Fidelity page's semantics line reading its board-view verdict.
