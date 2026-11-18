# 0005. The corrective retry keeps the strict schema and names the failing field

- **Status:** Accepted
- **Decided:** 2026-11-07, merged in [#155](https://github.com/Eslam93/FigureMatch/pull/155)
- **Written:** 2026-11-18, after the fact, from the pull request and the code

## Context

Structured output has three stages: ask for JSON under a strict schema, retry once if
the reply fails validation, and otherwise store the raw reply with a banner. In May the
retry dropped the strict schema and told the model its JSON was invalid. The usual
first-pass failure is valid JSON that breaks a limit the schema cannot express, such as
`meta_description` over 160 characters, so the paid retry was told about the wrong
problem and could fail the same way again.

## Decision

- Content generation and both improver stages retry under the same strict schema.
- The retry shows the model its reply and names each failing field with Pydantic's
  message, never the value.
- If the retry itself comes back cut off or filtered, the request does not fail: it
  falls back to stage 3 with the first attempt's reply, and every billed call is counted.
- The prompt versions moved to v2, because a row's `prompt_version` is the only record of
  which retry wording produced it.

## Alternatives

None is recorded in the pull request.

## Consequences

- A first reply that is cut off or filtered still fails the request with a typed error
  (see [0004](./0004-one-typed-family-of-provider-errors.md)); only the retry degrades.
- No one has measured how often the retry now succeeds. That needs real model calls.
