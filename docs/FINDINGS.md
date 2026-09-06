# Findings and frame

*What this project has actually found, and how to tell it. Lance, 2026-09-06: "worth saving
before you switch, because they're the actual output of these sessions and they're easy to lose in
a code context." Every number here was re-derived from `data/rollcall.db` on 2026-09-06 and each
one names the query that produces it. Nothing here is published on the site yet.*

**The standing rule for this file, in Lance's words: verify the exact category count on the live
page before you ever publish a number.** The first draft of finding 1 was checkable-wrong, and the
check took two minutes.

---

## Finding 1 - Fidelity said no to every social and environmental shareholder proposal, in both directions

**As stated first: "every shareholder proposal in that Fidelity filing voted AGAINST." That is
false, and someone would have found it.** Fidelity 500 Index Fund voted FOR **34 of 340**
shareholder-proposed vote lots: 22 in CORPORATE GOVERNANCE, 10 in SHAREHOLDER RIGHTS AND DEFENSES,
2 in COMPENSATION. Publishing "blanket no to shareholder voice" invites one click to disprove.

**What is true, and stronger for being exact.** Across the four social and environmental
categories the fund voted FOR **zero of 149** lots that voted shares:

| Category (as filed) | FOR | of |
|---|---|---|
| ENVIRONMENT OR CLIMATE | 0 | 66 |
| OTHER SOCIAL ISSUES | 0 | 57 |
| HUMAN RIGHTS OR HUMAN CAPITAL/WORKFORCE | 0 | 20 |
| DIVERSITY, EQUITY, AND INCLUSION | 0 | 6 |
| **total** | **0** | **149** |

**And it is not a political direction, which is the part worth publishing.** Those 149 lots cover
proposals from both sides and every one was opposed:

- **116 distinct proponent-side proposals** (report on emissions, racial equity audits, pay gaps,
  lobbying disclosure, charitable giving) - all AGAINST.
- **9 distinct ESG-critical proposals** - all AGAINST. Verbatim from the filing: *"a shareholder
  proposal regarding a viewpoint diversity risk report"*; *"Report on Discrimination in Charitable
  Support"*; *"a stockholder proposal requesting a report on the risks of ESG and DEI executive
  compensation"*; *"report on the risks of the Company excluding religious charities"*;
  *"report on risks of anti-American discrimination from H-1B visa"*.

So the story is not "anti-climate" and not "blanket no to shareholder voice". It is: **on social
and environmental questions this fund declines to take a position on behalf of the people whose
shares it votes - whichever direction the question comes from - while voting FOR about one in six
of the governance proposals put to it.** That is a statement about who holds the vote, not about
climate.

## Finding 2 - the contrast is the evidence, because the ballots are the same

Fidelity 500 Index Fund and iShares Core S&P 500 ETF hold **the same companies**: 490 of them by
CUSIP appear in both filings, 99% of the smaller list. On climate proposals specifically, 31 of the
32 companies where iShares voted are companies where Fidelity also voted.

Same companies, same year, same proposals, opposite answers:

| Category, shareholder items | Fidelity 500 Index | iShares Core S&P 500 |
|---|---|---|
| ENVIRONMENT OR CLIMATE | 0.0% (0 of 66) | 40.3% (27 of 67) |
| OTHER SOCIAL ISSUES | 0.0% (0 of 57) | 49.0% (25 of 51) |
| HUMAN RIGHTS OR HUMAN CAPITAL/WORKFORCE | 0.0% (0 of 20) | 46.9% (23 of 49) |

This is what makes the number mean something. A single fund voting 0% could be an artifact of which
proposals reached its ballots. Two index funds holding the same 490 companies, one at 0% and one
near half, cannot both be explained by the ballot. **The difference is the fund, not the year.**

## The frame - what-is / what-could-be, with the contrast as the engine

Duarte's structure, and the opening is the contrast, **not** the 6,591-row table. The table is the
receipt; the contrast is the story.

- **WHAT IS.** You own an index fund. It votes your shares at 490 companies. On every social and
  environmental question put to those companies last year, your fund said no - 0 of 149 - to
  proposals from every direction. You did not know, because the filing is public and unreadable.
- **WHAT COULD BE.** Another index fund, holding the same 490 companies, said yes to nearly half.
  The vote is not fixed by the market or the ballot. It is a choice your fund makes, and it could
  be yours.
- **THE GAP, repeated.** Category by category, fund by fund, each with a receipt.
- **THE NEW BLISS.** You can see how your fund votes, compare it to the alternative, and move -
  or ask it to vote differently. The Big Three already run pass-through voting programmes
  (TODO inbox, "the lever that already exists"): the vote can be yours without pooling a dollar.

**The line under all of it, Lance, 2026-09-06:** *"treat humans like humans. The whole project is
just that sentence with receipts."* The instrument exists so a person can check the claim rather
than trust the claimer. That is the whole design rule, and it is why no headline rests on a field
that has not been tested and why every number carries its denominator.

## Before publishing any of this

1. Re-derive on the live page, not from this file. These numbers were true at engine run
   `91dcc70d71711b7d`.
2. Categories are the SEC's, as filed by the fund - not this project's classification. Say so.
3. "% FOR" counts lots that voted shares. Fidelity has no zero-share lots; other filings do.
4. The 9 ESG-critical proposals are a small count. Quote them verbatim rather than percentaging
   them, and say there are nine.
