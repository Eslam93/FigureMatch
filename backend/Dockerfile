# SPDX-FileCopyrightText: 2026 Eslam Hamed
#
# SPDX-License-Identifier: MIT

# syntax=docker/dockerfile:1.7
ARG PYTHON_VERSION=3.12

# ──────────────────────────────────────────────────────────────────────
# Stage 1 — install dependencies via uv into a self-contained venv
# ──────────────────────────────────────────────────────────────────────
# App Runner runs amd64; pinning here makes M-series local builds emit
# the same architecture and stops "exec format error" surprises on
# push. BuildKit's `--platform` flag in the deploy workflow reinforces
# this at the CI layer.
FROM --platform=linux/amd64 ghcr.io/astral-sh/uv:python${PYTHON_VERSION}-bookworm-slim AS builder

WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv

# Install deps first so they cache independently of source.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Install the project itself (this layer rebuilds only when app/ or README change).
COPY README.md ./
COPY app ./app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ──────────────────────────────────────────────────────────────────────
# Stage 2 — runtime: minimal Python image + the prebuilt venv
# ──────────────────────────────────────────────────────────────────────
FROM --platform=linux/amd64 python:${PYTHON_VERSION}-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN groupadd --system --gid 1000 app \
 && useradd --system --uid 1000 --gid app --create-home --shell /usr/sbin/nologin app

WORKDIR /app
COPY --from=builder --chown=app:app /opt/venv /opt/venv
COPY --from=builder --chown=app:app /app/app ./app
# Migration tooling needs alembic.ini + scripts at runtime.
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app alembic ./alembic

# LocalImageStorage writes to /app/local_images at runtime. WORKDIR
# /app is owned by root (755), so the non-root `app` user can't
# create the subdir on first use — pre-create it and hand it over.
# When the S3 image-storage adapter lands, this can go.
RUN mkdir -p /app/local_images \
 && chown app:app /app /app/local_images

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request, sys; r=urllib.request.urlopen('http://localhost:8000/api/v1/health', timeout=3); sys.exit(0 if r.status==200 else 1)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
