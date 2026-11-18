# 0002. Reuse revocation is committed before the 401, and tests run the real session handling

- **Status:** Accepted
- **Decided:** 2026-11-07, merged in [#155](https://github.com/Eslam93/FigureMatch/pull/155)
- **Written:** 2026-11-18, after the fact, from the pull request and the code

## Context

Refresh tokens are single-use. When a token that was already used is presented again,
the backend treats it as stolen and revokes every refresh token the user holds, then
answers 401. The request's database session rolls back on any exception, and the 401 is
an exception, so the revocation was undone. A thief who used a stolen token first kept a
working token chain.

The May suite had a test for exactly this, and it passed: its fixture handed every request
the test's own session, which never committed or rolled back, so the rollback that undid
the revocation never ran under test.

## Decision

- The reuse handler commits the revocation itself, before the 401 is raised.
- The integration tests run the real `get_db_session`: each request gets its own session
  that commits on success and rolls back on error, nested in a savepoint the test
  discards. The fixture's docstring says not to go back to a bare-`yield` override.
- CI sets `REQUIRE_DB=1`, so a missing Postgres fails the integration suite instead of
  skipping it.

## Alternatives

None is recorded in the pull request.

## Consequences

- Two browser tabs that refresh at the same moment look exactly like reuse, so the user
  is signed out on every device. That was already the documented behaviour; it now
  happens. The frontend shares one refresh request per tab, not across tabs.
- Any other handler that writes and then raises has the same trap. Committing early is
  correct here only because the revocation must survive the error.

## Evidence

The `stolen-refresh-token` probe in [`audit/replay/`](../../audit/replay/) fails on the
May code and passes from this pull request on. `audit/replay/old_suite.py` swaps only the
fixture file from this pull request into the May code, and the May reuse test then fails:
`assert 200 == 401`.
