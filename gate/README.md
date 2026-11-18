# The gate

The repository's name promises a checker that confirms every figure in an Arabic version
matches its English original. **It is not built.** It gets built only if a cheap
measurement shows that real offers published in both languages get their figures wrong
often enough to be worth checking. This directory is that measurement.

## Where it stands

| Step | State | Where |
|---|---|---|
| 1. Label cases before any matcher exists | Done, 2026-11-18 19:34 UTC | [`cases/`](./cases/), commit `f63b393` |
| 2. Write the matcher | Done, first commit 2026-11-18 20:47 UTC | [`matcher/`](./matcher/), commit `6680690` |
| 3. Score it on the labelled cases | Done | [`SCORE.md`](./SCORE.md) |
| 4. Fix the threshold | **Not set.** It is the owner's decision, still open | `THRESHOLD.md`, to be committed before any page is fetched |
| 5. Scan public offers | **Not run** | |

Nothing has been measured on a real page yet. The checker's case therefore stands where it
did before this directory existed: unproven.

## What the matcher does

[`matcher/`](./matcher/) pairs six kinds of figure between an English text and its Arabic
version: prices, percentages, dates, phone numbers, links and promo codes. It reads each
figure into a value that does not depend on how it was written, so `١٬٢٩٩ ر.س` and
`SAR 1,299` read the same, and `٢٢ رجب ١٤٤٨هـ` reads as 31 December 2026 (Umm al-Qura,
through the [`hijridate`](https://pypi.org/project/hijridate/) tables). It then aligns
the two versions' figures of each kind in the order they are written and reports whatever
is left without an equal partner.

It reads no words and calls no model. That is a choice, not an oversight: the measurement
should cost nothing to run, and a figure checker that needs a language model to find a
wrong price would be a different product.

## The score

On the 78 labelled cases, 93 scored pairs of (case, check type):

| | Right | False green | False red |
|---|---|---|---|
| First run, commit `6680690` | 91 | 1 | 0, and 1 pair where it read no date at all |
| Now | 92 | 1 | 0 |

The difference between the two runs: 60 new test cases in
[`tests/test_fresh_sentences.py`](./tests/test_fresh_sentences.py), mostly short
sentences, with their expected values written before the matcher was run on them, found
four reading defects (a date
followed by a full stop, a date written `31-Dec-2026`, a range of rates `10-20%`, and
`tel` inside `hotel` taken as a phone cue). Fixing the first also fixed a case that had
been right for the wrong reason.

**The one false green that remains is a limit of the method.** In `price-04` the Basic
and Premium prices are swapped, but both versions list the amounts in the same order. A
matcher that pairs figures by order cannot see which plan a price belongs to. Seeing it
means reading the words around each figure, which this matcher does not do.

**A known risk for the scan.** A word in capitals with a digit in it reads as a promo code
even with no "code" nearby, so product codes such as `RTX4090` or `SM-A556E` are read as
codes. Where both versions name the same product this pairs and does no harm; where one
version leaves the product code out, it will be reported as a promo-code mismatch. The
scan's precision for promo codes will show how often that happens.

**What the score is worth.** The author of the matcher had read every labelled case
before writing it. The score shows that the matcher handles the traps written into those
cases. It says nothing about how often real pages trip it, which only the scan can show.
No native speaker has reviewed the labels.

## What the scan will be

Fifty to a hundred public offers that exist in both languages, each read in both and
scored per check type, with the false-green rate (estimated by reading a sample of pairs
the matcher called clean) reported beside precision. The threshold the result is held to
is committed before any page is fetched, so the result cannot move it. **A scan that
finds few mismatches is a result, and it means the checker is not built.**

Two things stand in its way today: the threshold is not decided, and this machine's
network policy refuses the shops' sites.

## Run it

```bash
cd gate
uv sync
uv run pytest                      # the 60 fresh test cases
uv run python score.py             # the score on the labelled cases
uv run python score.py --show      # every figure read, case by case
uv run python score.py --check     # fails if SCORE.md is out of date
```

The [`gate`](../.github/workflows/gate.yml) workflow runs the last check, the tests,
ruff and mypy on every change under `gate/`.
