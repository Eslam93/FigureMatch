"""Stage 2 of the parse fallback: the corrective retry.

When a model reply fails to parse, the content and improver services call
the model once more with the same strict json_schema. The retry shows the
model its rejected reply and says exactly what was wrong with it: either it
was not valid JSON, or which fields failed validation, each with Pydantic's
message. The note never repeats a rejected value; the model already sees
its whole reply.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from pydantic import BaseModel, ValidationError

_NOT_VALID_JSON: Final[str] = "The previous reply was not valid JSON."


@dataclass(frozen=True)
class ParseFailure:
    """Why a model reply was rejected, worded for the corrective retry."""

    note: str


def parse_reply[ModelT: BaseModel](raw: str, model: type[ModelT]) -> ModelT | ParseFailure:
    """Parse `raw` as JSON and validate it against `model`."""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return ParseFailure(_NOT_VALID_JSON)
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        return ParseFailure(_validation_note(exc))


def _validation_note(exc: ValidationError) -> str:
    # `include_input=False` keeps the rejected values out of the note.
    errors = exc.errors(include_url=False, include_context=False, include_input=False)
    lines = [f"- {_field_path(error['loc'])}: {error['msg']}" for error in errors]
    return "The previous reply failed validation. Fix these fields:\n" + "\n".join(lines)


def _field_path(loc: Sequence[int | str]) -> str:
    """`("sections", 0, "heading")` becomes `sections[0].heading`. Errors
    about the reply as a whole (wrong type, a model validator) have an
    empty location and become `(root)`."""
    path = ""
    for part in loc:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}" if path else part
    return path or "(root)"


def corrective_user_prompt(
    *,
    user_prompt: str,
    previous_reply: str,
    failure: ParseFailure,
    instruction: str,
) -> str:
    """The retry's user prompt: the original prompt, the rejected reply,
    what was wrong with it, and the prompt module's corrective instruction."""
    return (
        f"{user_prompt}\n\n"
        f"Previous response (invalid):\n{previous_reply}\n\n"
        f"{failure.note}\n\n"
        f"{instruction}"
    )
