# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Image storage abstraction.

Two implementations live behind one Protocol:

  - `LocalImageStorage` (default in dev) writes bytes to a local
    directory and returns a storage key. The mounted `/local-images/*`
    static path serves them; the public URL is derived at read time
    from `settings.images_cdn_base_url` + the key, NOT persisted on
    the row. That decouples the URL from the row, so a future S3
    cutover that only changes `IMAGES_CDN_BASE_URL` requires no row
    backfill.
  - `S3ImageStorage` (placeholder) — wires through to boto3 and a
    presigned URL once the deploy story is ready. Not part of this
    slice's local-first contract.

`build_image_storage()` picks the right one based on
`IMAGES_CDN_BASE_URL`. The image service consumes only the Protocol
so swapping is a config change.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

# Slice 3 ships local-disk storage only. Filenames are UUIDv4 so two
# tests/demos never collide. The directory is created lazily on first
# write — keeps the test suite from needing fixtures.
LOCAL_IMAGES_DIR: Path = Path(__file__).resolve().parents[2] / "local_images"


class IImageStorage(Protocol):
    """Write-then-return-key surface. Implementations decide whether
    "write" means S3 PutObject or a local filesystem write. The
    callable URL is derived from `public_url_for(key)` so callers don't
    persist URLs on rows.
    """

    async def store(self, *, image_bytes: bytes, extension: str = "png") -> str:
        """Persist `image_bytes` and return the storage key (filename
        for local, S3 object key for cloud). Callers never construct
        URLs themselves — they pass the key through `public_url_for`
        when projecting a row to the wire.
        """
        ...

    def public_url_for(self, key: str) -> str:
        """Return the public URL the frontend renders via
        `<img src=...>`. Implementations may presign / sign / decorate
        the key as needed. Pure function: same `key` always yields the
        same URL for a given configuration.
        """
        ...


class LocalImageStorage:
    """Write bytes to `LOCAL_IMAGES_DIR/<uuid>.<ext>` and serve via the
    `/local-images/*` mount declared in `app.main`. Public URL is
    derived at read time so an `IMAGES_CDN_BASE_URL` flip rewrites
    every row's URL without a DB migration.
    """

    def __init__(self, *, base_url: str, directory: Path | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._directory = directory or LOCAL_IMAGES_DIR

    async def store(self, *, image_bytes: bytes, extension: str = "png") -> str:
        self._directory.mkdir(parents=True, exist_ok=True)
        key = f"{uuid.uuid4().hex}.{extension.lstrip('.')}"
        path = self._directory / key
        path.write_bytes(image_bytes)
        log.info(
            "local_image_stored",
            key=key,
            bytes=len(image_bytes),
        )
        return key

    def public_url_for(self, key: str) -> str:
        # An empty base URL would produce `/<key>` — useful nowhere.
        # The router's public response projection should never hit this
        # branch in production; the env validator on `images_cdn_base_url`
        # is what guarantees it. Returning the bare key here keeps the
        # failure mode loud (broken `<img>`) rather than silently
        # serving the wrong asset.
        if not self._base_url:
            return key
        return f"{self._base_url}/{key}"


def build_image_storage() -> IImageStorage:
    """Pick the storage implementation based on settings.

    Today: local-disk for every environment. The hosted S3 path lands
    with the deploy batch.
    """
    settings = get_settings()
    return LocalImageStorage(base_url=settings.images_cdn_base_url)
