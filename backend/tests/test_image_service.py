"""Unit tests for `ImageService` — the three-stage orchestration loop.

Uses fake providers + in-memory session stand-ins (same pattern as
`test_content_service.py`) so the test runs without Postgres. The
integration test in `tests/integration/test_image_routes.py` covers
the wire-up with a real DB.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import NotFoundError, ValidationError
from app.db.enums import ImageProvider
from app.db.models import ContentPiece
from app.providers.errors import ProviderError, ProviderErrorKind
from app.providers.image.base import ImageQuality, ImageResult
from app.providers.llm.base import LLMResult
from app.services.image_service import ImageService

# ── fakes ──────────────────────────────────────────────────────────────


@dataclass
class _RecordingSession:
    added: list[Any] | None = None

    def __post_init__(self) -> None:
        self.added = []

    def add(self, obj: Any) -> None:
        assert self.added is not None
        self.added.append(obj)

    async def flush(self) -> None:
        return None

    async def refresh(self, obj: Any) -> None:
        return None

    async def execute(self, _stmt: Any) -> Any:
        # Used by `mark_others_not_current`. Pretend zero rows updated;
        # the in-memory stand-in doesn't model concurrent images.
        return _RecordingResult()


@dataclass
class _RecordingResult:
    def scalar_one_or_none(self) -> Any:
        return None

    def scalars(self) -> Any:
        return self

    def all(self) -> list[Any]:
        return []


class _FakeStorage:
    """Captures storage calls so tests assert on bytes-in / url-out.

    Matches the production `IImageStorage` protocol: `store` returns
    the key only; `public_url_for(key)` is the pure derivation. Tests
    that previously asserted on a returned URL now drive through the
    same projection path the router uses.
    """

    def __init__(self, *, base_url: str = "http://test/img") -> None:
        self.calls: list[bytes] = []
        self._base_url = base_url

    async def store(self, *, image_bytes: bytes, extension: str = "png") -> str:
        self.calls.append(image_bytes)
        return f"fake-{len(self.calls)}.{extension}"

    def public_url_for(self, key: str) -> str:
        return f"{self._base_url}/{key}"


def _llm_returning(payload: dict[str, Any]) -> AsyncMock:
    """Build an LLM mock that returns a single canned JSON payload."""
    mock = AsyncMock()
    mock.generate = AsyncMock(
        return_value=LLMResult(
            raw_text=json.dumps(payload),
            model="fake-llm",
            input_tokens=1,
            output_tokens=2,
            cost_usd=0.001,
            latency_ms=1,
            finish_reason="stop",
        )
    )
    return mock


def _image_provider(raw_bytes: bytes = b"\x89PNGfake", model: str = "fake-image") -> AsyncMock:
    mock = AsyncMock()
    mock.generate = AsyncMock(
        return_value=ImageResult(
            image_bytes=raw_bytes,
            width=128,
            height=128,
            model=model,
            quality=ImageQuality.MEDIUM,
            cost_usd=0.04,
            latency_ms=10,
            prompt_used="captured prompt",
        )
    )
    return mock


def _piece(
    *,
    rendered_text: str = "Some rendered content with plenty of words to summarize.",
) -> ContentPiece:
    return ContentPiece(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        content_type="blog_post",  # type: ignore[arg-type]
        topic="Test topic",
        tone=None,
        target_audience=None,
        brand_voice_id=None,
        prompt_version="blog_post.v1",
        system_prompt_snapshot="x",
        user_prompt_snapshot="y",
        result=None,
        rendered_text=rendered_text,
        result_parse_status="ok",  # type: ignore[arg-type]
        word_count=10,
        model_id="fake-llm",
        input_tokens=0,
        output_tokens=0,
        cost_usd=0,
    )


def _user() -> Any:
    return type("U", (), {"id": uuid.uuid4()})()


# ── tests ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unknown_style_raises_validation_error() -> None:
    session = _RecordingSession()
    service = ImageService(
        session,  # type: ignore[arg-type]
        llm_provider=_llm_returning({"prompt": "p", "negative_prompt": "", "style_summary": "s"}),
        image_provider=_image_provider(),
        storage=_FakeStorage(),
    )
    with pytest.raises(ValidationError) as excinfo:
        await service.generate_for_content(
            user=_user(),
            content_id=uuid.uuid4(),
            style="cubism",
        )
    assert excinfo.value.code == "UNSUPPORTED_IMAGE_STYLE"


@pytest.mark.asyncio
async def test_missing_content_raises_not_found(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    session = _RecordingSession()
    service = ImageService(
        session,  # type: ignore[arg-type]
        llm_provider=_llm_returning({"prompt": "p", "negative_prompt": "", "style_summary": "s"}),
        image_provider=_image_provider(),
        storage=_FakeStorage(),
    )

    async def _none(*_a, **_k):  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr(service._content_repo, "get_for_user", _none)
    with pytest.raises(NotFoundError) as excinfo:
        await service.generate_for_content(
            user=_user(),
            content_id=uuid.uuid4(),
            style="photorealistic",
        )
    assert excinfo.value.code == "CONTENT_NOT_FOUND"


@pytest.mark.asyncio
async def test_happy_path_persists_image_with_is_current_true(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    session = _RecordingSession()
    piece = _piece()
    storage = _FakeStorage()
    llm = _llm_returning(
        {
            "prompt": "A cinematic still life",
            "negative_prompt": "text, watermark",
            "style_summary": "cinematic still",
        }
    )
    image_provider = _image_provider(raw_bytes=b"\x89PNGreal-fake", model="gpt-image-2.5-flare")

    service = ImageService(
        session,  # type: ignore[arg-type]
        llm_provider=llm,
        image_provider=image_provider,
        storage=storage,
    )

    async def _piece_lookup(*_a, **_k):  # type: ignore[no-untyped-def]
        return piece

    async def _mark_others(_pid):  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr(service._content_repo, "get_for_user", _piece_lookup)
    monkeypatch.setattr(service._image_repo, "mark_others_not_current", _mark_others)

    image = await service.generate_for_content(
        user=_user(),
        content_id=piece.id,
        style="photorealistic",
    )
    assert image.is_current is True
    assert image.cdn_url.startswith("http://test/img/")
    assert image.image_prompt.startswith("A cinematic still life")
    assert "Avoid: text, watermark" in image.image_prompt
    assert image.provider == ImageProvider.OPENAI
    assert image.model_id == "gpt-image-2.5-flare"
    assert storage.calls == [b"\x89PNGreal-fake"]
    # Two upstream calls: LLM for prompt building, then image provider.
    assert llm.generate.await_count == 1
    assert image_provider.generate.await_count == 1


def _service_with_failing_image_provider(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> ImageService:
    image_provider = AsyncMock()
    image_provider.generate = AsyncMock(side_effect=error)
    service = ImageService(
        _RecordingSession(),  # type: ignore[arg-type]  # a stand-in, not an AsyncSession
        llm_provider=_llm_returning({"prompt": "p", "negative_prompt": "", "style_summary": "s"}),
        image_provider=image_provider,
        storage=_FakeStorage(),
    )
    piece = _piece()

    async def _piece_lookup(*_a: Any, **_k: Any) -> ContentPiece:
        return piece

    monkeypatch.setattr(service._content_repo, "get_for_user", _piece_lookup)
    return service


@pytest.mark.asyncio
async def test_provider_error_from_the_image_provider_propagates_unwrapped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The service used to re-wrap it as `Image provider failed: {exc}`,
    which carried the upstream text into the response and lost the kind."""
    error = ProviderError("OpenAI image call failed.", kind=ProviderErrorKind.CONTENT_REJECTED)
    service = _service_with_failing_image_provider(monkeypatch, error)

    with pytest.raises(ProviderError) as excinfo:
        await service.generate_for_content(
            user=_user(), content_id=uuid.uuid4(), style="minimalist"
        )

    assert excinfo.value is error


