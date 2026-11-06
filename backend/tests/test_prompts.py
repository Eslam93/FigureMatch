"""Smoke tests for the four prompt modules.

These prove the contract, not the wording, which
`tests/test_prompt_goldens.py` pins against golden files: every module
exports the required surface, the user prompt threads the provided
fields into the body, and `brand_voice_block` widens the prompt when
supplied.
"""

from __future__ import annotations

import pytest

from app.prompts import ad_copy, blog_post, email, linkedin_post

_PROMPT_MODULES = [blog_post, linkedin_post, email, ad_copy]


@pytest.mark.parametrize("module", _PROMPT_MODULES, ids=lambda m: m.__name__.rsplit(".", 1)[-1])
def test_module_exports_required_surface(module: object) -> None:
    """Every prompt module must export the same five symbols. The
    content service registry indexes these by name, so a missing one
    fails import, not runtime — but a wrong type is silent until a
    generate call, which this test catches earlier."""
    assert isinstance(module.PROMPT_VERSION, str)  # type: ignore[attr-defined]
    assert module.PROMPT_VERSION  # type: ignore[attr-defined]
    assert isinstance(module.SYSTEM_PROMPT, str) and module.SYSTEM_PROMPT  # type: ignore[attr-defined]
    assert isinstance(module.CORRECTIVE_RETRY_INSTRUCTION, str)  # type: ignore[attr-defined]
    schema = module.JSON_SCHEMA  # type: ignore[attr-defined]
    assert isinstance(schema, dict)
    assert schema.get("strict") is True
    assert isinstance(schema.get("schema"), dict)
    assert callable(module.build_prompt)  # type: ignore[attr-defined]


@pytest.mark.parametrize("module", _PROMPT_MODULES, ids=lambda m: m.__name__.rsplit(".", 1)[-1])
def test_build_prompt_threads_topic_tone_and_audience(module: object) -> None:
    system, user = module.build_prompt(  # type: ignore[attr-defined]
        topic="A unique-topic-marker-xyz",
        tone="punchy-tone-marker",
        target_audience="audience-marker-789",
    )
    assert isinstance(system, str) and system
    assert "A unique-topic-marker-xyz" in user
    assert "punchy-tone-marker" in user
    assert "audience-marker-789" in user


@pytest.mark.parametrize("module", _PROMPT_MODULES, ids=lambda m: m.__name__.rsplit(".", 1)[-1])
def test_build_prompt_brand_voice_block_appears_when_supplied(module: object) -> None:
    _, with_voice = module.build_prompt(  # type: ignore[attr-defined]
        topic="topic",
        tone=None,
        target_audience=None,
        brand_voice_block="VOICE_BLOCK_SENTINEL",
    )
    _, without_voice = module.build_prompt(  # type: ignore[attr-defined]
        topic="topic",
        tone=None,
        target_audience=None,
    )
    assert "VOICE_BLOCK_SENTINEL" in with_voice
    assert "VOICE_BLOCK_SENTINEL" not in without_voice


@pytest.mark.parametrize(
    "module,expected_version",
    [
        (blog_post, "blog_post.v1"),
        (linkedin_post, "linkedin_post.v1"),
        (email, "email.v1"),
        (ad_copy, "ad_copy.v1"),
    ],
    ids=lambda x: getattr(x, "__name__", str(x)),
)
def test_prompt_versions_are_pinned(module: object, expected_version: str) -> None:
    """`prompt_version` is persisted with every generation; flipping it
    must be a deliberate bump, not an incidental rename."""
    assert expected_version == module.PROMPT_VERSION  # type: ignore[attr-defined]
