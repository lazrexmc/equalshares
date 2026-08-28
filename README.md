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
   blended number measures nothing. Per-category only, flagged `thin` below
   `n_comparable < 5` (`thin_n`, VisibleGov precedent).
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

## How to run (five commands, from the repo root)

    python pipeline/run_ingest.py       # 1. fetch from EDGAR, store raw (SQLite: data/rollcall.db)
    python pipeline/extract.py          # 2. parse raw -> vote_records, provenance-stamped
    python pipeline/export_site.py      # 3. write site/data/*.json
    python pipeline/checks.py           # 4. acceptance gates - must pass before publishing
    python -m http.server 8000 --directory site    # 5. view at http://localhost:8000

EDGAR requires a declared User-Agent (in code: `EqualShares/0.1
(lancemccarter1316@hotmail.com)`) and >= 0.5s between requests - anonymous
fetchers get HTTP 403. `data/` is local working state (raw files run to ~20MB);
keep it out of git.

## Acceptance gates (`pipeline/checks.py`)

| Gate | Proves |
|---|---|
| Outage != quiet day | `run_ingest.py` pointed at an unreachable host (`--base-url-data` / `--base-url-archives`) exits **2**; a no-new-filings day exits **0**; partial failure exits **1**. Three different codes, always. |
| Terminal audit | Every `terminal` row has a non-empty written reason. |
| G5 re-parse | `extract.py` run twice: identical counts, no duplicates. Hand-alter one extracted value, re-run: the correct value is restored. Proves UPSERT, not insert-ignore. |
| G6 provenance | `EXTRACT_CONFIG_PERTURB=1` yields a **different** `engine_run_id`; unset returns the original. A git commit alone must **not** change the id (`git_commit` is trace, never part of the fingerprint). |
| Artifact integrity | `site/data` JSON totals match the database; the rollup contains no blended number; every record's `source_url` equals the filing's `index_url`. |
| Failure state | A non-2xx or unparseable fetch on the site renders an error box, never an empty table. |

## OPEN OWNER DECISION - where does the data live long-term?

The static path is **live today and costs $0**: the pipeline writes JSON to
`site/data/` and Cloudflare Pages serves it. Three options, facts only - Lance
decides:

| Option | Cost | Notes |
|---|---|---|
| A. New dedicated Supabase project | **$10/mo** (a 4th project, past the free allotment) | Draft migration ready: `supabase/0001_rollcall_draft.sql`, written for a dedicated project. Buys a queryable REST surface behind an RLS wall and per-record reads at scale. |
| B. Schema in an existing Supabase project | $0 | Shares blast radius with the host project. The draft's repo-wide default-privileges revoke must **not** run as-is there (rls-wall trap 6.3): it would change the posture of the host's future tables. Needs rework plus a grant-back audit first. |
| C. Stay static | $0 | The current shape. At one-filing scale the JSON is small and nothing functional is lost. Revisit when filers multiply. |

Either way the migration is **DRAFT - NOT APPLIED**. Draft-then-apply: Lance
reviews and applies it himself.

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
