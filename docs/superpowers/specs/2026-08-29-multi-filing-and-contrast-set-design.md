# Multi-filing and the contrast set - design

**Date:** 2026-08-29 (late, CDT). **Status:** DRAFT for RapidForge review before any code
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
| F3 | "Several series merged into one list": the same Cisco / Coca-Cola / Disney proposal appears 2-4 times with different share counts and different votes; "one fund, one year" looks false | Every row carries the same `voteSeries` (`S000002840`); it IS one fund. An N-PX `<proxyTable>` (one proposal) holds 1 to 10 `<voteRecord>` lots, each with its own `howVoted`, `sharesVoted` and `managementRecommendation`. 10,387 proposals became 29,891 rows (2.88 lots per proposal; 1,944 single-lot, 4,141 with four). A row is a **vote lot**, not a proposal | Say so. Define "record = one lot"; count proposals and lots separately everywhere; group lots under their proposal in the drill-down. The split lots are themselves a finding worth showing: they are the fund voting blocks of its shares differently, which is what a pass-through voting program looks like in the filing (TODO inbox, "the lever that already exists") |
| F4 | "% with mgmt recommendation" is read backwards: ENVIRONMENT, HUMAN RIGHTS, DEI show 0%, and a stranger reads "opposed management every time" when the rows show the fund voting AGAINST shareholder proposals | `managementRecommendation` sits inside each lot and tracks the lot: Coca-Cola director election, lots ABSTAIN/AGAINST/FOR carry rec AGAINST/AGAINST/FOR - a board does not recommend AGAINST its own nominee. On SECURITY HOLDER items agreement is 0 of 1,433; on ISSUER items 24,270 of 28,359. The field does not mean "the board's recommendation" in this filing | **Drop the concordance headline.** No statistic derived from `managementRecommendation` is published as a headline for any filer until that filer's field semantics are checked (the check: agreement rate on SECURITY HOLDER items; a field that is the board's view cannot be 0%). Replace with "% FOR" split by `voteSource` (management items / shareholder items), each with n and the thin flag. The as-filed recommendation stays visible in the drill-down rows, labelled as filed |
| F5 | "Comparable" is undefined and excludes 10 records with no explanation (CORPORATE GOVERNANCE 1,330 vs 1,322; SHAREHOLDER RIGHTS 168 vs 166) | The 10 have `managementRecommendation` = `NONE` in the raw, normalised to NULL. `NONE` is an extracted value meaning "no recommendation", not absent-in-source; conflating them broke the tri-valued rule | Keep `NONE` as a normalised value. "Comparable" retires with the concordance column |
| F6 | Every row's receipt is the same URL - the 17.7 MB rendered table; "a receipt for every row" is one receipt for all rows | True. N-PX has no per-record anchor or identifier; the rendered view is the closest EDGAR gets | Say it plainly: one receipt per filing, and each row tells you where to look. Show the row's ordinal in the filing (`record 12,345 of 29,891`) and its proposal number, plus the find-it-by text (issuer, CUSIP, meeting date) **visibly**, not only in a title attribute (VisibleGov's "Roll call 283" pattern) |
| F7 | "Raw SHA-256 2299061d3fe3..." is truncated and unverifiable; "Engine run b13f9c5877e362ce" links to nothing and is unexplained | Both are stored in full in `meta.json` | Full hash in a copyable code element; one-line definitions beside both |
| F8 | Undefined terms: Absent in source, Unparseable, Withhold vs Against, the proxy year (July-June never stated), who EqualShares is, whether "% with mgmt" means agreed | All definable from the data and the SEC form | A "How to read this" block, one place, every term. Computed numbers stay computed; the block contains no numbers |
| F9 | Intro overstates: "Every mutual fund votes the shares it holds ... at every company meeting, every year" (bond and money-market funds hold no voting shares) | Correct | Reword: funds that hold voting shares vote them |
| F10 | "Show all 266 records" rendered 100 rows with no visible way to the rest | The pager exists (`PAGE_SIZE = 100`, prev/next below the table); the reader did not find it | Pager above the table as well as below; page status in the heading |
| F11 | Category placement (a Cisco DEI item under ENVIRONMENT OR CLIMATE) cannot be told apart from the site's own choice | Categories are `categoryType` as filed; multi-category records are counted under their first | Label: "SEC category, as filed by the fund" |
| F12 | Lots of 0 shares, unexplained | 2,845 lots report `sharesVoted` = 0 | Shown as filed, with a definition line: a zero lot is the fund reporting that a voting block held no shares at that meeting |
| F13 | The row link's `xslNPX-INFO-TABLE_X01/proxytable.xml` path looks constructed | It is stored at ingest from the filing index page (`cc24368`), never built at render time | No change to the mechanism; the receipts note names where the URL came from |

## 3. Scope

- **Part 1 - reader fixes** on the current page (F3-F13). Ships first, on its own commit, so the
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
