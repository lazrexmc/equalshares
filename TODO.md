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

- **THE LARGER GOAL — Lance, 2026-08-28, verbatim:** *"Equalshares has a larger goal, if it can
  have enough funds to become the major voting entity in Blackrock vanguard and state street,
  equalshares could redistribute the wealth through the same processes these entities run now,
  their system would be used against them to drain them and make the playing field level for all."*
  **Lance, moments later:** *"Well if voters choose too"* — the redistribution happens only if the
  shareholders choose it. That makes the goal consent-based: EqualShares enables the choice; it
  never makes it. Captured as stated, not reworded. Two notes recorded alongside it, for Lance to weigh:
  - **It sits against locked decision 1** (`RapidForge/ProjectContext.md` §4: *activate, not
    accumulate — no pooled fund, no custody, no token; '40 Act / Howey / money-transmitter
    exposure*). Decision 1 is the **v1 route**, not a verdict on the larger goal. Re-opening it is
    Lance's call, not the build's.
  - **The lever that already exists needs participation, not capital.** The Big Three each run
    pass-through "voting choice" programs that let fund investors direct how their shares are voted.
    An organizer of *existing* shareholders' voting rights reaches voting power without pooling
    assets or registering a fund — which is the "activate" path decision 1 chose, and is the same
    system used from inside. Verify current program terms before building on them (class B).
  The Roll Call is step one on that road either way: nobody can direct a vote they cannot see.

- **2026-08-28, Lance — system-wide comparison: a CORE CAPABILITY, not the ultimate goal.**
  The goal is transparency — show how funds voted the shares they hold, with receipts. Comparison
  via the graphs is how that transparency becomes *useful*: put many funds' Roll Calls side by side
  so a shareholder can see how *different* funds voted the *same* proposals and directors (the
  contrast-set thesis, decision 3). The instrument draws no conclusion; the reader compares.
  Layers, in order of reach:
  1. **Cross-filer comparison** of identical proposals and director elections — more `SOURCES`
     entries, same pipeline. Crosstab by `voteSource` first (today's finding).
  2. **Director-name resolution across issuers**, so one director's elections can be compared across
     the companies they serve — a data structure, not a verdict. Entity resolution already exists:
     `VisibleGov/src/lib/person-identity.js`. The free-text name parser will be rewritten → the
     shadow path becomes necessary here.
  3. **DEF 14A enrichment** — full proposal text, proponent, outcome — correctly parked by
     DRYRUN_001; layer 3 waits on it.
  Every edge carries a receipt; the reader compares. Thesis-forward, instrument-backed (decision 4).
- Concordance semantics vary by filer convention on shareholder proposals — verify per filer
  before any cross-filer comparison is published.
- 50 multi-category records: consider counting under every category with a disclosure, once a
  second filer makes the choice matter.
