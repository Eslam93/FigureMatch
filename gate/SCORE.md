# The matcher's score on the labelled cases

Written by `score.py`. Do not edit by hand: `uv run python score.py --check` fails
if this file is not what the matcher produces.

78 cases, 93 scored pairs of (case, check type).

A **false green** is a labelled mismatch the matcher called a match. A **false red**
is a labelled match it called a mismatch. **Not read** is a labelled match where the
matcher found no figure of that type in either version, so its match compared nothing.
The false-green rate is false greens over labelled mismatches. Precision is the share
of the matcher's mismatch verdicts that the labels agree with.

A verdict can also be right for the wrong reason, which this table cannot show. The
figures the matcher read for every case are printed by `uv run python score.py --show`.

## By check type

| Type | Pairs | Labelled mismatch | Caught | False green | Labelled match | Passed | False red | Not read | False-green rate | Precision |
|---|---|---|---|---|---|---|---|---|---|---|
| Price | 20 | 10 | 9 | 1 | 10 | 10 | 0 | 0 | 1 of 10 (10%) | 9 of 9 (100%) |
| Percentage | 16 | 6 | 6 | 0 | 10 | 10 | 0 | 0 | 0 of 6 (0%) | 6 of 6 (100%) |
| Date | 17 | 7 | 7 | 0 | 10 | 9 | 0 | 1 | 0 of 7 (0%) | 7 of 7 (100%) |
| Phone | 14 | 6 | 6 | 0 | 8 | 8 | 0 | 0 | 0 of 6 (0%) | 6 of 6 (100%) |
| Link | 12 | 5 | 5 | 0 | 7 | 7 | 0 | 0 | 0 of 5 (0%) | 5 of 5 (100%) |
| Promo code | 14 | 6 | 6 | 0 | 8 | 8 | 0 | 0 | 0 of 6 (0%) | 6 of 6 (100%) |
| **All** | 93 | 40 | 39 | 1 | 53 | 52 | 0 | 1 | 1 of 40 (2%) | 39 of 39 (100%) |

## The traps

A false-green trap is a mismatch written so that a careless check calls it a match.
A false-red trap is a match written so that a careless check flags it.

| Cases | Pairs | Right | Wrong |
|---|---|---|---|
| False-green traps | 31 | 30 caught | 1 called a match |
| False-red traps | 41 | 41 passed | 0 flagged, 0 not read |
| Plain cases | 20 | 19 | 1 |

## False greens

- `price-04` (price, a false-green trap): The prices are swapped between the two plans, so the set of amounts is equal on both sides.

## False reds

None.

## Not read

- `date-11` (date): Same day in the same numeric form.

## Mismatches reported in a type the case does not label

None.
