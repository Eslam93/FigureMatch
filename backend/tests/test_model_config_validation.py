"""Boot-time validation of the configured OpenAI models.

`Settings` refuses a model OpenAI has shut down in every environment, and
an unknown, wrong-kind or unpriced model outside `local`. The catalog clock
is pinned to 2026-11-06 (the verification date) so shutdown dates are fixed.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import TYPE_CHECKING, Any

import pytest

from app.core import model_catalog
from app.core.config import AIProviderMode, Environment, Settings

if TYPE_CHECKING:
    from pytest import MonkeyPatch

# 64 hex chars (valid `openssl rand -hex 32` output); passes the entropy gate.
_STRONG_HEX_SECRET = "3f9a17ce4d2b48a1c0e7f63bda5912f48e6c0a9d7b2e54f1c8a3d6094e7b1c2f"


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: MonkeyPatch) -> None:
    """Pin the catalog clock, and keep a developer's shell out of these
    tests: the builders below pass the mode and environment explicitly and
    skip `.env`, and the shipped-default model ids must not be overridden."""
    monkeypatch.setattr(model_catalog, "today", lambda: date(2026, 11, 6))
    for var in ("OPENAI_TEXT_MODEL", "OPENAI_IMAGE_MODEL"):
        monkeypatch.delenv(var, raising=False)


def _settings(base: dict[str, Any], overrides: dict[str, Any]) -> Settings:
    # `ai_provider_mode` is explicit because the model check only runs in
    # openai mode; an ambient AI_PROVIDER_MODE=mock would skip it silently.
    values = {"ai_provider_mode": AIProviderMode.OPENAI, **base, **overrides}
    return Settings(_env_file=None, **values)


def _local(**overrides: Any) -> Settings:
    return _settings({"environment": Environment.LOCAL}, overrides)


def _production(**overrides: Any) -> Settings:
    """Production settings that pass every other validator, so a failure
    can only come from the model check."""
    base: dict[str, Any] = {
        "environment": Environment.PROD,
        "jwt_secret": _STRONG_HEX_SECRET,
        "openai_api_key": "sk-proj-fake-but-not-placeholder-value-for-test",
        "cors_origins": ["https://test-frontend.example.com"],
    }
    return _settings(base, overrides)


_ENVIRONMENTS = pytest.mark.parametrize("build", [_local, _production], ids=["local", "production"])


def _error(build: Callable[..., Settings], **overrides: Any) -> str:
    with pytest.raises(ValueError) as excinfo:
        build(**overrides)
    return str(excinfo.value)


# ── shipped defaults ───────────────────────────────────────────────────


@_ENVIRONMENTS
def test_shipped_defaults_pass(build: Callable[..., Settings]) -> None:
    settings = build()
    assert settings.openai_text_model == "gpt-5.4-mini-2026-03-17"
    assert settings.openai_image_model == "gpt-image-2.5-flare"


# ── shut-down models: rejected everywhere ──────────────────────────────


@_ENVIRONMENTS
def test_shut_down_image_model_fails_naming_env_var_date_and_replacement(
    build: Callable[..., Settings],
) -> None:
    message = _error(build, openai_image_model="gpt-image-1")
    assert "OPENAI_IMAGE_MODEL='gpt-image-1' was shut down by OpenAI on 2026-10-23" in message
    assert "(see https://developers.openai.com/api/docs/deprecations)" in message
    assert "Set OPENAI_IMAGE_MODEL=gpt-image-2.5-flare, the catalog's suggested" in message


def test_dall_e_replacement_is_not_attributed_to_openai() -> None:
    """OpenAI names gpt-image-2, gpt-image-1 or gpt-image-1-mini for DALL·E;
    gpt-image-2.5-flare is the catalog's own pick, and must read as such."""
    message = _error(_local, openai_image_model="dall-e-3")
    assert "Set OPENAI_IMAGE_MODEL=gpt-image-2.5-flare, the catalog's suggested" in message
    assert "OpenAI's replacement" not in message


@_ENVIRONMENTS
def test_shut_down_model_in_the_wrong_slot_points_at_a_model_of_the_slots_kind(
    build: Callable[..., Settings],
) -> None:
    """dall-e-3's replacement is an image model: following it in the text
    slot would just swap one broken text setting for another."""
    message = _error(build, openai_text_model="dall-e-3")
    assert "OPENAI_TEXT_MODEL='dall-e-3' was shut down by OpenAI on 2026-05-12" in message
    assert (
        "It is also catalogued as kind='image', but OPENAI_TEXT_MODEL needs kind='text': "
        "set OPENAI_TEXT_MODEL=gpt-5.4-mini-2026-03-17, the shipped default." in message
    )
    assert "gpt-image-2.5-flare" not in message


