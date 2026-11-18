# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Unit tests for `LocalImageStorage` and the `public_url_for` contract.

The Slice 3 storage layer originally returned `(key, url)` and the
service persisted the absolute URL on the row. The hardening pass
split that: `store` returns the key only, and `public_url_for(key)`
is a pure derivation called at projection time. That way an
`IMAGES_CDN_BASE_URL` flip rewrites every row's wire URL without a
data migration.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.image_storage import LocalImageStorage


@pytest.mark.asyncio
async def test_store_returns_key_with_correct_extension(tmp_path: Path) -> None:
    storage = LocalImageStorage(base_url="http://x/y", directory=tmp_path)
    key = await storage.store(image_bytes=b"\x89PNG\r\n\x1a\n")
    assert key.endswith(".png")
    assert (tmp_path / key).read_bytes() == b"\x89PNG\r\n\x1a\n"


@pytest.mark.asyncio
async def test_public_url_for_combines_base_and_key(tmp_path: Path) -> None:
    storage = LocalImageStorage(base_url="https://cdn.example.com", directory=tmp_path)
    assert storage.public_url_for("abc.png") == "https://cdn.example.com/abc.png"


@pytest.mark.asyncio
async def test_public_url_for_trims_trailing_slash(tmp_path: Path) -> None:
    storage = LocalImageStorage(base_url="https://cdn.example.com/", directory=tmp_path)
    assert storage.public_url_for("abc.png") == "https://cdn.example.com/abc.png"


def test_public_url_for_empty_base_returns_bare_key(tmp_path: Path) -> None:
    """An empty `IMAGES_CDN_BASE_URL` indicates a misconfigured deploy.
    We return the bare key so `<img src="...">` breaks loudly rather
    than silently serving the wrong asset."""
    storage = LocalImageStorage(base_url="", directory=tmp_path)
    assert storage.public_url_for("abc.png") == "abc.png"


@pytest.mark.asyncio
async def test_keys_are_unique_across_calls(tmp_path: Path) -> None:
    storage = LocalImageStorage(base_url="http://x", directory=tmp_path)
    keys = {await storage.store(image_bytes=b"a") for _ in range(5)}
    assert len(keys) == 5
