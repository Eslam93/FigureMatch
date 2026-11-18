# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""The four probes of the November 2026 audit.

Each probe states what a correct backend does, drives a running backend
over HTTP only, and reports one of three verdicts:

  pass   the backend behaved correctly
  fail   the backend showed the defect the probe is written for
  error  something else happened, so the probe proves nothing either way

Nothing here imports backend code or reads its database, so the same file
runs against any version of the backend that serves the same routes.
Standard library only.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import facts
import fake_openai

_PASSWORD = "ReplayProbe2026"  # letters and digits: accepted by the backend
_SIX_PLACES = Decimal("0.000001")  # the backend stores cost to six decimal places

# The May code answers register, login, refresh and logout before it commits
# them (a fifth defect, found by this replay; see audit/README.md). So a
# probe waits for a write to land before its next step, and the race cannot
# decide a verdict. A registration is waited for by polling /auth/me; a
# refresh token's rotation has nothing to poll without spending the token,
# so the probe waits a fixed time, hundreds of times longer than a commit.
_VISIBLE_WITHIN_SECONDS = 10.0
_SETTLE_SECONDS = 0.5

# No proxy: every request goes to 127.0.0.1.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


# ── HTTP ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Reply:
    status: int
    text: str
    refresh_cookie: str | None

    def json(self) -> Any:
        return json.loads(self.text)

    def error_code(self) -> str | None:
        try:
            code = self.json()["error"]["code"]
        except (ValueError, KeyError, TypeError):
            return None
        return str(code)


def _refresh_cookie(headers: Any) -> str | None:
    for value in headers.get_all("Set-Cookie") or []:
        name, _, cookie = value.split(";", 1)[0].partition("=")
        if name.strip() == "refresh_token" and cookie.strip('"'):
            return str(cookie.strip('"'))
    return None


def call(
    method: str,
    url: str,
    *,
    body: dict[str, Any] | None = None,
    bearer: str | None = None,
    refresh_cookie: str | None = None,
) -> Reply:
    headers = {"Accept": "application/json", "User-Agent": "audit-replay"}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    if refresh_cookie:
        headers["Cookie"] = f"refresh_token={refresh_cookie}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with _OPENER.open(request, timeout=120) as response:
            return Reply(
                status=response.status,
                text=response.read().decode("utf-8", "replace"),
                refresh_cookie=_refresh_cookie(response.headers),
            )
    except urllib.error.HTTPError as exc:
        return Reply(
            status=exc.code,
            text=exc.read().decode("utf-8", "replace"),
            refresh_cookie=_refresh_cookie(exc.headers),
        )


# ── results ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Target:
    """Where the backend under test and the OpenAI stand-in listen."""

    api: str  # e.g. http://127.0.0.1:8001/api/v1
    openai_origin: str  # e.g. http://127.0.0.1:9001


@dataclass
class Result:
    probe: str
    defect: str  # the defect, as the README words it
    correct: str  # what a correct backend does
    verdict: str = "error"
    observed: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProbeError(Exception):
    """A step the probe depends on did not behave as any version should."""


def _expect(reply: Reply, status: int, step: str) -> None:
    if reply.status != status:
        raise ProbeError(f"{step}: expected HTTP {status}, got {reply.status}: {reply.text[:300]}")


def _register(target: Target, label: str) -> Reply:
    reply = call(
        "POST",
        f"{target.api}/auth/register",
        body={
            "email": f"replay-{label}-{uuid.uuid4().hex[:12]}@example.com",
            "password": _PASSWORD,
            "full_name": "Replay Probe",
        },
    )
    _expect(reply, 201, "register")
    _wait_until_registered(target, reply.json()["access_token"])
    return reply


def _wait_until_registered(target: Target, bearer: str) -> None:
    """Return once the new user is committed and visible to other requests."""
    deadline = time.monotonic() + _VISIBLE_WITHIN_SECONDS
    while True:
        me = call("GET", f"{target.api}/auth/me", bearer=bearer)
        if me.status == 200:
            return
        if time.monotonic() > deadline:
            raise ProbeError(
                f"the registered user was not visible after {_VISIBLE_WITHIN_SECONDS}s"
            )
        time.sleep(0.05)


def _generate_text(target: Target, bearer: str) -> Reply:
    reply = call(
        "POST",
        f"{target.api}/content/generate",
        bearer=bearer,
        body={
            "content_type": "linkedin_post",
            "topic": "What a passing test suite does and does not tell you",
        },
    )
    _expect(reply, 200, "generate a LinkedIn post")
    return reply