def test_retiring_model_becomes_fatal_in_local_on_its_shutdown_day(
    monkeypatch: MonkeyPatch,
) -> None:
    assert _local(openai_image_model="gpt-image-1.5").openai_image_model == "gpt-image-1.5"

    monkeypatch.setattr(model_catalog, "today", lambda: date(2026, 12, 1))

    message = _error(_local, openai_image_model="gpt-image-1.5")
    assert "was shut down by OpenAI on 2026-12-01" in message
    assert "gpt-image-2.6-flare" in message


# ── unknown, wrong-kind, unpriced: rejected outside local ──────────────


def test_unknown_model_fails_outside_local_pointing_at_the_catalog() -> None:
    message = _error(_production, openai_text_model="gpt-9-imaginary")
    assert "OPENAI_TEXT_MODEL='gpt-9-imaginary'" in message
    assert "Add the model to app/core/model_catalog.py with verified prices" in message


def test_unknown_model_is_allowed_in_local() -> None:
    """Local stays open for experiments: the providers log a warning and
    record zero cost for unpriced models there."""
    settings = _local(openai_text_model="gpt-9-imaginary", openai_image_model="gpt-image-9")
    assert settings.openai_text_model == "gpt-9-imaginary"
    assert settings.openai_image_model == "gpt-image-9"


@pytest.mark.parametrize(
    ("field", "model_id", "env_var", "actual_kind"),
    [
        ("openai_text_model", "gpt-image-2.5-flare", "OPENAI_TEXT_MODEL", "image"),
        ("openai_image_model", "gpt-5.4-mini", "OPENAI_IMAGE_MODEL", "text"),
    ],
)
def test_wrong_kind_fails_outside_local(
    field: str, model_id: str, env_var: str, actual_kind: str
) -> None:
    message = _error(_production, **{field: model_id})
    assert f"{env_var}={model_id!r} is catalogued as kind={actual_kind!r}" in message


def test_wrong_kind_is_tolerated_in_local() -> None:
    settings = _local(openai_text_model="gpt-image-2.5-flare")
    assert settings.openai_text_model == "gpt-image-2.5-flare"


def test_retiring_model_fails_outside_local_naming_shutdown_and_replacement() -> None:
    message = _error(_production, openai_image_model="gpt-image-1.5")
    assert "OPENAI_IMAGE_MODEL='gpt-image-1.5' has no verified price" in message
    assert "OpenAI shuts it down on 2026-12-01" in message
    assert "Set OPENAI_IMAGE_MODEL=gpt-image-2.6-flare instead" in message


def test_retiring_model_is_allowed_in_local_before_its_shutdown() -> None:
    settings = _local(openai_image_model="chatgpt-image-latest")
    assert settings.openai_image_model == "chatgpt-image-latest"


def test_unpriced_model_without_a_shutdown_date_fails_outside_local(
    monkeypatch: MonkeyPatch,
) -> None:
    entry = model_catalog.ModelEntry(
        model_id="gpt-image-unpriced",
        kind="image",
        pricing=None,
        verified_on=date(2026, 11, 6),
        source_url="https://developers.openai.com/api/docs/pricing",
    )
    patched = {**model_catalog.MODEL_CATALOG, entry.model_id: entry}
    monkeypatch.setattr(model_catalog, "MODEL_CATALOG", patched)

    message = _error(_production, openai_image_model="gpt-image-unpriced")

    assert "OPENAI_IMAGE_MODEL='gpt-image-unpriced' has no verified price" in message
    assert "shuts it down" not in message


# ── modes that never call OpenAI skip the check ────────────────────────


@pytest.mark.parametrize("mode", [AIProviderMode.MOCK, AIProviderMode.BEDROCK])
def test_non_openai_modes_skip_the_model_check_in_local(mode: AIProviderMode) -> None:
    settings = _local(
        ai_provider_mode=mode,
        openai_text_model="gpt-9-imaginary",
        openai_image_model="gpt-image-1",
    )
    assert settings.openai_image_model == "gpt-image-1"


def test_mock_mode_skips_the_model_check_in_production() -> None:
    settings = _production(
        ai_provider_mode=AIProviderMode.MOCK,
        allow_mock_provider=True,
        openai_image_model="gpt-image-1",
    )
    assert settings.ai_provider_mode is AIProviderMode.MOCK


# ── precedence with the existing validators ────────────────────────────


def test_secret_errors_still_fire_before_the_model_check() -> None:
    message = _error(_production, jwt_secret="secret", openai_image_model="gpt-image-1")
    assert "JWT_SECRET is unacceptable" in message
    assert "OPENAI_IMAGE_MODEL" not in message


def test_text_slot_is_checked_before_the_image_slot() -> None:
    message = _error(_local, openai_text_model="dall-e-2", openai_image_model="gpt-image-1")
    assert "OPENAI_TEXT_MODEL='dall-e-2'" in message
