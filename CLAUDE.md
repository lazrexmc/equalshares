# EqualShares - The Roll Call

Eight fund series from their SEC Form N-PX filings, per category, with receipts,
and the same category comparable across them. The first build run THROUGH
RapidForge. The method lives at `F:/RapidForge` - **pointers, never copies**
(copies fork; proven twice on that machine).

## Read order

1. `README.md` - what this is, how to run, the gates, live status
2. `TODO.md` -> **RESUME HERE** - the live state; it outranks every other document here
3. `PLAYBOOK_DELTA.md` - what this build earned, and where its lessons live in the registry
4. The RapidForge modules this build implements - read them **at**
   `F:/RapidForge/modules/`, never copy them here:
   - `ingestion-pipeline.md` (raw/extract split; outage != quiet day; the `listings` expected set)
   - `extractor-provenance.md` (the engine_run_id fingerprint; promoted to proven on this build)
   - `static-publication-site.md` (failure is not emptiness; receipts; section 5.6 stay-static default)
   - `headers-aware-local-server.md` (`pipeline/serve_local.py` is one of its two reference implementations)
   - `deploy-runbook.md` (phase 1 executed here, 2026-08-29)
   - `pointer-checker.md` (gate G10 became its second check)
   - `supabase-rls-wall.md` (the draft migration only - NOT applied)
   - `scheduled-worker-github-actions.md` (the parked workflow)
5. `F:/RapidForge/docs/DRYRUN_001_equalshares.md` Part 2 - the live EDGAR
   findings this design is built on
6. `CHATLOG.md` - the word-for-word trail, only if you need the *why*. It starts
   2026-08-29; before that the trail is the commit bodies (`git log --format='%h %ci%n%B'`)

## Standing rules (locked - do not relitigate)

- **Computed, never typed.** Every published number is computed from
  `vote_records` by a fingerprinted engine run.
- **Anti-blend.** Per-category only. No blended cross-category number anywhere,
  ever - not in JSON, not on the page.
- **Tri-valued field state.** extracted / absent-in-source (raw NULL) /
  unparseable (raw kept, normalized NULL). Never invent, never blank a raw.
- **Receipts verbatim.** Render stored URLs and hashes exactly as stored; never
  construct or guess a URL at render time.
- **One identity function.** `assign_proposals` in `pipeline/extract.py` decides
  what a proposal IS - issuer, description and proposer normalised for case,
  spacing and trailing punctuation; CUSIP and meeting date used as filed - and
  **every published count derives from the `proposal_no` it assigns**, never
  from a second grouping written at the point of use. Filing data splits one
  company across spellings and one proposal across punctuation: the first key
  did, and fixing it moved the published counts 10,523 -> 8,906 proposals, 198
  -> 495 spanning categories, 5,022 -> 4,594 self-contradicting. A count
  computed anywhere else silently disagrees with the page.
- **No headline rests on a filed field until a computed check on that filer
  passes.** `managementRecommendation` is named after a board's view and is not
  one in six of eight filings on disk. `export_site.py` computes
  `meta.mgmt_rec_semantics` per filing (proposals whose own lots carry more than
  one value; a board recommends once per item), publishes the evidence, and G8
  refuses `headline_allowed` unless the verdict is `board-view`. Re-admission is
  by evidence, never by memory: Fidelity and T. Rowe pass, the other six do not.
  This is not covered by computed-never-typed, which governs how a number is
  produced rather than whether it may be published at all.
- **Draft-then-apply.** Anything touching production data/infra (the Supabase
  migration) is a reviewed draft; Lance applies it himself.

## The cross-project standard

`F:/RapidForge/docs/PROJECT_STANDARD.md` is the one place the rules every project
shares are written: required artifacts under fixed names, fifteen rules, the
convention conflicts resolved. `python F:/RapidForge/tools/verify_standard.py`
measures this repo against it. Adopted here 2026-08-29 on Lance's word in this
repo's session ("ensure rules/standards/constraints are updated and follow
rapidforge"). Instruments: `python tools/verify_claims.py` (counted claims,
punctuation, pointers, RESUME date, publication committed) and
`python tools/verify_deploy.py` (does the origin serve what git holds).

### Deviations from the standard

- **Commit trailer** - every commit here carries
  `Co-Authored-By: Claude Fable 5 (1M context) <noreply@anthropic.com>`. Declared.
- **`PLAYBOOK_DELTA.md` is thin by design.** The registry ran this build, so its
  lessons were deposited into `F:/RapidForge/modules/*.md` section 6 at the
  deposit gate; the local file points at them and holds only what was earned
  here (standard section 3: "EqualShares (no local delta - allowed for a build
  the registry ran)").
- **Specs.** Build 001's design record is the registry's
  `F:/RapidForge/docs/DRYRUN_001_equalshares.md` and `F:/RapidForge/docs/INTERRUPTIONS.md`,
  pointed at, not copied. From 2026-08-29 this repo's own specs live under
  `docs/superpowers/specs/` as the standard asks.
- **Instruments** - a claim checker and a deploy verifier are present. No RLS
  probe: nothing runs against a database in production (the Supabase draft is
  unapplied by the owner's word, 2026-08-29). No PII guard: the repo has never
  held contact data; the one email address is the User-Agent EDGAR requires,
  in `pipeline/sources.py`, Lance's own.
- **`CHATLOG.md` starts 2026-08-29.** The trail before that is the commit bodies;
  nothing is retyped.
- **Rule 15 (plain ASCII punctuation)** is applied everywhere: documents, the
  served `site/index.html` and `site/js/`, and every file under `pipeline/` and
  `tools/`. The per-file sweep this file once deferred completed during Part 1.1
  (2026-08-30), each fingerprinted file swept alongside a real behaviour change
  so no `engine_run_id` rotated for punctuation alone (PLAYBOOK_DELTA Lesson 5).
  `tools/verify_claims.py` C4 fails on any hit in a live document.

## Finishing

The deposit is a GATE: a build finishes when it is written down what this
build taught that the RapidForge playbook does not already contain.
