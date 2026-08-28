# EqualShares — TODO

*The Roll Call: fund proxy votes made readable, with receipts. Built through RapidForge
(`F:\RapidForge`) — the method home. This file is the live state; `README.md` explains the build.*

---

## NOW

- [ ] **Dogfood** (rung three): Lance is using the page at http://127.0.0.1:8765/ and reporting.
      Two findings so far, both fixed and deposited: the cold-reader intro; receipts land on EDGAR's
      rendered vote table.
- [ ] **Cloudflare Pages connect** (~2 min, Lance): repo `equalshares`, **Root: `site`, Build
      output: EMPTY**. Rung two.
- [ ] **Where does the publication database live?** — the one open interruption. $10/mo project /
      schema-in-existing / stay static ($0, current). `README.md` has the facts.

## BUILD QUEUE

- [ ] **More filers.** The pipeline is one config line per source. Big Three + contrast set
      (Fidelity, T. Rowe, Capital Group, a large pension) — decision 3. Each is a `SOURCES` entry;
      the IM *notice* reports enumerate a filer's fund registrants for free (DRYRUN_001 finding 4).
- [ ] **Multi-filing support** — replaces the `max_filings: 1` unstable pointer (README, deferred
      review finding 2). A trust files one N-PX per fund series; the page must say which, or show all.
- [ ] **Shadow/promotion path** for the extractor — build it the first time the extractor is
      actually rewritten (extractor-provenance §5.4; deferred review finding 1).
- [ ] **Concordance by `voteSource`** on the category table — the 85.6% / 0.0% split belongs in the
      rollup, not only in a footnote.

## INBOX (captured, not chased)

- **2026-08-28, Lance:** *"The ultimate goal would be to compare tables system wide and see if
  board members across the major companies are in cahoots."* Decomposes into three layers:
  1. **Interlocking directorates** — resolve director names across issuers from the 73% of records
     that are director elections. Entity resolution already exists: `VisibleGov/src/lib/person-identity.js`
     (source-agnostic by design). Name parsing from `voteDescription` free text will be rewritten
     → the shadow path (above) becomes necessary here.
  2. **Bloc voting across filers** — same directors, same proposals, many funds; do they move
     together? The original contrast-set thesis, now with a pipeline under it. Must be crosstabbed
     by `voteSource` first (today's finding).
  3. **Board conduct** — committees, pay, related-party — is NOT in N-PX. Needs **DEF 14A**
     enrichment, correctly parked by DRYRUN_001. Layer 3 waits on it.
  The site publishes the graph with receipts; it never says "cahoots" — the reader infers.
  Thesis-forward, instrument-backed (decision 4).
- Concordance semantics vary by filer convention on shareholder proposals — verify per filer
  before any cross-filer comparison is published.
- 50 multi-category records: consider counting under every category with a disclosure, once a
  second filer makes the choice matter.
