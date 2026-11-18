# 0010. The checker is built only if a measurement fixed in advance says so

- **Status:** Accepted for the labelled cases and the matcher. The threshold and the scan
  are open.
- **Decided:** 2026-11-18, commits `f63b393` (the cases), `6680690` and `1f33924` (the
  matcher)
- **Written:** 2026-11-18

## Context

A figure checker is worth building only if real offers published in English and Arabic
get their figures wrong often enough that someone would pay to catch it. That is a
question about the world, and a cheap way to answer it exists before writing the product:
compare the figures of public offers that exist in both languages, and count.

A measurement like this is easy to bend without meaning to. A matcher written alongside
its test cases learns them; a threshold chosen after seeing the result moves to meet it.

## Decision

The order is fixed, and each step is committed before the next starts, so the history
shows it was kept:

1. **Label cases before any matcher exists.** 78 English and Arabic pairs, 30 of them
   built to make a careless check miss a mismatch and 30 to make it flag a match. Committed
   at 19:34 UTC on 18 November.
2. **Write the matcher, and keep its first score.** Committed at 20:47 UTC with its score
   as first run, including its misses. Later fixes come from new test cases whose expected
   values were written before running them, not from the labelled set.
3. **Commit the threshold before fetching any page.** The owner decides it.
4. **Scan 50 to 100 public offers** and report the false-green rate beside precision for
   each kind of figure.
5. **A scan that finds few mismatches is the answer, and it means the checker is not
   built.**

The matcher reads no words and calls no model. The measurement should cost nothing to
run, and a checker that needs a language model to notice a wrong price would be a
different product with different costs.

## Alternatives

None is recorded.

## Consequences

- Reading no words has a known blind spot: two figures swapped between items while their
  order is kept, as in the labelled case `price-04`. The matcher misses that case.
- The person who wrote the matcher had read every labelled case, and no native speaker
  has reviewed the labels. The score on them shows the traps are handled, not that real
  pages are.
- Until steps 3 and 4 are done, nothing is known about real pages, and the checker's case
  is unproven. See [`gate/README.md`](../../gate/README.md).
