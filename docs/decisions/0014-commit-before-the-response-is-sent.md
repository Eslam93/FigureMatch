# 0014. Auth writes are committed before the response is sent

- **Status:** Accepted
- **Decided:** 2026-11-18
- **Written:** 2026-11-18

## Context

The request's session commits in `get_db_session`, after the endpoint returns. FastAPI
gives a dependency with `yield` the scope `"request"` by default, and in that scope the
code after `yield` runs after the response has been sent. So the four routes that rely on
that commit (register, login, refresh and logout) answered before their writes were
committed. Every other write route commits explicitly before it returns.

A client that used what it was just given could arrive before the commit: a new user's
first request could find no user, and a fresh refresh token could be refused. If the
commit itself failed, the client would already hold tokens for writes that never landed.
Both the May code and the code before this decision lock FastAPI 0.136.1.

The audit replay found it. On 18 November 2026, in a `numbers` run on GitHub's runner,
the May code's image probe registered a user and was refused on its very next request:
`401 "Authenticated user no longer exists"`. Driving the app's ASGI interface directly
then showed, for all four routes, the last byte of the response sent before the commit.

## Decision

`DbSession` declares `Depends(get_db_session, scope="function")`. In that scope FastAPI
runs the code after `yield`, and so the commit or the rollback, when the endpoint
returns and before the response is sent. Every route takes its session through
`DbSession`, so the change covers all of them.

`tests/integration/test_commit_before_response.py` records the order of the commit and
the last byte of the response for register, login, refresh and logout. It fails without
the change, with `['response sent', 'commit']`, and passes with it.

## Alternatives

An explicit `await db.commit()` at the end of each of the four routes, as the other write
routes do. It works, but it leaves the default in place for the next route that forgets.

## Consequences

- The session is closed before the response is sent, so a response cannot lazy-load from
  it. Responses are built from Pydantic models inside the endpoint, and the full suite
  passes.
- The audit replay's probes still wait for each write to land before their next step,
  because the May code they also run keeps the race.
