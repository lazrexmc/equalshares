# PLAYBOOK_DELTA - EqualShares

*The traps and lessons **this project** earned. A delta, not a copy: the trunk is
`F:\RapidForge\MASTER_PLAYBOOK.md` (read section 4 traps before building) and the index of every
lesson on this machine is `F:\RapidForge\docs\PLAYBOOK_INDEX.md`. Pointers, never copies - copies
fork (proven twice on this machine).*

## 0. Lineage

Glizzness `REPLICATION_PLAYBOOK.md` -> LinkedUmp `PLAYBOOK_DELTA.md` -> VisibleGov `PLAYBOOK_DELTA.md`
-> RapidForge `MASTER_PLAYBOOK.md` (the trunk) -> **this file**.

Thin by design (declared in `CLAUDE.md`): the registry ran this build, so its lessons were deposited
into the modules at the deposit gate. Section 1 says where each one lives. Section 2 holds what was
earned here, with the failure narrative, and at the next deposit gate it goes back to the module.

## 1. Where Build 001's lessons live (by pointer, all under `F:\RapidForge\`)

| Lesson | Lives in |
|---|---|
| Outage != quiet day; persist the expected set (`listings`); the newest-listed guard (G9) | `modules/ingestion-pipeline.md` (cites `pipeline/store.py`, `pipeline/edgar_npx.py` `enumerate_index_html`) |
| Code + config fingerprint; the export step belongs inside it; the perturbation guard | `modules/extractor-provenance.md` (promoted to `proven` on this build) |
| Failure is not emptiness; receipts verbatim; tri-valued columns on the page; the stay-static default (5.6); `git check-ignore` on the publication | `modules/static-publication-site.md` |
| Parse `_headers` locally so the production CSP is tested before deploy | `modules/headers-aware-local-server.md` (`pipeline/serve_local.py` is a reference implementation) |
| Pages root/output pairing; an unknown path returns 200 on this host | `modules/deploy-runbook.md` (phase 1 executed here 2026-08-29) |
| G10 as a pointer check: every file under the publish dir must be tracked | `modules/pointer-checker.md` |
| The draft migration; a repo-wide default-privileges revoke must not run in a shared project | `modules/supabase-rls-wall.md` |
| A cron stays parked until a push destination exists | `modules/scheduled-worker-github-actions.md` |
| The build's one interruption (money-shaped) and its answer | `docs/INTERRUPTIONS.md` |
| The live EDGAR findings the design rests on | `docs/DRYRUN_001_equalshares.md` Part 2 |

## 2. Earned here

## Lesson 1 - The publication was gitignored while the README said it was committed (2026-08-28)

An unanchored `data/` pattern in `.gitignore` also matched `site/data/`, so the whole publication
was silently absent from the repo while the first line of the same `.gitignore` claimed it was
committed. CI could never catch it: `export_site.py` regenerated the files before every check.
Found by the adversarial review round (`4846c4f`). Fix: `/data/` anchored, and gate G10 asks git
directly (`git check-ignore` must fail for the publication). Rule: **a deploy claim needs git's
answer, not the filesystem's.** Deposited: `static-publication-site`, `pointer-checker`.

## Lesson 2 - A cold reader could not tell what the page was (2026-08-28)

Lance's first reaction to the live page: "it looks like we are looking at how many shares were
voted on specific proposals." Close, but the page had provenance and footnotes and no "what is
this and why should I care." Ten gates cannot see an assumption gap; only a reader can. Fix:
three sentences above the header, no numbers typed (`df0c576`). Rule: **dogfood is a stage, not a
courtesy - rung three exists because the gates stop at rung two.**

## Lesson 3 - The receipt landed on a document list, not on the row (2026-08-28)

Following a record's source link landed on the filing index page - honest, and useless at 21,474
records. Underneath it a second defect: EDGAR's `index.json` omits documents that the index PAGE
lists, including the direct `proxytable.xml` and EDGAR's own rendered, searchable view of the
table. Fix: enumerate the page too, union with `index.json`, land receipts on the rendered table
with a find-it-by hint (`cc24368`). Rule: **a receipt lands where the reader can find the row; a
source's machine listing is not its complete listing.** Deposited: `ingestion-pipeline`,
`static-publication-site` 5.3.

## Lesson 4 - A counted claim the store cannot derive (2026-08-29)

`README.md` said the trust files "108" N-PX per window. That number came from DRYRUN_001's EDGAR
observation; the store's `listings` table holds 2 rows (the one filing, seen twice), so no script
here could re-derive it. Rule 2 of the standard: derived or deleted. Replaced with a pointer to the
document that counted it; `tools/verify_claims.py` now derives the rest of the README's numbers.
Rule: **before typing a number, ask which script would notice it going stale.**

## Lesson 5 - Cosmetic edits to a fingerprinted file are not free (2026-08-29)

Rule 15 (plain ASCII punctuation) arrived; `pipeline/export_site.py` holds sixteen em dashes in
comments and messages, and it sits inside `FINGERPRINT_FILES`. Any byte change rotates
`engine_run_id`, `export_site.py` then refuses mixed provenance until `extract.py` re-runs over
29,891 rows, and G6/G7 want the new id everywhere. Correct behaviour - the fingerprint cannot know
a comment from code - but it means a punctuation sweep of that file costs a full re-extract. Rule:
**sweep a fingerprinted file only alongside a real behaviour change, and say so in the commit.**
Open question for the registry (`extractor-provenance`): should the fingerprint hash a
comment-stripped form? Sent 2026-08-29, not decided here.
