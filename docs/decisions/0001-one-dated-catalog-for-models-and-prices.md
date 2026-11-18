# 0001. Model ids, prices and shutdown dates live in one dated catalog

- **Status:** Accepted
- **Decided:** 2026-11-07, merged in [#154](https://github.com/Eslam93/FigureMatch/pull/154)
- **Written:** 2026-11-18, after the fact, from the pull request and the code

## Context

Two defects had the same root. Text costs were computed from a price table typed into
the provider module, which held $0.15 and $0.60 per million tokens for `gpt-5.4-mini`
where OpenAI charges $0.75 and $4.50. Every recorded text cost was 5 to 7.5 times too
low. And the default image model, `gpt-image-1`, was shut down by OpenAI on 2026-10-23;
nothing in the repository knew a model could have a shutdown date, so image generation
on the shipped default failed from that day.

The test suite passed throughout. Its one cost test computed the expected value from the
same wrong prices, and every image test used a mock client. See [`audit/`](../../audit/).

## Decision

- Every model id, price and shutdown date lives in
  [`backend/app/core/model_catalog.py`](../../backend/app/core/model_catalog.py), each
  entry with the date it was read and the OpenAI page it was read from.
- Cached input tokens bill at the cached rate. GPT Image models bill per token from the
  response's `usage`; a labelled per-image estimate is used only when `usage` is missing.
- The backend checks both configured models against the catalog at boot, in `openai`
  mode. A shut-down model stops it in every environment. An unknown, wrong-kind or
  unpriced model stops it outside `local`.
- A weekly CI job, `model-lifecycle`, fails if a configured model is unknown, unpriced,
  shut down, due to shut down within 30 days, or listed on OpenAI's deprecations page. It
  also fails when that page cannot be fetched or read, so a blind check cannot pass.
- The default image model became `gpt-image-2.5-flare`, which OpenAI names as the
  replacement.

## Alternatives

None is recorded in the pull request.

## Consequences

- A price change at OpenAI is not noticed automatically. The catalog must be read again
  by hand; its `verified_on` dates say how old each figure is.
- The weekly job reads an HTML page, so it fails loudly when OpenAI changes the page's
  layout. That is intended: a check that cannot see must not pass.
- Its first two scheduled runs, on 9 and 16 November 2026, passed.

## Evidence

The `text-cost` and `default-image-model` probes in [`audit/replay/`](../../audit/replay/)
fail on the May code and pass from this pull request on.
