# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Per-path, per-IP in-memory rate limit middleware.

MVP-grade: a fixed-window counter keyed on `(rule_key, ip)` where
`rule_key` is either an exact-match path (`/api/v1/auth/login`) or the
pattern label of a regex-matched rule (`pattern:image_generate`).
The counters live in this process's memory: each backend process has
its own, and a restart clears them.

Scope:
  - Only the configured rules trigger limiting; everything else is a
    pass-through.
  - The "ip" identity is the real TCP peer (`scope["client"]`), NOT a
    forwarded-for header. Until we sit behind a proxy with a trusted
    XFF allowlist (P11.x), trusting client-supplied headers as security
    identity is a free DoS / impersonation vector. The audit-only XFF
    helper in `app/api/v1/routers/auth.py` is correctly NOT used here.

429 responses carry `Retry-After` (seconds) plus the project's standard
{error, meta} envelope.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from time import monotonic
from typing import Final

from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.request_context import get_request_id

# Window length. Matches the brief's "per minute" framing.
_WINDOW_SECONDS: Final[int] = 60

# Hard cap on the number of (rule_key, ip) buckets we'll keep in memory.
# Without this, an attacker spamming distinct source IPs would balloon
# memory. When the cap is hit, the LEAST-recently-touched key gets
# evicted.
_MAX_BUCKETS: Final[int] = 50_000


@dataclass(frozen=True)
class RateLimitRule:
    """A regex-matched rule for paths that vary at runtime (e.g.
    `/api/v1/content/<uuid>/image`).

    `key` is the bucket label persisted across requests — distinct
    rules must have distinct keys so two endpoints can't share the same
    counter by accident.
    """

    pattern: re.Pattern[str]
    limit: int
    key: str


class _Bucket:
    """A per-(rule_key, ip) sliding-window timestamp list plus an
    insertion-order hint for LRU eviction."""

    __slots__ = ("last_touch", "timestamps")

    def __init__(self) -> None:
        self.timestamps: list[float] = []
        self.last_touch: float = monotonic()


_BUCKETS: dict[tuple[str, str], _Bucket] = defaultdict(_Bucket)


def reset_rate_limit_state() -> None:
    """Wipe all bucket state. Tests call this between cases; production
    code never needs it."""
    _BUCKETS.clear()


def _prune_oldest_buckets_if_over_cap() -> None:
    """Evict the least-recently-touched buckets when the global cap is hit.

    Cheap-enough heuristic: at the cap, drop the oldest 10% in one
    pass to amortize the work.
    """
    if len(_BUCKETS) < _MAX_BUCKETS:
        return
    target_drops = _MAX_BUCKETS // 10
    sorted_items = sorted(_BUCKETS.items(), key=lambda kv: kv[1].last_touch)
    for key, _ in sorted_items[:target_drops]:
        _BUCKETS.pop(key, None)


def _envelope_429(retry_after: int) -> bytes:
    """Build the JSON body for a 429 response that matches the project's
    standard error envelope shape.
    """
    import json

    body = {
        "error": {
            "code": "RATE_LIMITED",
            "message": "Too many requests.",
            "details": {"retry_after_seconds": retry_after},
        },
        "meta": {"request_id": get_request_id()},
    }
    return json.dumps(body).encode("utf-8")


class RateLimitMiddleware:
    """ASGI middleware enforcing per-(rule, ip) request budgets.

    Construct with `rules` (exact-path → cap) and/or `patterns` (regex
    rules for dynamic paths). Exact-path lookup runs first; on a miss
    the patterns are scanned in order and the first match wins. Paths
    matched by neither are pass-through.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        rules: dict[str, int] | None = None,
        patterns: list[RateLimitRule] | None = None,
    ) -> None:
        self._app = app
        self._rules = rules or {}
        self._patterns = patterns or []

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        path = scope.get("path", "")
        resolved = self._resolve_rule(path)
        if resolved is None:
            await self._app(scope, receive, send)
            return
        rule_key, limit = resolved

        client = scope.get("client")
        ip = client[0] if client else "unknown"

        now = monotonic()
        bucket_key = (rule_key, ip)
        bucket = _BUCKETS[bucket_key]
        bucket.last_touch = now

        # Prune timestamps that fell out of the window.
        cutoff = now - _WINDOW_SECONDS
        while bucket.timestamps and bucket.timestamps[0] < cutoff:
            bucket.timestamps.pop(0)

        if len(bucket.timestamps) >= limit:
            retry_after = max(1, int(bucket.timestamps[0] + _WINDOW_SECONDS - now))
            body = _envelope_429(retry_after)
            await self._send_429(send, body=body, retry_after=retry_after)
            return

        bucket.timestamps.append(now)
        _prune_oldest_buckets_if_over_cap()
        await self._app(scope, receive, send)

    def _resolve_rule(self, path: str) -> tuple[str, int] | None:
        """Return `(bucket_key, limit)` for `path`, or None if no rule
        matches. Exact-path lookup wins over patterns to keep auth
        routes' identity stable across rule changes.
        """
        exact = self._rules.get(path)
        if exact is not None:
            return path, exact
        for rule in self._patterns:
            if rule.pattern.match(path):
                return rule.key, rule.limit
        return None

    @staticmethod
    async def _send_429(send: Send, *, body: bytes, retry_after: int) -> None:
        headers: list[tuple[bytes, bytes]] = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode("ascii")),
            (b"retry-after", str(retry_after).encode("ascii")),
        ]
        await send(
            {
                "type": "http.response.start",
                "status": 429,
                "headers": headers,
            }
        )
        await send({"type": "http.response.body", "body": body})
