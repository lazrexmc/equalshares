# Cold-read protocol

*The test the gates cannot run: what a stranger sees. Written 2026-08-29 after the first round
(five peer sessions asked, three reports within the hour). RapidForge asked for it as a file so the
registry can catalogue it; EqualShares is its first consumer.*

## Why

Ten gates prove the numbers recompute, the receipts resolve, the publication is committed. None of
them can see an assumption gap: a header a reader takes backwards, a term never defined, a link that
is technically a receipt and practically a haystack. Dogfood findings 1 and 2 were both of this
class. The owner said the project should proceed without his dogfooding; independent readers are
the substitute for the *test*, not for rung three (real users), which stays where it is.

## Who reads

Sessions or people with no stake in the page and, ideally, no domain knowledge. Ask five, expect
three. Leave out anyone in a specs-first stage or with a build in flight (RapidForge rule 8: a side
task costs the most there). Readers on the same machine can render the page in a real browser under
the production CSP; that is the preferred read. A reader without a browser reads the served HTML,
the page's JS, and the JSON, and says what a reader would see.

## The ask (send verbatim, one message)

> Open <URL> as a stranger who has never heard of <project> or <the source form>. If you have a
> browser tool, render it and open one drill-down; otherwise read the served files and say what a
> reader would see. Report in one message, four lines:
> (1) in one sentence, what is this page;
> (2) what confused you, or what you wanted to know and could not find;
> (3) any number or claim you could not trace to a receipt link;
> (4) anything you believe is false.
> Report the confusion, not the cause: "I cannot tell whether these four rows are one fund or
> several" is the whole job. A diagnosis you could not check from where you stand is worth less
> than it looks, and a wrong one lands in the record. No fixes, no praise, no rewrite. Nothing
> needed from the owner.

Ask for the render facts too when the reader has a browser: console errors, which row or category
they opened.

The four questions are a floor on what gets reported, never a ceiling: a protocol's shape must not
suppress a finding that has no slot in it. If something is wrong that none of the four asks about,
report it anyway. (VisibleGov, 2026-08-30, the complement to its own "confusion, not cause" rule,
which it wrote against its own miss on this site, not as advice passed along.)

## What comes back, and what to do with it

1. **Record every report in the trail** (CHATLOG), attributed, before touching anything. Condense
   only with the reader's key phrases kept verbatim.
2. **Verify each finding in the data before giving it a disposition.** Query the store and the raw;
   do not reason from the page. A reader's diagnosis can be wrong while the symptom is right (round
   one: "several series merged" was one series with multi-lot proposals). Both halves are recorded:
   the symptom is the finding, the cause is what the fix addresses. (VisibleGov, retracting its
   own diagnosis after round one: "a cold read reports the confusion, not the diagnosis ... a
   confident cause from a stranger is worth less than it looks." Now in the ask above.)
3. **Disposition each finding** in one line: fix / say so on the page / accepted as filed / not a
   finding, with the evidence. Findings that change a published statistic go to the spec, not
   straight to code.
4. **Send the verified cause back to the readers** (rule 10). A reader who learns their diagnosis
   was wrong reads better next round.
5. **Re-run the round after the fixes ship**, same readers, same four questions. Findings that
   recur are not fixed.
6. **Log the round** under AUDIT_LOG "Post-Audit Changes" with verdicts.

## What the readers are not

Not approval. Not rung three. Not a substitute for the owner's decisions where the spec names an
assumption for him. Five convergent reports are strong evidence about the page and no evidence at
all about whether the thing should exist.
