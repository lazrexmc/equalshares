# EqualShares - The Roll Call (slice v0)

How one fund family actually voted, per category, with receipts. One filer, one
N-PX filing, published as a static page. **The first build run THROUGH
RapidForge** (F:/RapidForge) - its modules decided this shape; this repo is the
test of them.

- Filer: VANGUARD INDEX FUNDS, CIK 0000036405
- Filing: accession 0001104659-26-102001, period 2026-06-30, filed 2026-08-27
- Stack: Python 3.14 stdlib only (pipeline) + vanilla JS (site). No frameworks,
  no bundler, no dependency that expires.

## Locked decisions this build implements

1. **Anti-blend.** No blended cross-category concordance number anywhere - not
   in the JSON, not on the page. This filing is ~73% director elections; a
   blended number measures nothing. Per-category only; inside a category,
   "% FOR" is split by who proposed the item (`voteSource`) and every cell
   carries its numerator and denominator, flagged `thin` below `n_voted < 5`
   (`thin_n`, VisibleGov precedent).
2. **Tri-valued field state.** extracted (value) / absent-in-source (raw NULL)
   / unparseable (raw kept, normalized NULL). Never invent, never blank a raw.
   Known dirty data: some `howVoted` values are numeric strings ("1.0"/"2.0"/
   "3.0", say-on-pay frequency votes) - they keep their raw, normalize to NULL.
3. **Computed, never typed.** Every published number is computed from
   `vote_records` by a fingerprinted engine run. Nothing on the page is typed.
4. **Receipts verbatim.** Two URLs stored at ingest time - the EDGAR filing
   index page (every record's `source_url`) and the document actually parsed
   (`vote_doc_url`, with size and sha256) - rendered verbatim. The site never
   constructs or guesses a URL at render time.
5. **Failure is not emptiness.** Any non-2xx fetch or JSON parse failure on the
   site renders a visible error state, never an empty table.
6. **Re-parse = UPSERT.** `vote_records` upserts on `(accession, seq)`;
   insert-ignore silently discards corrections and fails gate G5.
7. **A row is a vote lot, and no headline rests on `managementRecommendation`.**
   (Cold-read round one, 2026-08-29.) An N-PX `<proxyTable>` block holds 1-10
   `<voteRecord>` lots; a proposal spans 1-5 blocks. Every row is published
   with `proposal_no` / `lot_index` / `lots_in_proposal`, and totals hold
   records, lots and proposals apart. `managementRecommendation` is a per-lot
   field that tracks the lot in this filing (0 of 1,433 shareholder lots
   agree); `meta.mgmt_rec_semantics` publishes that computed check per filing
   and gate G8 refuses any recommendation-derived or blended key anywhere.

## How to run (five commands, from the repo root)

    python pipeline/run_ingest.py       # 1. fetch from EDGAR, store raw (SQLite: data/rollcall.db)
    python pipeline/extract.py          # 2. parse raw -> vote_records, provenance-stamped
    python pipeline/export_site.py      # 3. write site/data/*.json
    python pipeline/checks.py           # 4. acceptance gates - must pass before publishing
    python pipeline/serve_local.py      # 5. view at http://127.0.0.1:8765

Step 5 uses serve_local.py ON PURPOSE: it forces correct MIME types (Windows
registry entries can poison .json into text/plain and serve a silently blank
page) and it serves the SAME security headers as production by parsing
site/_headers - a bare `python -m http.server` does neither.

EDGAR requires a declared User-Agent (in code: `EqualShares/0.1
(lancemccarter1316@hotmail.com)`) and >= 0.5s between requests - anonymous
fetchers get HTTP 403. `data/` is local working state (raw files run to ~20MB);
keep it out of git.

## Acceptance gates (`pipeline/checks.py`)

Ten gates, exit 0 only on all-pass. These are the REAL gate names - this table
is a summary; checks.py's own output is the authority.

| Gate | Proves |
|---|---|
| G1 raw-integrity | Every filing's raw file exists with matching sha256 and size. |
| G2 coverage | Every filing in the store extracted to >0 vote_records (trap 6.8). |
| G3 outage-distinguishable | `run_ingest.py` against an unreachable host exits **2**; quiet day **0**; partial **1**. |
| G4 terminal-audit | Every `terminal` row has a non-empty written reason. |
| G5 reparse | Run extract twice: identical counts, no dupes; hand-corrupt one value, re-run: restored (UPSERT proven). |
| G6 provenance | Perturbed config -> different `engine_run_id`; unset -> original; a git commit alone never changes the id. |
| G7 export-consistency | Every `site/data` number recomputes from the database exactly - counts, slugs, ordering, formulas, totals. |
| G8 anti-blend | `rollup.json` carries NO top-level blended number; concordance is per-category only. |
| G9 listing-coverage | The NEWEST source-listed filing is actually ingested and extracted - a terminal retirement of the current filing can never read as a quiet day. |
| G10 publication-committed | `site/data` is not gitignored (the critical review finding: an unanchored `data/` pattern silently ignored the whole publication while CI regenerated it before every check). |

**Checked in the browser, not by checks.py:** the failure-is-not-emptiness
rendering (a failed fetch shows an error box, never an empty table) is
exercised manually against serve_local.py - break a data file and reload.

## Live

**https://equalshares.pages.dev/** - deployed 2026-08-29 (Cloudflare Pages, root `site`, build
output empty). Deploys on push to `master`. Verified at the origin, not in a browser: the CSP in
`site/_headers` is applied by Pages, JSON is served as `application/json`, and the served payload
carries no blended number. Re-check any time with `python tools/verify_deploy.py`.

