# Labelled cases for the parity gate

`labelled.jsonl` holds 78 short offers, each written as an English original and its Arabic
version, with the verdict a parity check must reach for each kind of figure in it. They were
written and committed **before any matcher existed**, so no label was adjusted to fit one.

Who labelled them: Claude (Opus 5.5), on 2026-11-18, for this gate. No native speaker has
reviewed them yet. A blind set labelled by someone else is a later step, and only if the gate
passes. Until then, a matcher's score on these cases says how it handles the traps written
here, not how it handles real pages.

## What a case holds

| Field | Meaning |
|---|---|
| `id` | Unique, prefixed by the main check type. |
| `en`, `ar` | The English original and the Arabic version. |
| `checks` | The check types the case scores, each `match` or `mismatch`. |
| `trap` | `false_green`: a mismatch built so a careless check calls it a match. `false_red`: a match built so a careless check flags it. `null`: a plain case. |
| `arabic_forms` | How the Arabic side writes its figures: `eastern_digits` (٠–٩), `arabic_separators` (٫ decimal, ٬ thousands), `arabic_percent` (٪), `arabic_currency` (درهم, ر.س, د.إ…), `arabic_month`, `hijri`, `number_words` (a figure in words or a phrase), `rtl_marks`, `arabic_script_code`. |
| `note` | Why the label is what it is. |

Every case pairs an English original with an Arabic version. 44 of the 78 write the Arabic
figures with Eastern digits, Arabic separators or percent sign, number words or a Hijri date;
51 use at least one Arabic form of any kind. 30 cases are false-green traps and 30 are
false-red traps. All phone numbers are made up, and every link uses the reserved
`example.com` and `example.net` domains.

## How a label is decided

A case is scored once per check type listed in `checks`.

**Mismatch** if any figure of that type has no equal partner in the other version: it is
missing, extra, or different. Figures pair by role, not by position or as a set: the Basic
plan's price pairs with the Basic plan's price, the booking deadline with the booking
deadline. Two prices swapped between plans are a mismatch even though the same amounts
appear on both sides.

**Match** only if every figure of that type pairs with an equal one.

What counts as equal, per type:

| Type | Equal when | Differences that do not count |
|---|---|---|
| Price | Same amount, same currency, attached to the same thing | Digit script, separators, currency code against symbol against word, position |
| Percentage | Same rate | Digit script, `%` against `٪`, the sign before or after the number, a phrase with the same meaning (نصف = 50%, بدون فوائد = 0%) |
| Date | Same calendar day, after converting a Hijri date (Umm al-Qura) | Digit script, month names (Gregorian, Levantine), numeric against written form |
| Phone | Same digits after dialling prefixes are resolved (`+971 4` = `04` in the UAE, `00974` = `+974`) | Spaces, hyphens, digit script, right-to-left marks, a `+` that drifted to the end |
| Link | Same host and path once the language marker is set aside, provided each version's marker names its own language | `www.`, a trailing slash, the `en`/`ar` path segment, subdomain or `lang` parameter |
| Promo code | Same characters, ignoring letter case | Quotation marks and right-to-left marks around it |

A promo code is compared as typed, so Eastern digits or Arabic letters inside a code make it
a different code: a customer cannot type `EID٥٠` at a checkout that expects `EID50`. A link in
the Arabic version that points at the English page is a mismatch.

## Counts

| Type | Match | Mismatch |
|---|---|---|
| Price | 10 | 10 |
| Percentage | 10 | 6 |
| Date | 10 | 7 |
| Phone | 8 | 6 |
| Link | 7 | 5 |
| Promo code | 8 | 6 |
| **Scored pairs** | **53** | **40** |
