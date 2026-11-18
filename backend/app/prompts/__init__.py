# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Prompt modules.

Each content type lives in its own module exposing two things:

  - `PROMPT_VERSION` — opaque string persisted with every generation so we
    can map an old `content_pieces` row back to the exact template that
    produced it. Bump when the strings change in a way that would alter
    output meaningfully.
  - `build_prompt(...) -> tuple[str, str]` — pure function that returns
    `(system_prompt, user_prompt)`. No I/O, no provider knowledge.

`json_schema` dicts (for OpenAI's `response_format: json_schema, strict: true`)
also live in the per-type module. The service layer hands them to the provider
verbatim.
"""