**Host semantics enumerated** (`deploy-runbook` §7.1, for this host): `/` -> 200; `/index.html` ->
308 -> `/`; **an unknown path returns 200, not 404** - there is no `404.html`, so a mistyped URL
renders the Roll Call page. Cosmetic for a single-page site with no deep links; recorded rather
than fixed.

## Known limitations, accepted deliberately (2026-08-28 review)

Two review findings are DEFERRED, not fixed - recorded here so nobody mistakes
silence for coverage:

1. **No shadow/promotion path yet** (extractor-provenance module section 5.4).
   A rewritten extractor's first run overwrites production rows in place; the
   fingerprint records THAT it changed, not a side-by-side comparison. The
   module's own trigger applies: build the shadow mode when the extractor is
   actually rewritten. Until then, the raw store + UPSERT means any bad
   re-parse is recoverable by re-running the previous extractor version.
2. **`max_filings: 1` over a multi-series trust is an unstable pointer.**
   VANGUARD INDEX FUNDS files one N-PX per fund series (over a hundred in the
   window DRYRUN_001 Part 2 observed; that count is not derived here), so "the most recent filing" changes fund whenever any series
   files. The page always SAYS which series it shows (header + provenance
   box), so it is honest - but a slice reader refreshing across a filing day
   may see a different fund. Fix lands with multi-filing support, not with a
   pin hack.

## Owner decision - where the data lives: CLOSED, stay static (2026-08-29)

Lance answered on 2026-08-29, on the EventFinds Build 002 form, verbatim: **"13. C for now."**
The registry records it as settling this build's one interruption
(`F:/RapidForge/docs/INTERRUPTIONS.md`) and as the default it earned: `static-publication-site`
section 5.6, computed static artifacts are the $0 fallback, never an unapproved recurring charge.

So the shape stays as it is: the pipeline writes JSON to `site/data/`, the JSON is committed
(gate G10), and Cloudflare Pages serves it. The draft migration
`supabase/0001_rollcall_draft.sql` stays **DRAFT - NOT APPLIED**, by his word; it exists so the
Postgres path is ready if he chooses it later. For the record, the options were: (A) a dedicated
Supabase project at $10/mo, a fourth project past the free allotment; (B) a schema in an existing
project, whose repo-wide default-privileges revoke must **not** run as-is there (rls-wall trap 6.3);
(C) stay static at $0. Revisit when filers multiply.

## Deploy (Cloudflare Pages, connect-to-git - deploy-runbook phase 1)

1. Dashboard -> Workers & Pages -> Create -> Pages -> Connect to Git -> this repo.
2. Framework preset: **None**. Build command: **(empty)**. Root directory:
   **`site`**. Build output directory: **EMPTY**. The output directory is
   resolved **relative to the root directory** - with root `site` and output
   empty, Pages publishes `site/` itself. Typing `site` into the output field
   would make Pages look for `site/site` and 404.
3. Every push to master redeploys. Definition of done is rung three: built ->
   deployed/viewable -> **live**. A resolving URL is only *viewable*.

Note: Pages 308-canonicalizes `.html` to extensionless before rewrites resolve;
if a `_redirects` file is ever added, its targets must be extensionless.

## Instruments (`tools/`)

Two checks a stranger can re-run from the repo, both stdlib only, both exit 1 on drift:

    python tools/verify_claims.py    # every counted claim in the live documents derives from data, code or git
    python tools/verify_deploy.py    # the origin serves the bytes git holds; headers applied; JSON content-type

`pipeline/checks.py` remains the data gate. The cross-project standard this repo follows is
`F:/RapidForge/docs/PROJECT_STANDARD.md`; `python F:/RapidForge/tools/verify_standard.py` measures
compliance. Deviations are declared in `CLAUDE.md`.

## Provenance statement

Every published number traces to an engine run:

    code_fingerprint = sha256(bytes of extract.py + edgar_npx.py + store.py, concatenated)
    config_hash      = sha256(canonical JSON of CONFIG in sources.py, sorted keys)
    engine_run_id    = sha256(code_fingerprint + "|" + config_hash)[:16]
    git_commit       = trace metadata only - NEVER part of the id

Every `vote_records` row carries `engine_run_id`; `site/data/meta.json`
publishes the full engine_run block plus the raw file's sha256 and byte size.
Two runs that behave identically share an id; two that differ cannot.

## GitHub Actions

`.github/workflows/ingest.yml` runs ingest -> extract -> export -> checks on
manual dispatch and uploads `site/data` as a build artifact. The cron is parked
(commented) until a push destination exists - the un-park condition is written
beside it in the file.
