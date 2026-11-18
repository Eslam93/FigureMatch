# 0012. CI commits the numbers it measured, because its logs expire

- **Status:** Accepted
- **Decided:** 2026-11-18
- **Written:** 2026-11-18

## Context

The last CI runs before the November audit were on 2 June 2026. Their status survives,
but their logs do not: GitHub answers `410 Gone` for the backend job's log, because
Actions logs expire. Nothing records how many tests those runs passed or what coverage
they measured. Numbers typed into a document by the author would be only as good as the
author's word.

## Decision

The `numbers` workflow runs every check that produces a number: the backend suite with
coverage, the frontend and infrastructure suites, `reuse lint`, the audit replay and the
gate's score. It writes the results, with the commit, the run's address and the tool
versions, to a dated file under [`numbers/`](../../numbers/). On `main`, CI commits that
file itself, as `github-actions[bot]`. On any other branch it only shows the file in the
run's summary.

## Alternatives

Keeping the numbers only in the logs, or as run artifacts, was rejected: both expire.

## Consequences

- Each push to `main` that changes code adds one commit by the bot.
- A number in `numbers/` was measured by GitHub's runner on the commit it names. It says
  nothing about any other commit.
