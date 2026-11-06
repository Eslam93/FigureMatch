"""Content generation orchestration.

Slice 2 widens this from "blog only" to all four content types: blog
post, LinkedIn post, email, ad copy. The public `generate(user,
request)` dispatches through a per-type registry that pairs a prompt
module with its Pydantic result model and renderer. The three-stage
parse fallback (parse → corrective retry → graceful degrade) is shared
across every content type.

The fallback is non-negotiable (PROJECT_BRIEF §7.0):

  1. Attempt 1 — call provider with strict json_schema. Pydantic-validate.
                 Status = OK on success.
  2. Attempt 2 — on parse/validation failure, re-call with the same strict
                 json_schema, showing the model its reply and naming what
                 failed (invalid JSON, or each failing field with
                 Pydantic's message). Status = RETRIED on success.
  3. Attempt 3 — on second failure, persist the raw model output as
                 `rendered_text` with `result = None`,
                 `result_parse_status = FAILED`. Sentry-warn so we notice
                 drift without crashing the user.

Aggregate token usage from both calls; cost is the sum of both
`LLMResult.cost_usd` values (zero for mock).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.db.enums import ContentType, ResultParseStatus
from app.db.models import ContentPiece, User
from app.db.session import end_read_transaction
from app.prompts import ad_copy as ad_copy_prompt
from app.prompts import blog_post as blog_post_prompt
from app.prompts import email as email_prompt
from app.prompts import linkedin_post as linkedin_post_prompt
from app.providers.llm.base import ILLMProvider, LLMResult
from app.repositories.brand_voice_repository import BrandVoiceRepository
from app.repositories.content_repository import ContentRepository
from app.schemas.content import (
    AdCopyResult,
    BlogPostResult,
    ContentResult,
    EmailResult,
    GenerateRequest,
    LinkedInPostResult,
)
from app.services.brand_voice_service import render_brand_voice_block
from app.services.corrective_retry import ParseFailure, corrective_user_prompt, parse_reply
from app.services.renderers import (
    render_ad_copy,
    render_blog_post,
    render_email,
    render_linkedin_post,
    word_count,
)

log = get_logger(__name__)


# ── per-type bundles ───────────────────────────────────────────────────


@dataclass(frozen=True)
class _ContentTypeBundle:
    """Everything the service needs to drive one content type end to end.

    The fallback semantics in `_run_pipeline` are content-type agnostic;
    each bundle provides only the per-type strings, the validator, and
    the renderer. Adding a fifth content type is appending one entry to
    `_REGISTRY`.
    """

    prompt_version: str
    build_prompt: Callable[..., tuple[str, str]]
    json_schema: dict[str, Any]
    corrective_retry_instruction: str
    result_model: type[BaseModel]
    render: Callable[[Any], str]


_REGISTRY: dict[ContentType, _ContentTypeBundle] = {
    ContentType.BLOG_POST: _ContentTypeBundle(
        prompt_version=blog_post_prompt.PROMPT_VERSION,
        build_prompt=blog_post_prompt.build_prompt,
        json_schema=blog_post_prompt.JSON_SCHEMA,
        corrective_retry_instruction=blog_post_prompt.CORRECTIVE_RETRY_INSTRUCTION,
        result_model=BlogPostResult,
        render=render_blog_post,
    ),
    ContentType.LINKEDIN_POST: _ContentTypeBundle(
        prompt_version=linkedin_post_prompt.PROMPT_VERSION,
        build_prompt=linkedin_post_prompt.build_prompt,
        json_schema=linkedin_post_prompt.JSON_SCHEMA,
        corrective_retry_instruction=linkedin_post_prompt.CORRECTIVE_RETRY_INSTRUCTION,
        result_model=LinkedInPostResult,
        render=render_linkedin_post,
    ),
    ContentType.EMAIL: _ContentTypeBundle(
        prompt_version=email_prompt.PROMPT_VERSION,
        build_prompt=email_prompt.build_prompt,
        json_schema=email_prompt.JSON_SCHEMA,
        corrective_retry_instruction=email_prompt.CORRECTIVE_RETRY_INSTRUCTION,
        result_model=EmailResult,
        render=render_email,
    ),
    ContentType.AD_COPY: _ContentTypeBundle(
        prompt_version=ad_copy_prompt.PROMPT_VERSION,
        build_prompt=ad_copy_prompt.build_prompt,
        json_schema=ad_copy_prompt.JSON_SCHEMA,
        corrective_retry_instruction=ad_copy_prompt.CORRECTIVE_RETRY_INSTRUCTION,
        result_model=AdCopyResult,
        render=render_ad_copy,
    ),
}


def supported_content_types() -> frozenset[ContentType]:
    """Content types the service knows how to generate.

    The router uses this to translate an unknown content type into a
    422 with a structured error code instead of crashing here.
    """
    return frozenset(_REGISTRY.keys())


def project_result(
    content_type: ContentType | str,
    raw: dict[str, Any] | None,
) -> ContentResult | None:
    """Re-validate a stored JSONB row through the per-type Pydantic model.

    Single source of truth for "given a row's content_type, which
    Pydantic class projects its `result` JSONB for the wire?". Lives
    in the service so adding a fifth content type only requires
    appending to `_REGISTRY` — the router projector that used to
    duplicate this knowledge has been dropped.

    None passes through — that's the FAILED parse-status path where
    `rendered_text` carries the raw model output and `result` is null
    on the row.
    """
    if raw is None:
        return None
    ct = ContentType(content_type) if not isinstance(content_type, ContentType) else content_type
    bundle = _REGISTRY[ct]
    return bundle.result_model.model_validate(raw)  # type: ignore[return-value]


# ── parse outcome ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class _ParseOutcome:
    """Internal result of the three-stage parse pass.

    Either `result` is populated (OK or RETRIED — `rendered_text` is the
    canonical render of `result`), or it's None (FAILED — `rendered_text`
    is the raw model output verbatim and `failure` says what was wrong).
    """

    result: ContentResult | None
    rendered_text: str
    status: ResultParseStatus
    failure: ParseFailure | None = None


# ── service ────────────────────────────────────────────────────────────


class ContentService:
    """Generate content. One public method; everything else is helper."""

    def __init__(self, session: AsyncSession, provider: ILLMProvider) -> None:
        self._session = session
        self._provider = provider
        self._repo = ContentRepository(session)

    async def generate(
        self,
        *,
        user: User,
        request: GenerateRequest,
    ) -> ContentPiece:
        """Run the prompt → parse → persist pipeline for any content type.

        Raises `KeyError` if the registry is missing the content type;
        the router validates the input against `supported_content_types()`
        before getting here.
        """
        bundle = _REGISTRY[request.content_type]

        brand_voice_block = await self._maybe_brand_voice_block(user, request.brand_voice_id)
        system_prompt, user_prompt = bundle.build_prompt(
            topic=request.topic,
            tone=request.tone,
            target_audience=request.target_audience,
            brand_voice_block=brand_voice_block,
        )

        # --- Attempt 1: strict json_schema ---
        # Don't hold the user and brand-voice reads' transaction through the call.
        await end_read_transaction(self._session)
        attempt1 = await self._provider.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_schema=bundle.json_schema["schema"],
            content_type=request.content_type.value,
        )
        outcome = self._try_parse(
            attempt1.raw_text,
            ResultParseStatus.OK,
            result_model=bundle.result_model,
        )

        total_input = attempt1.input_tokens
        total_output = attempt1.output_tokens
        total_cost = Decimal(str(attempt1.cost_usd))
        model_id = attempt1.model

        # --- Attempt 2: corrective retry ---
        if outcome.failure is not None:
            log.warning(
                "content_parse_failed_attempt_1",
                content_type=request.content_type.value,
                user_id=str(user.id),
                model=model_id,
            )
            attempt2 = await self._call_corrective_retry(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                previous_raw=attempt1.raw_text,
                failure=outcome.failure,
                json_schema=bundle.json_schema["schema"],
                content_type=request.content_type,
                corrective_instruction=bundle.corrective_retry_instruction,
            )
            outcome = self._try_parse(
                attempt2.raw_text,
                ResultParseStatus.RETRIED,
                result_model=bundle.result_model,
            )
            total_input += attempt2.input_tokens
            total_output += attempt2.output_tokens
            total_cost += Decimal(str(attempt2.cost_usd))

            if outcome.result is None:
                # Stage 3 — graceful degrade. Surface but don't raise.
                log.warning(
                    "content_parse_failed_attempt_2",
                    content_type=request.content_type.value,
                    user_id=str(user.id),
                    model=model_id,
                )

        # Render canonical text when we have structured output; otherwise
        # the raw model text is already in `outcome.rendered_text`.
        if outcome.result is not None:
            rendered_text = bundle.render(outcome.result)
            result_jsonb = outcome.result.model_dump()
            wc = word_count(rendered_text)
        else:
            rendered_text = outcome.rendered_text
            result_jsonb = None
            wc = word_count(rendered_text)

        piece = ContentPiece(
            user_id=user.id,
            content_type=request.content_type,
            topic=request.topic,
            tone=request.tone,
            target_audience=request.target_audience,
            brand_voice_id=request.brand_voice_id,
            prompt_version=bundle.prompt_version,
            system_prompt_snapshot=system_prompt,
            user_prompt_snapshot=user_prompt,
            result=result_jsonb,
            rendered_text=rendered_text,
            result_parse_status=outcome.status,
            word_count=wc,
            model_id=model_id,
            input_tokens=total_input,
            output_tokens=total_output,
            cost_usd=total_cost,
        )
        return await self._repo.create(piece)

    # ── helpers ────────────────────────────────────────────────────────

    async def _maybe_brand_voice_block(
        self,
        user: User,
        brand_voice_id: Any,
    ) -> str | None:
        """Fetch the voice row and render it into a prompt block.

        Returns None when the caller didn't supply a `brand_voice_id`.
        Raises `NotFoundError` if they did but the row doesn't exist
        or isn't owned — `BRAND_VOICE_NOT_FOUND` reads cleanly in the
        toast.
        """
        if brand_voice_id is None:
            return None
        repo = BrandVoiceRepository(self._session)
        voice = await repo.get_for_user(brand_voice_id, user.id)
        if voice is None:
            raise NotFoundError(
                "Brand voice not found.",
                code="BRAND_VOICE_NOT_FOUND",
            )
        return render_brand_voice_block(voice)

    @staticmethod
    def _try_parse(
        raw: str,
        success_status: ResultParseStatus,
        *,
        result_model: type[BaseModel],
    ) -> _ParseOutcome:
        """Parse raw text as JSON and validate against `result_model`.

        On any failure return an outcome with `result=None`, the raw text
        preserved and the failure described — the caller decides whether
        to retry or degrade.
        """
        parsed = parse_reply(raw, result_model)
        if isinstance(parsed, ParseFailure):
            return _ParseOutcome(
                result=None,
                rendered_text=raw,
                status=ResultParseStatus.FAILED,
                failure=parsed,
            )
        # The narrow union return type is enforced by the registry: the
        # only models in `_REGISTRY` are members of `ContentResult`.
        return _ParseOutcome(
            result=parsed,  # type: ignore[arg-type]
            rendered_text="",  # caller renders from `result`
            status=success_status,
        )

    async def _call_corrective_retry(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        previous_raw: str,
        failure: ParseFailure,
        json_schema: dict[str, Any],
        content_type: ContentType,
        corrective_instruction: str,
    ) -> LLMResult:
        """Second-pass call that says what was wrong with the first reply.

        We feed the prior raw response back into the user prompt, with a
        note naming what failed, so the model can see what it sent and
        correct course. Strict `json_schema` stays on: the usual first-pass
        failure is a limit the schema can't express (a field's length),
        and dropping strict mode only let the retry return any shape.
        """
        await end_read_transaction(self._session)
        return await self._provider.generate(
            system_prompt=system_prompt,
            user_prompt=corrective_user_prompt(
                user_prompt=user_prompt,
                previous_reply=previous_raw,
                failure=failure,
                instruction=corrective_instruction,
            ),
            json_schema=json_schema,
            content_type=content_type.value,
        )
