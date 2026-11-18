# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""A stand-in for the two OpenAI endpoints the backend calls.

The replay points the backend at this server through `OPENAI_BASE_URL`,
which the OpenAI SDK reads by itself, so no backend code is changed or
patched. It answers the way OpenAI does in the two respects the audit is
about, and nothing more:

  * model lifecycle: a model that `facts.SHUT_DOWN` says is shut down, or
    that is not on a live list, gets HTTP 404 `model_not_found`;
  * usage: every chat completion reports the same fixed token counts, so
    the cost a correct backend records is known in advance.

It keeps a log of what it was asked, which the probes read back from
`GET /__replay/requests`. Standard library only.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import facts

# Token counts every chat completion reports. Round on purpose: the
# arithmetic in the cost probe can be checked by eye.
PROMPT_TOKENS = 1000
COMPLETION_TOKENS = 1000
CACHED_PROMPT_TOKENS = 0

# A 1x1 transparent PNG.
_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6"
    "kgAAAABJRU5ErkJggg=="
)

# What the model "writes", keyed by the name of the JSON schema the backend
# asks for. Each satisfies the backend's own schema for that name.
_CANNED_JSON: dict[str, dict[str, Any]] = {
    "linkedin_post": {
        "hook": "A test that passes is a claim about the test, not about the code.",
        "body": (
            "We reread a small service six months after shipping it. Its suite "
            "was green and four defects were live. Each one was hidden by the "
            "way the suite was built, not by a missing test."
        ),
        "cta": "Pick one passing test and ask what it would take to make it fail.",
        "hashtags": ["testing", "softwareengineering"],
    },
    "image_prompt": {
        "prompt": "An open paper ledger on a plain desk in soft daylight, seen from above.",
        "negative_prompt": "text, watermark, logos",
        "style_summary": "Quiet photorealistic still life.",
    },
}


def _today() -> date:
    return datetime.now(timezone.utc).date()


class _Handler(BaseHTTPRequestHandler):
    server: FakeOpenAIServer

    # ── plumbing ───────────────────────────────────────────────────────

    def log_message(self, format: str, *args: Any) -> None:
        return  # the request log below is the record; keep stderr quiet

    def _send_json(self, status: int, body: dict[str, Any] | list[Any]) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        parsed = json.loads(raw or b"{}")
        return parsed if isinstance(parsed, dict) else {}

    def _refuse_model(self, path: str, model: str) -> None:
        """Answer 404 `model_not_found`, as OpenAI does for a model it has
        shut down or has never heard of."""
        if facts.is_shut_down(model, on=_today()):
            message = (
                f"The model `{model}` has been deprecated, learn more here: "
                "https://platform.openai.com/docs/deprecations"
            )
        else:
            message = f"The model `{model}` does not exist or you do not have access to it."
        self.server.record(path=path, model=model, status=404, error_code="model_not_found")
        self._send_json(
            404,
            {
                "error": {
                    "message": message,
                    "type": "invalid_request_error",
                    "param": None,
                    "code": "model_not_found",
                }
            },
        )

    # ── routes ─────────────────────────────────────────────────────────

    def do_GET(self) -> None:
        if self.path == "/__replay/requests":
            self._send_json(200, self.server.requests())
            return
        self._send_json(404, {"error": {"message": "not found", "code": "not_found"}})

    def do_POST(self) -> None:
        body = self._read_json()
        model = str(body.get("model", ""))
        if self.path == "/v1/chat/completions":
            if model in facts.LIVE_TEXT_MODELS:
                self._chat_completion(body, model)
            else:
                self._refuse_model(self.path, model)
            return
        if self.path == "/v1/images/generations":
            if model in facts.LIVE_IMAGE_MODELS:
                self._image(model)
            else:
                self._refuse_model(self.path, model)
            return
        self._send_json(404, {"error": {"message": "not found", "code": "not_found"}})

    def _chat_completion(self, body: dict[str, Any], model: str) -> None:
        response_format = body.get("response_format") or {}
        schema_name = (response_format.get("json_schema") or {}).get("name", "")
        canned = _CANNED_JSON.get(schema_name)
        content = json.dumps(canned) if canned is not None else "ok"
        self.server.record(path=self.path, model=model, status=200, schema_name=schema_name)
        self._send_json(
            200,
            {
                "id": "chatcmpl-replay",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content, "refusal": None},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": PROMPT_TOKENS,
                    "completion_tokens": COMPLETION_TOKENS,
                    "total_tokens": PROMPT_TOKENS + COMPLETION_TOKENS,
                    "prompt_tokens_details": {"cached_tokens": CACHED_PROMPT_TOKENS},
                },
            },
        )

    def _image(self, model: str) -> None:
        self.server.record(path=self.path, model=model, status=200)
        self._send_json(
            200,
            {
                "created": int(time.time()),
                "data": [{"b64_json": _PNG_B64}],
                "usage": {
                    "input_tokens": 50,
                    "input_tokens_details": {"text_tokens": 50, "image_tokens": 0},
                    "output_tokens": 1056,
                    "total_tokens": 1106,
                },
            },
        )


class FakeOpenAIServer(ThreadingHTTPServer):
    """Listens on 127.0.0.1 on a free port; `base_url` is what to hand the SDK."""

    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self._log: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"

    @property
    def base_url(self) -> str:
        return f"{self.origin}/v1"

    def record(self, **entry: Any) -> None:
        with self._lock:
            self._log.append(entry)

    def requests(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._log)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self.shutdown()
        self.server_close()
