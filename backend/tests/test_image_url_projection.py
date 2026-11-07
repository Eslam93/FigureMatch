"""Pin the projection rule: image URL is computed fresh from
`s3_key` + storage config, NEVER read from the persisted `cdn_url`.

Round 1 refactored the storage layer so `cdn_url` is no longer the
source of truth — it's persisted on insert as a redundant cache for
backwards compatibility. The router projection at
`routers/content.py` reads `image.s3_key` and calls
`storage.public_url_for(...)`, which means a future change to
`IMAGES_CDN_BASE_URL` rewrites every row's wire URL with no DB
migration. This test asserts that contract by feeding the projector
a row whose `cdn_url` would be wrong if anyone ever re-read it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.api.v1.routers.content import _project_image
from app.db.enums import ImageProvider


class _FakeStorage:
    """Same protocol shape as `LocalImageStorage`. Constructs URLs
    from a controlled base so the test can assert the URL came from
    storage, not from the row."""

    base = "https://fresh-cdn.example.com"

    async def store(self, *, image_bytes: bytes, extension: str = "png") -> str:  # pragma: no cover
        raise NotImplementedError("not exercised by this test")

    def public_url_for(self, key: str) -> str:
        return f"{self.base}/{key}"


def _row(**overrides: Any) -> Any:
    """Build a row-shaped object the projector can read from. Using a
    bare namespace keeps the test independent of SQLAlchemy fixtures."""
    base: dict[str, Any] = {
        "id": uuid.uuid4(),
        "content_piece_id": uuid.uuid4(),
        "style": "photorealistic",
        "provider": ImageProvider.OPENAI,
        "model_id": "gpt-image-2.5-flare",
        "width": 1024,
        "height": 1024,
        "s3_key": "abc123.png",
        # Deliberately stale — the projection MUST ignore this and
        # rebuild the URL from `s3_key` + the storage's base.
        "cdn_url": "https://stale-and-wrong.example.com/old-base/abc123.png",
        "image_prompt": "...",
        "negative_prompt": None,
        "cost_usd": 0,
        "is_current": True,
        "created_at": datetime.now(UTC),
    }
    base.update(overrides)
    return type("Row", (), base)()


def test_projection_uses_storage_public_url_for_not_row_cdn_url() -> None:
    response = _project_image(_row(), _FakeStorage())
    assert response.cdn_url == "https://fresh-cdn.example.com/abc123.png"
    # And specifically NOT the stale value on the row.
    assert "stale-and-wrong" not in response.cdn_url


def test_projection_rebuilds_url_when_storage_base_changes() -> None:
    """The whole point of the refactor: a config flip on
    `IMAGES_CDN_BASE_URL` rewrites every row's wire URL with no
    backfill. Simulated by swapping the storage instance."""
    row = _row()

    class _OtherStorage(_FakeStorage):
        base = "https://s3.us-east-1.amazonaws.com/figurematch-prod-images"

    first = _project_image(row, _FakeStorage())
    second = _project_image(row, _OtherStorage())
    assert first.cdn_url.startswith("https://fresh-cdn.example.com/")
    assert second.cdn_url.startswith("https://s3.us-east-1.amazonaws.com/")
    # Same row, two different storage configs, two different URLs —
    # which is the contract.
    assert first.cdn_url != second.cdn_url
