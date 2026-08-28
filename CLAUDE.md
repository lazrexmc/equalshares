# EqualShares - The Roll Call (slice v0)

The first build run THROUGH RapidForge. The method lives at `F:/RapidForge` -
**pointers, never copies** (copies fork; proven twice on that machine).

## Read order

1. `README.md` - what this is, how to run, the gates, the open owner decision
2. The RapidForge modules this build implements - read them **at**
   `F:/RapidForge/modules/`, never copy them here:
   - `ingestion-pipeline.md` (raw/extract split; outage != quiet day)
   - `extractor-provenance.md` (the engine_run_id fingerprint)
   - `static-publication-site.md` (failure is not emptiness; receipts)
   - `supabase-rls-wall.md` (the draft migration only - NOT applied)
   - `scheduled-worker-github-actions.md` (the parked workflow)
3. `F:/RapidForge/docs/DRYRUN_001_equalshares.md` Part 2 - the live EDGAR
   findings this design is built on

## Standing rules (locked - do not relitigate)

- **Computed, never typed.** Every published number is computed from
  `vote_records` by a fingerprinted engine run.
- **Anti-blend.** Per-category only. No blended cross-category number anywhere,
  ever - not in JSON, not on the page.
- **Tri-valued field state.** extracted / absent-in-source (raw NULL) /
  unparseable (raw kept, normalized NULL). Never invent, never blank a raw.
- **Receipts verbatim.** Render stored URLs and hashes exactly as stored; never
  construct or guess a URL at render time.
- **Draft-then-apply.** Anything touching production data/infra (the Supabase
  migration) is a reviewed draft; Lance applies it himself.

## Finishing

The deposit is a GATE: a build finishes when it is written down what this
build taught that the RapidForge playbook does not already contain.
