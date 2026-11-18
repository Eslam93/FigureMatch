# 0004. Model-provider failures are one typed family with fixed responses

- **Status:** Accepted
- **Decided:** 2026-11-07, merged in [#155](https://github.com/Eslam93/FigureMatch/pull/155)
- **Written:** 2026-11-18, after the fact, from the pull request and the code

## Context

There were two unrelated `ProviderError` classes. The text path's was never translated
into a response, so a timeout, a rate limit or a reply cut off at the length limit became
a generic 500. The image path's wrapped OpenAI's own error text into its 502 body.

## Decision

- One `ProviderError` family, in `app/providers/errors.py`, carries a kind: timeout, rate
  limited, quota exhausted, truncated output, content rejected, and so on.
- One handler maps each kind to a fixed status, error code and message. The upstream
  error text goes to the log, never into a response.
- A 429 caused by an exhausted quota (`insufficient_quota`) is not retried; other 429s,
  timeouts and 5xx are retried with backoff.

## Alternatives

None is recorded in the pull request.

## Consequences

- The frontend can show a specific message per code (`lib/errors/ai-codes.ts`).
- A failure the mapping does not know becomes a generic provider error, and its detail
  is only in the log.
