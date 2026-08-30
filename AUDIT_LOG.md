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