@pytest.mark.asyncio
async def test_unexpected_image_provider_exception_is_not_passed_off_as_a_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-provider exception is a bug: it propagates as is, to become a
    logged 500 rather than a 502 blaming the provider."""
    service = _service_with_failing_image_provider(monkeypatch, KeyError("b64_json"))

    with pytest.raises(KeyError):
        await service.generate_for_content(
            user=_user(), content_id=uuid.uuid4(), style="minimalist"
        )


@pytest.mark.asyncio
async def test_llm_parse_failure_falls_back_to_default_prompt(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """When the LLM returns junk, the service uses a topic-derived
    fallback prompt rather than crashing."""
    session = _RecordingSession()
    piece = _piece()
    storage = _FakeStorage()

    bad_llm = AsyncMock()
    bad_llm.generate = AsyncMock(
        return_value=LLMResult(
            raw_text="not json at all",
            model="fake-llm",
            input_tokens=1,
            output_tokens=2,
            cost_usd=0.0,
            latency_ms=1,
            finish_reason="stop",
        )
    )

    image_provider = _image_provider()
    service = ImageService(
        session,  # type: ignore[arg-type]
        llm_provider=bad_llm,
        image_provider=image_provider,
        storage=storage,
    )

    async def _piece_lookup(*_a, **_k):  # type: ignore[no-untyped-def]
        return piece

    async def _mark_others(_pid):  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr(service._content_repo, "get_for_user", _piece_lookup)
    monkeypatch.setattr(service._image_repo, "mark_others_not_current", _mark_others)

    image = await service.generate_for_content(
        user=_user(),
        content_id=piece.id,
        style="illustration",
    )
    # The fallback prompt mentions the topic and uses the chosen style.
    assert "Test topic" in image.image_prompt
    assert "illustration" in image.image_prompt
