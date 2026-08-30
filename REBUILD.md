# REBUILD.md - Disaster recovery (rebuild The Roll Call from nothing)

> The from-nothing runbook. It assumes the **GitHub repo** survived and everything else is gone:
> this machine, the local `data/` store, the Cloudflare Pages project, the Actions run history.
> There are no secrets anywhere in this system, so there is no secret map to keep.
>
> Last updated: **2026-08-29**. Self-audit of this file's claims in section 5.

## What the system is (one paragraph)

One private GitHub repo, one static host, no database in production. A stdlib-only Python pipeline
fetches one N-PX filing from SEC EDGAR into a local SQLite store (`data/rollcall.db`, gitignored),
extracts `vote_records` under a fingerprinted engine run, and exports `site/data/*.json`. Those
JSON files are **committed** (gate G10) and Cloudflare Pages serves `site/` as-is on every push to
`master`. The Supabase migration under `supabase/` is a draft that has never been applied, by the
owner's word (2026-08-29, "13. C for now").

## 0. Premise and survivors

- **Assume GONE:** this machine; `data/` (raw filings ~20MB, `rollcall.db`); the Cloudflare Pages
  project; GitHub Actions run history.
- **Assume SURVIVES:** `github.com/lazrexmc/equalshares` (private as of 2026-08-29), which holds
  the pipeline, the site, **and the publication** (`site/data/`, 14 files). The method it was built
  from is a separate repo, `F:/RapidForge` - needed to read *why*, not to run this.
- **Secrets: none.** No API keys, tokens, `.env`, or repository secrets. EDGAR requires a declared
  User-Agent with a contact email; it is plain text in `pipeline/sources.py` (`EDGAR_UA`) and is
  Lance's own address, not a credential.

## 1. Restore the workspace

```powershell
git clone https://github.com/lazrexmc/equalshares.git
cd equalshares
python --version   # 3.14; stdlib only, nothing to install
python pipeline/serve_local.py   # the committed publication is viewable at once: http://127.0.0.1:8765/
```

`serve_local.py` on purpose: it forces correct MIME types and parses `site/_headers`, so what you
see locally is under the production CSP.

## 2. Regenerate the data (only when fresh numbers are wanted)

```powershell
python pipeline/run_ingest.py    # EDGAR -> data/raw + data/rollcall.db. Exit 0 quiet day / 1 partial / 2 outage
python pipeline/extract.py       # raw -> vote_records, engine_run_id stamped
python pipeline/export_site.py   # -> site/data/*.json (refuses mixed provenance: re-extract first)
python pipeline/checks.py        # ten gates, exit 0 only on all-pass; G3 needs the network
```

EDGAR: declared User-Agent, >= 0.5s between requests, or HTTP 403. `README.md` has the gate table
and the provenance formula. After a regeneration, `site/data/meta.json` carries the new
`engine_run_id`; commit `site/data/` with the code that produced it.

## 3. Re-deploy

Cloudflare Pages, connect-to-git, exactly as `README.md` section Deploy: framework preset **None**,
build command **empty**, root directory **`site`**, build output **EMPTY** (output resolves relative
to root; typing `site` there makes Pages look for `site/site`). Every push to `master` redeploys.
Then, from the repo:

```powershell
python tools/verify_deploy.py    # byte-compares site/ with the origin; checks the headers; JSON content-type
```

No custom domain as of 2026-08-29; the URL is `https://equalshares.pages.dev/`. GitHub Actions:
`.github/workflows/ingest.yml` is `workflow_dispatch` only, cron parked, no secrets to re-add.

## 4. Traps that bite a rebuild

- Pages 308-canonicalises `.html` to extensionless. If a `_redirects` file is ever added, its
  targets must be extensionless.
- An unknown path returns 200 (no `404.html`). Recorded, not fixed.
- Windows registry can poison `.json` into `text/plain` under a bare `http.server`; use
  `serve_local.py`.
- `export_site.py` is inside the behaviour fingerprint: any edit to it rotates `engine_run_id` and
  requires a re-extract before export (PLAYBOOK_DELTA Lesson 5).

## 5. Self-audit of this file's claims (2026-08-29)

| Claim | How it was checked |
|---|---|
| Repo is private | `gh repo view lazrexmc/equalshares --json visibility` -> `PRIVATE`, 2026-08-29 |
| No secrets in tracked files | grep for key shapes (`eyJ...`, `sk_live`, `service_role`) over `*.py *.js *.md *.yml *.sql`: none; `.gitignore` excludes `.env*`; no `.env` on disk |
| Publication committed | `git ls-files site/data` -> 14 files; gate G10 |
| Workflow uses no secrets | `grep 'secrets\.' .github/workflows/ingest.yml` -> none |
| stdlib only | no requirements file; every import is stdlib (checked by reading, not by a script) |
| Draft migration never applied | owner's word 2026-08-29 (`F:/RapidForge/docs/INTERRUPTIONS.md`); no Supabase project exists for it |

**Not yet tested:** an actual from-nothing rebuild has never been run. Until one is, this file is
a plan, not evidence (standard rule 9).
