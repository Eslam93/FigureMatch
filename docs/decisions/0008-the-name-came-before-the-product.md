# 0008. The project is named for a figure checker that is not built

- **Status:** Accepted; what the name promises is open
- **Decided:** 2026-11-07, merged in [#157](https://github.com/Eslam93/FigureMatch/pull/157)
- **Written:** 2026-11-18, after the fact, from the pull request and the code

## Context

The repository was called MagnaCMS. Its owner intends it to carry, possibly, a bilingual
Arabic and English figure checker: something that confirms every price, rate, date,
phone number, link and promo code in an Arabic version matches the English original.
None of that existed.

## Decision

The repository and every name in the tree became FigureMatch: documents, application
titles, package names, CDK stack and resource names, container names and seed data. Git
history keeps the old name.

On 18 November the README was rewritten to say plainly that the checker is not built, and
the page title says "content studio", because the code holds nothing the bare name would
describe.

## Alternatives

None is recorded in the pull request.

## Consequences

- Until the checker exists, the name promises something the code does not do. The
  README's first lines say so, so that a reader is not misled.
- Whether the checker is built at all is decided by the measurement in
  [0010](./0010-measure-before-building-the-checker.md). If it is not built, the name
  should be reconsidered.
- The repository's description on GitHub, which is not part of the tree, still said on
  18 November that the project "is being rebuilt" into the checker.
