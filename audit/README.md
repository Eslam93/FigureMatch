# The November 2026 audit, replayed

The studio was built in two days in May 2026 and its test suite passed. Read again in
November, the code had four defects that the suite did not catch. This directory lets
you check that claim instead of taking it on trust:

- [`replay/run.py`](./replay/run.py) runs four probes against the May code and against
  today's. Each probe fails on the May code and passes on today's.
- [`replay/old_suite.py`](./replay/old_suite.py) reruns the May test suite on the May
  code and reports which tests executed each faulty line. Every one of them ran during
  that passing test run: the lines that do the faulty work ran inside named tests, and
  the two that only hold a wrong value, a price and a model name, ran when their module
  was imported.

Neither script calls OpenAI or needs a key.

## Run it

You need git, [uv](https://docs.astral.sh/uv/), Python 3.10 or later for the scripts
(the backends install their own 3.12), and a Postgres 13 or later server the scripts may create
databases on. They default to
`postgresql://app:app@localhost:5432/app`; pass `--database-url` for another.

```bash
# A throwaway Postgres, if you have none running:
docker run -d --name replay-pg -p 127.0.0.1:5432:5432 \
  -e POSTGRES_USER=app -e POSTGRES_PASSWORD=app -e POSTGRES_DB=app postgres:16

git fetch origin tag take-home-2026-05-16
python3 audit/replay/run.py          # about 15 seconds once dependencies are cached
python3 audit/replay/old_suite.py    # about 40 seconds
```

`run.py` exits 0 only when every probe fails on the first ref and passes on the second.
`--before` and `--after` take any ref, so you can watch one fix at a time:
`--after 57b57d8` is the tree after [#154](https://github.com/Eslam93/FigureMatch/pull/154),
`--after 3e1b333` the tree after [#155](https://github.com/Eslam93/FigureMatch/pull/155).

The [`audit-replay`](../.github/workflows/audit-replay.yml) workflow runs both scripts on
GitHub's runners, so there is a run that did not happen on the author's machine.

## What it printed

On 2026-11-18, against Postgres 16.15:

```
  before  take-home-2026-05-16 @ 52dc30b   expected: every probe fails, the defects are present
  after   HEAD @ 593bafc   expected: every probe passes

  probe                   before  after
  stolen-refresh-token    FAIL    PASS
  text-cost               FAIL    PASS
  default-image-model     FAIL    PASS
  rejected-password-echo  FAIL    PASS

  What each probe saw on take-home-2026-05-16 @ 52dc30b:
    stolen-refresh-token: The reuse was answered with 401, yet the thief's token was still accepted afterwards (200) and exchanged for a new one.
    text-cost: 1000 input and 1000 output tokens of gpt-5.4-mini-2026-03-17 were recorded at $0.000750; the published price is $0.005250, 7.00 times as much.
    default-image-model: The backend asked for gpt-image-1, which OpenAI shut down on 2026-10-23. The API answered 404 and the backend returned HTTP 502 (PROVIDER_ERROR).
    rejected-password-echo: The 422 body contained the submitted password, character for character.

  What each probe saw on HEAD @ 593bafc:
    stolen-refresh-token: After the reuse, the thief's token was refused (401).
    text-cost: 1000 input and 1000 output tokens of gpt-5.4-mini-2026-03-17 were recorded at $0.005250, the published price.
    default-image-model: The backend asked for gpt-image-2.5-flare and returned an image.
    rejected-password-echo: The 422 body did not contain the submitted password.

REPRODUCED: 4 of 4 probes fail on take-home-2026-05-16 @ 52dc30b and 4 of 4 pass on HEAD @ 593bafc.
```

Each probe changes verdict at the commit that fixed its defect and not before:

| Probe | `7e1673a` (June) | `57b57d8` (#154) | `3e1b333` (#155) |
|---|---|---|---|
| `stolen-refresh-token` | fail | fail | pass |
| `text-cost` | fail | pass | pass |
| `default-image-model` | fail | pass | pass |
| `rejected-password-echo` | fail | fail | pass |

## How the replay works

For each ref, `run.py` unpacks that ref's `backend/` with `git archive`, installs it from
its own lockfile, gives it an empty database, runs its migrations and starts it. It sets
five variables and no others: `ENVIRONMENT=local`, `AI_PROVIDER_MODE=openai`, a
placeholder `OPENAI_API_KEY`, `DATABASE_URL`, and `OPENAI_BASE_URL`. No model is named,
so each ref runs on the defaults it shipped with.

`OPENAI_BASE_URL` is read by the OpenAI SDK itself. It points the backend at
[`replay/fake_openai.py`](./replay/fake_openai.py), a stand-in for the two endpoints the
backend calls. No backend code is imported, patched or mocked.

The probes in [`replay/probes.py`](./replay/probes.py) speak HTTP to the backend and
nothing else. They are the same file for both refs. A probe reports `pass`, `fail` (the
defect it was written for) or `error` (anything else, which proves nothing either way).

## The four defects

The line numbers below are in the May code, tag
[`take-home-2026-05-16`](https://github.com/Eslam93/FigureMatch/tree/take-home-2026-05-16).
The May suite, rerun on that code on 2026-11-18, gives 331 passed and 86.84% line and
branch coverage.

| | Defect | Did the May suite run the faulty line? | What hid it |
|---|---|---|---|
| 1 | A stolen refresh token stayed valid | Yes: the revocation ran in 4 tests | The test fixture replaced the request's database session, so the rollback that undid the revocation never ran in a test |
| 2 | Text costs recorded 5 to 7.5 times too low | Yes: the wrong prices loaded at import, and the arithmetic using them ran in 8 tests | The one test of the figure computed its expected value from the same wrong prices |
| 3 | The default image model was shut down | Yes: the default loaded at import, and the call that sends it ran in 6 tests | Every test used a mock in place of OpenAI, and nothing read OpenAI's list of retired models |
| 4 | 422 responses echoed a rejected password | Yes: the line that returns the raw errors ran in 8 tests | The tests checked the status and the error code and never read the rest of the body |

### 1. A stolen refresh token stayed valid

Refresh tokens are single-use. Presenting one a second time means it was copied, so the
backend revokes every refresh token the user holds
([`auth_service.py` line 199](https://github.com/Eslam93/FigureMatch/blob/take-home-2026-05-16/backend/app/services/auth_service.py#L199)).
It then raises a 401. The request's database session rolls back on any error
([`session.py` line 87](https://github.com/Eslam93/FigureMatch/blob/take-home-2026-05-16/backend/app/db/session.py#L87)),
and that rollback undid the revocation. The thief's token went on working: it could be
exchanged for a fresh 30-day token, and that one for another.

**The probe.** Register. Use the refresh token once, as a thief would, and keep the new
token it returns. Present the original token again, as its owner would: 401. Then use
the thief's token. A correct backend refuses it. The May code accepts it.

**What hid it.** The May suite had this exact test:
[`test_refresh_reuse_revokes_entire_family`](https://github.com/Eslam93/FigureMatch/blob/take-home-2026-05-16/backend/tests/integration/test_auth_routes.py#L250-L288)
makes the same four requests and asserts the same 401. It passed. Its fixture
[overrode `get_db_session`](https://github.com/Eslam93/FigureMatch/blob/take-home-2026-05-16/backend/tests/integration/conftest.py#L98-L101)
with a function that hands every request the test's own session and never commits or
rolls back. Under test, nothing undid the revocation; in production, the rollback did.

`old_suite.py` shows this two ways. Four tests executed the revocation and six executed
the rollback, and no test executed both. The request's commit on success
([line 85](https://github.com/Eslam93/FigureMatch/blob/take-home-2026-05-16/backend/app/db/session.py#L85))
was executed by no test at all. Then it swaps in the fixture file from the fix, changes
nothing else, and reruns the May auth tests on the May code:

```
  pytest tests/integration/test_auth_routes.py: 1 failed, 19 passed
    FAILED tests/integration/test_auth_routes.py::test_refresh_reuse_revokes_entire_family
      E       assert 200 == 401
```

**The fix** ([#155](https://github.com/Eslam93/FigureMatch/pull/155)) commits the
revocation before raising, and makes the integration tests run the real session handling.

### 2. Text costs were recorded 5 to 7.5 times too low

The price table held $0.15 per million input tokens and $0.60 per million output tokens
for `gpt-5.4-mini`
([`openai_provider.py` lines 39 to 43](https://github.com/Eslam93/FigureMatch/blob/take-home-2026-05-16/backend/app/providers/llm/openai_provider.py#L39-L43)).
OpenAI charges $0.75 and $4.50: 5 times and 7.5 times as much.

**The probe.** Generate a LinkedIn post. The stand-in reports 1,000 input and 1,000
output tokens. At OpenAI's prices that costs $0.005250. The May code records $0.000750,
a seventh of it.

**What hid it.** One test checked the figure,
[`test_compute_cost_usd_for_known_model`](https://github.com/Eslam93/FigureMatch/blob/take-home-2026-05-16/backend/tests/providers/test_openai_llm.py#L54-L57),
and it computed its expected value from the same two numbers:

```python
# 1000 input + 500 output at $0.15/$0.60 per 1M.
cost = _compute_cost_usd("gpt-5.4-mini-2026-03-17", 1000, 500)
assert cost == pytest.approx((1000 * 0.15 + 500 * 0.60) / 1_000_000)
```

It tested the multiplication. Nothing compared the table with OpenAI's price list. The
other seven tests that ran the arithmetic asserted `cost_usd > 0` or nothing about cost.

**The fix** ([#154](https://github.com/Eslam93/FigureMatch/pull/154)) moves prices into
a dated catalog that names the page each figure came from, and bills cached input at its
own rate.

### 3. OpenAI had shut down the default image model

The default image model was `gpt-image-1`
([`config.py` line 184](https://github.com/Eslam93/FigureMatch/blob/take-home-2026-05-16/backend/app/core/config.py#L184)).
OpenAI shut it down on 2026-10-23. This was not wrong in May. It became wrong nearly
five months after the suite's last CI run, on 2 June, and from that day a backend on
the shipped default could not generate an image.

**The probe.** With no model configured, generate a piece of content and ask for its
image. A correct backend returns one. The May code asks for `gpt-image-1`, gets the
API's 404, and returns a 502.

**What hid it.** All six tests that reached the API call
([line 128](https://github.com/Eslam93/FigureMatch/blob/take-home-2026-05-16/backend/app/providers/image/openai_provider.py#L128))
passed in a
[`MagicMock` client](https://github.com/Eslam93/FigureMatch/blob/take-home-2026-05-16/backend/tests/providers/test_openai_image.py#L34-L37),
and the route tests ran on the mock provider. No test and no CI job sent a model name to
OpenAI or read its deprecations page. A suite that never looks outside cannot see a
change that happens outside, and this one would still pass today.

**The fix** ([#154](https://github.com/Eslam93/FigureMatch/pull/154)) changes the
default, makes the backend refuse to boot on a model the catalog records as shut down,
and adds a weekly CI job that reads OpenAI's deprecations page.

### 4. 422 responses echoed back a rejected password

The validation handler returned Pydantic's error list as it came
([`exceptions.py` line 175](https://github.com/Eslam93/FigureMatch/blob/take-home-2026-05-16/backend/app/core/exceptions.py#L175)).
Each Pydantic error carries an `input` field holding the rejected value. A password that
failed the strength rule came back in the response body, where anything that logs
response bodies keeps it.

**The probe.** Register with a password made of letters only, which the strength rule
rejects. The 422 must not contain it. The May code returns it character for character.

**What hid it.** Eight tests executed that line. Two of them posted a weak password,
[this one](https://github.com/Eslam93/FigureMatch/blob/take-home-2026-05-16/backend/tests/test_weak_password_error_code.py#L22-L41)
and
[this one](https://github.com/Eslam93/FigureMatch/blob/take-home-2026-05-16/backend/tests/integration/test_auth_routes.py#L61-L74),
and received it back. Both asserted the status and the error code, and stopped there.
No test in the suite reads `input`.

**The fix** ([#155](https://github.com/Eslam93/FigureMatch/pull/155)) keeps only `loc`,
`msg` and `type` from each error.

## What this does not show

- **It never contacts OpenAI.** Defects 2 and 3 are about the outside world: a published
  price and a shutdown date. The replay takes both from
  [`replay/facts.py`](./replay/facts.py), which names the OpenAI page for each. They
  were read on 2026-11-06, when the fixes were made, and not read again when the replay
  was written: that machine could not reach OpenAI's site. If a figure there is wrong,
  the verdict on those two probes is wrong with it.
- **The 404 is assumed, not observed.** The stand-in answers a request for a shut-down
  model with HTTP 404 `model_not_found`. No request was sent to OpenAI to confirm that
  is still what it returns for `gpt-image-1`.
- **The probes were written after the fixes**, on 2026-11-18, from reading both versions
  of the code. They replay the audit. They are not how the defects were found, and a
  probe written knowing the answer is weaker evidence than one written before it.
- **Four defects, not all of them.** These are the four the README names. Pull requests
  #154, #155 and #156 fixed others that are not replayed here.
- **One platform.** Run on Ubuntu 24.04 with Postgres 16.15, and on GitHub's
  `ubuntu-latest` runners. Not run on Windows or macOS.
