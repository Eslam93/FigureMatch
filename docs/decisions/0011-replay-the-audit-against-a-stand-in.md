# 0011. The audit is replayed against a stand-in for OpenAI, not the real API

- **Status:** Accepted
- **Decided:** 2026-11-18, commit `948fdce`
- **Written:** 2026-11-18

## Context

The README says the November audit found four defects behind a green test suite. A claim
like that should be checkable by a reader, on the May code and on today's, without trust
in the author and without an OpenAI account.

## Decision

- [`audit/replay/run.py`](../../audit/replay/run.py) installs each version of the backend
  from its own lockfile, gives it an empty database, and starts it on the model settings
  it shipped with.
- The backend reaches a local stand-in for OpenAI through `OPENAI_BASE_URL`, which the
  OpenAI SDK reads by itself. No backend code is imported, patched or mocked.
- The same four probes, over HTTP only, run against both versions. Each must fail on the
  May code and pass on the current code.
- The two facts about the outside world that the probes depend on, a published price and
  a shutdown date, are pinned in [`audit/replay/facts.py`](../../audit/replay/facts.py)
  with the page each came from.
- [`audit/replay/old_suite.py`](../../audit/replay/old_suite.py) reruns the May suite with
  per-test coverage, to answer whether the faulty lines were executed at all.
- The `audit-replay` workflow runs both on every change to `backend/` or `audit/`.

## Alternatives

Calling the real API was rejected: it costs money on every run, needs a key in CI, and
OpenAI no longer serves the May image model at all, so the May code could not be run as
it ran in May.

## Consequences

- The replay is only as right as `facts.py`. Its figures were read on 2026-11-06 and not
  read again when the replay was written.
- The probes were written after the fixes, knowing the answers. They replay the audit;
  they are not how the defects were found.
