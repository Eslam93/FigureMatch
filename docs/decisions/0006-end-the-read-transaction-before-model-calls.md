# 0006. No database transaction stays open across a model call

- **Status:** Accepted, except on the image path
- **Decided:** 2026-11-07, merged in [#155](https://github.com/Eslam93/FigureMatch/pull/155)
- **Written:** 2026-11-18, after the fact, from the pull request and the code

## Context

Reading the current user or a brand voice opens a transaction implicitly. It stayed open,
idle in a pooled connection, for the whole model call that followed, which takes seconds
to tens of seconds. The pool holds 10 connections plus 10 overflow, so about 20
generations at once could take every connection. That figure is reasoned from the pool
size; it was not measured.

## Decision

Content generation and both improver stages commit the read transaction
(`end_read_transaction` in `app/db/session.py`) before every call to a model provider.
Loaded objects stay usable, and the next query opens a new transaction.

## Alternatives

None is recorded in the pull request.

## Consequences

- The image path still holds a row lock (`SELECT … FOR UPDATE NOWAIT`) and its connection
  across the prompt call, the image call and the upload, so a second request for the same
  piece gets a 409 at once. Removing that needs a schema change, which was left for later.
- `end_read_transaction` commits whatever the transaction holds, so it is safe only where
  nothing has been written yet.
