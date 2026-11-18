# 0003. A 422 says which field failed and why, never what was submitted

- **Status:** Accepted
- **Decided:** 2026-11-07, merged in [#155](https://github.com/Eslam93/FigureMatch/pull/155)
- **Written:** 2026-11-18, after the fact, from the pull request and the code

## Context

The validation handler returned Pydantic's error objects as they came. Each carries an
`input` field holding the rejected value, plus `ctx` and `url`. A password rejected by
the strength rule came back in the 422 body, where anything that logs response bodies
keeps it. Two May tests posted a weak password and received it back; both checked only
the status and the error code.

## Decision

Each error in a 422 body keeps only `loc`, `msg` and `type`. The response envelope and
the `WEAK_PASSWORD` error code are unchanged.

## Alternatives

None is recorded in the pull request.

## Consequences

- A client cannot read back what it sent from the error, only where and why it failed.
- `msg` is Pydantic's message, which names limits but not values. A custom validator that
  put the value in its message would leak it again; none does today.

## Evidence

The `rejected-password-echo` probe in [`audit/replay/`](../../audit/replay/) fails on
the May code and passes from this pull request on.
