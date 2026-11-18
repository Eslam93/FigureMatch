# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

"""Per-content-type renderers.

Each module exports a pure `render(result) -> str`. Renderers run once
at write time so dashboard preview, full-text search, copy-to-clipboard,
and export all consume the same canonical text. `word_count` is a shared
helper that lives with the blog-post renderer for historical reasons
but applies to any content type.
"""

from app.services.renderers.ad_copy import render_ad_copy
from app.services.renderers.blog_post import render_blog_post, word_count
from app.services.renderers.email import render_email
from app.services.renderers.linkedin_post import render_linkedin_post

__all__ = [
    "render_ad_copy",
    "render_blog_post",
    "render_email",
    "render_linkedin_post",
    "word_count",
]