def _openai_requests(target: Target) -> list[dict[str, Any]]:
    reply = call("GET", f"{target.openai_origin}/__replay/requests")
    _expect(reply, 200, "read the stand-in's request log")
    return list(reply.json())


# ── probe 1: a stolen refresh token ────────────────────────────────────


def _stolen_refresh_token(target: Target, result: Result) -> None:
    original = _register(target, "token").refresh_cookie
    if not original:
        raise ProbeError("register set no refresh_token cookie")

    # The thief uses the stolen token first and receives its successor.
    thief = call("POST", f"{target.api}/auth/refresh", refresh_cookie=original)
    _expect(thief, 200, "first use of the refresh token")
    if not thief.refresh_cookie:
        raise ProbeError("refresh set no new refresh_token cookie")
    time.sleep(_SETTLE_SECONDS)  # let the rotation commit; see _SETTLE_SECONDS

    # The owner then presents the same token. It is spent, so this is reuse.
    owner = call("POST", f"{target.api}/auth/refresh", refresh_cookie=original)
    _expect(owner, 401, "second use of the same refresh token")

    # Does the thief's token still work?
    after = call("POST", f"{target.api}/auth/refresh", refresh_cookie=thief.refresh_cookie)
    result.evidence = {
        "reuse_status": owner.status,
        "reuse_code": owner.error_code(),
        "thief_token_status_after_reuse": after.status,
        "thief_token_code_after_reuse": after.error_code(),
    }
    if after.status == 401:
        result.verdict = "pass"
        result.observed = "After the reuse, the thief's token was refused (401)."
    elif after.status == 200:
        result.verdict = "fail"
        result.observed = (
            "The reuse was answered with 401, yet the thief's token was still "
            "accepted afterwards (200) and exchanged for a new one."
        )
    else:
        raise ProbeError(f"thief's token after reuse: unexpected HTTP {after.status}")


# ── probe 2: the recorded cost of a text generation ────────────────────


def _text_cost(target: Target, result: Result) -> None:
    bearer = _register(target, "cost").json()["access_token"]
    usage = _generate_text(target, bearer).json()["usage"]
    model = usage["model_id"]
    input_tokens, output_tokens = usage["input_tokens"], usage["output_tokens"]
    if model not in facts.TEXT_PRICES_PER_MILLION:
        raise ProbeError(f"no published price on file for model {model!r}")
    sent = (fake_openai.PROMPT_TOKENS, fake_openai.COMPLETION_TOKENS)
    if (input_tokens, output_tokens) != sent:
        raise ProbeError(
            f"backend reported {input_tokens}/{output_tokens} tokens; "
            f"the stand-in sent {sent[0]}/{sent[1]}"
        )

    recorded = Decimal(str(usage["cost_usd"])).quantize(_SIX_PLACES)
    expected = facts.text_cost_usd(
        model,
        input_tokens=input_tokens,
        cached_input_tokens=fake_openai.CACHED_PROMPT_TOKENS,
        output_tokens=output_tokens,
    ).quantize(_SIX_PLACES)
    result.evidence = {
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "published_usd_per_million": {
            k: str(v) for k, v in facts.TEXT_PRICES_PER_MILLION[model].items()
        },
        "price_source": facts.PRICING_URL,
        "price_read_on": facts.READ_ON.isoformat(),
        "expected_cost_usd": str(expected),
        "recorded_cost_usd": str(recorded),
    }
    tokens = f"{input_tokens} input and {output_tokens} output tokens of {model}"
    if recorded == expected:
        result.verdict = "pass"
        result.observed = f"{tokens} were recorded at ${recorded}, the published price."
        return
    result.verdict = "fail"
    result.observed = f"{tokens} were recorded at ${recorded}; the published price is ${expected}"
    if recorded > 0:
        ratio = (expected / recorded).quantize(Decimal("0.01"))
        result.evidence["expected_over_recorded"] = str(ratio)
        result.observed += f", {ratio} times as much."
    else:
        result.observed += "."


# ── probe 3: the default image model ───────────────────────────────────


def _default_image_model(target: Target, result: Result) -> None:
    today = datetime.now(timezone.utc).date()
    bearer = _register(target, "image").json()["access_token"]
    content_id = _generate_text(target, bearer).json()["content_id"]

    seen_before = len(_openai_requests(target))
    image = call(
        "POST",
        f"{target.api}/content/{content_id}/image",
        bearer=bearer,
        body={"style": "photorealistic"},
    )
    image_calls = [
        entry
        for entry in _openai_requests(target)[seen_before:]
        if entry["path"] == "/v1/images/generations"
    ]
    asked_for = [entry["model"] for entry in image_calls]
    shut_down = sorted({m for m in asked_for if facts.is_shut_down(m, on=today)})
    result.evidence = {
        "image_models_requested": asked_for,
        "openai_answers": [entry["status"] for entry in image_calls],
        "backend_status": image.status,
        "backend_error_code": image.error_code(),
        "shutdown_dates": {m: facts.SHUT_DOWN[m].isoformat() for m in shut_down},
        "shutdown_source": facts.DEPRECATIONS_URL,
        "checked_on": today.isoformat(),
    }
    if image.status in (200, 201) and asked_for and not shut_down:
        result.verdict = "pass"
        result.observed = f"The backend asked for {asked_for[-1]} and returned an image."
    elif shut_down:
        model = shut_down[0]
        result.verdict = "fail"
        result.observed = (
            f"The backend asked for {model}, which OpenAI shut down on "
            f"{facts.SHUT_DOWN[model].isoformat()}. The API answered 404 and the "
            f"backend returned HTTP {image.status} ({image.error_code()})."
        )
    else:
        raise ProbeError(
            f"image request returned HTTP {image.status}; the stand-in saw image "
            f"calls for {asked_for}: {image.text[:300]}"
        )


# ── probe 4: what a 422 says back ──────────────────────────────────────


def _rejected_password_echo(target: Target, result: Result) -> None:
    # Letters only, so the strength rule (a letter and a digit) rejects it.
    letters = "".join(c for c in uuid.uuid4().hex if c.isalpha())
    password = f"Rejected{letters}Password"
    reply = call(
        "POST",
        f"{target.api}/auth/register",
        body={
            "email": f"replay-echo-{uuid.uuid4().hex[:12]}@example.com",
            "password": password,
            "full_name": "Replay Probe",
        },
    )
    _expect(reply, 422, "register with a password the strength rule rejects")
    echoed = password in reply.text
    result.evidence = {
        "status": reply.status,
        "error_code": reply.error_code(),
        "response_contains_submitted_password": echoed,
    }
    if echoed:
        result.verdict = "fail"
        result.observed = "The 422 body contained the submitted password, character for character."
    else:
        result.verdict = "pass"
        result.observed = "The 422 body did not contain the submitted password."


# ── registry ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Probe:
    name: str
    defect: str
    correct: str
    run: Callable[[Target, Result], None]


PROBES: tuple[Probe, ...] = (
    Probe(
        name="stolen-refresh-token",
        defect="A stolen refresh token stayed valid because its revocation was rolled back.",
        correct=(
            "When a refresh token that was already used is presented again, every "
            "refresh token of that user stops working, including the one a thief "
            "obtained with it."
        ),
        run=_stolen_refresh_token,
    ),
    Probe(
        name="text-cost",
        defect="Text costs were recorded 5 to 7.5 times too low.",
        correct=(
            "The cost recorded for a generation equals the tokens OpenAI reported "
            "multiplied by the prices OpenAI publishes for that model."
        ),
        run=_text_cost,
    ),
    Probe(
        name="default-image-model",
        defect="OpenAI had shut down the default image model.",
        correct=(
            "With no model configured, generating an image succeeds: the default "
            "image model is one OpenAI still serves."
        ),
        run=_default_image_model,
    ),
    Probe(
        name="rejected-password-echo",
        defect="422 responses echoed back a rejected password.",
        correct="A response that rejects a submitted password does not contain that password.",
        run=_rejected_password_echo,
    ),
)


def run_all(target: Target) -> list[Result]:
    """Run every probe. A probe that cannot reach a verdict reports `error`."""
    results: list[Result] = []
    for probe in PROBES:
        result = Result(probe=probe.name, defect=probe.defect, correct=probe.correct)
        try:
            probe.run(target, result)
        except Exception as exc:  # anything unexpected is an `error` verdict
            result.verdict = "error"
            result.observed = f"{type(exc).__name__}: {exc}"
        results.append(result)
    return results
