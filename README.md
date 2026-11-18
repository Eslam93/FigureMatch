# FigureMatch

An AI content studio: a Next.js and FastAPI app that drafts marketing copy with OpenAI, pairs each piece with a generated image, and keeps each user's work in Postgres.

Built by **Eslam Hamed**, Technical Lead & AI Solutions Architect. More work: [eslamhamed.com](https://eslamhamed.com).

[![Backend CI](https://github.com/Eslam93/FigureMatch/actions/workflows/backend-ci.yml/badge.svg)](https://github.com/Eslam93/FigureMatch/actions/workflows/backend-ci.yml) [![Frontend CI](https://github.com/Eslam93/FigureMatch/actions/workflows/frontend-ci.yml/badge.svg)](https://github.com/Eslam93/FigureMatch/actions/workflows/frontend-ci.yml) [![Infra CI](https://github.com/Eslam93/FigureMatch/actions/workflows/infra-ci.yml/badge.svg)](https://github.com/Eslam93/FigureMatch/actions/workflows/infra-ci.yml) [![REUSE](https://github.com/Eslam93/FigureMatch/actions/workflows/reuse.yml/badge.svg)](https://github.com/Eslam93/FigureMatch/actions/workflows/reuse.yml) ![License](https://img.shields.io/badge/license-MIT-blue)

It started as a two-day hiring take-home in May 2026: an AI content-marketing studio.

## What is here, and what is not

- **The studio as built in May 2026.** Commit `52dc30b` (tag `take-home-2026-05-16`) is where that work ended. It ran on AWS for a demo that month. The stack was torn down in June 2026 and nothing is deployed today. It runs on your machine, against OpenAI or in mock mode with no key.
- **A November 2026 audit.** Read again six months later, the code had defects that its passing test suite did not catch. A stolen refresh token stayed valid because its revocation was rolled back. Text costs were recorded 5 to 7.5 times too low. OpenAI had shut down the default image model. And 422 responses echoed back a rejected password. These were fixed in [#154](https://github.com/Eslam93/FigureMatch/pull/154) and [#155](https://github.com/Eslam93/FigureMatch/pull/155). [`audit/`](./audit/) replays them: four probes that fail on the May code and pass on today's, and a rerun of the May suite showing that it executed every faulty line.
- **The figure checker is not built.** The name is for what may come next: a checker that confirms every figure in an Arabic version matches its English original. Whether it gets built depends on a cheap measurement, set up in [`gate/`](./gate/) before any checker code exists.

## What the studio does

1. **Generate**: pick a content type (blog post, LinkedIn post, email or ad copy), describe the topic, tone and audience, and get a draft.
2. **Pair with an image**: one click builds an image prompt from the draft and generates the image.
3. **Improve**: paste existing text, pick a goal, and get a rewrite with an explanation of what changed, shown beside the original.
4. **Manage**: a dashboard of past drafts with search, filters, Markdown download, and soft delete with undo.
5. **Brand voice**: saved profiles that prefill the style of new drafts.

## Run it locally

You need Docker, Node 22 and pnpm 10. Mock mode needs no OpenAI key and spends nothing.

```bash
git clone https://github.com/Eslam93/FigureMatch.git
cd FigureMatch
cp .env.example .env
# Mock mode: set AI_PROVIDER_MODE=mock in .env.
# Real models: set OPENAI_API_KEY, and put a spend cap on the OpenAI account first.
docker compose up --build        # Postgres and the backend, reachable from this machine only
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.scripts.seed   # demo user: demo@figurematch.dev / DemoPass123

cd frontend
pnpm install
pnpm dev                          # http://localhost:3000, calls the backend at http://localhost:8000/api/v1
```

In mock mode the app shows a banner saying so, and every draft and image is canned.

## Stack

| Layer | Choice |
|---|---|
| Frontend | Next.js 15 (App Router, built as a static export), TypeScript, Tailwind, shadcn/ui, TanStack Query, Zod, React Hook Form |
| Backend | FastAPI, Python 3.12, Pydantic v2, async SQLAlchemy 2.0, Alembic |
| Database | PostgreSQL 16 |
| AI, text | OpenAI `gpt-5.4-mini-2026-03-17` |
| AI, image | OpenAI `gpt-image-2.5-flare` |
| Auth | Custom JWT: short-lived access token in memory, refresh token in an httpOnly cookie, single-use rotation with reuse detection, Origin check against CSRF |
| Rate limits | Per-minute buckets held in each backend process's memory |
| Image storage | The backend's local disk, behind an `IImageStorage` interface |
| Infrastructure as code | AWS CDK in TypeScript, five stacks (see [Deployment](#deployment)) |
| Logs and errors | structlog JSON logs; Sentry on the backend when `SENTRY_DSN` is set |
| CI | GitHub Actions |

Rationale for each choice is in [`ARCHITECTURE.md`](./ARCHITECTURE.md).

## How it fits together

```
Browser ── Next.js static pages ──→ FastAPI backend (/api/v1)
                                      ├──→ PostgreSQL (users, refresh tokens, drafts, images, improvements, brand voices)
                                      ├──→ local disk (generated images, served at /local-images)
                                      └──→ OpenAI (text and images), or the mock provider
```

The backend calls OpenAI through two interfaces, `ILLMProvider` and `IImageProvider`, with OpenAI and mock implementations behind a factory. Model output is parsed in three stages: a strict JSON schema, then one corrective retry with the same schema, then the raw text with a banner saying it could not be structured. A reply that comes back cut off or refused returns a typed error (`AI_OUTPUT_TRUNCATED`, `AI_CONTENT_REJECTED`) instead.

Every model id, price and shutdown date lives in one dated catalog, [`backend/app/core/model_catalog.py`](./backend/app/core/model_catalog.py), with the OpenAI page each came from. The backend refuses to boot on a model that OpenAI has shut down, and a weekly CI job checks the configured models against OpenAI's deprecations page.

## API

FastAPI generates an OpenAPI 3.1 spec from the routes. `/docs`, `/redoc` and `/openapi.json` are served only when `ENVIRONMENT` is `local` or `dev`. To get the spec from the source tree:

```bash
cd backend
uv run python -c "import json; from app.main import app; print(json.dumps(app.openapi(), indent=2))" > openapi.json
```

| Group | Endpoints |
|---|---|
| Auth | `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me` |
| Content | `POST /content/generate`, `GET /content`, `GET /content/:id`, `DELETE /content/:id` (soft delete), `POST /content/:id/restore` (within 24 hours), `GET /content/:id/export?format=md` |
| Images | `POST /content/:id/image` (generate or regenerate), `GET /content/:id/images` (every version, newest first) |
| Improver | `POST /improve`, `GET /improvements`, `GET /improvements/:id`, `DELETE /improvements/:id` |
| Brand voices | `GET /brand-voices`, `POST /brand-voices`, `GET /brand-voices/:id`, `PATCH /brand-voices/:id`, `DELETE /brand-voices/:id` |
| System | `GET /health`, `GET /meta` (provider mode and app version) |

All paths are under `/api/v1`.

## Repository layout

```
FigureMatch/
├── README.md           # this file
├── ARCHITECTURE.md     # decisions and trade-offs
├── DEVLOG.md           # build journal, May 2026
├── docker-compose.yml  # Postgres and the backend for local work
├── .env.example        # environment template
├── .github/workflows/  # CI
├── backend/            # FastAPI service
├── frontend/           # Next.js app
├── infra/              # AWS CDK app
├── audit/              # the November 2026 audit, replayable
└── gate/               # the measurement that decides whether the figure checker gets built
```

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `ENVIRONMENT` | `local` | `local`, `dev`, `staging` or `production`. Outside `local`, weak secrets and missing keys stop the backend from booting. |
| `AI_PROVIDER_MODE` | `openai` | `openai` or `mock`. `bedrock` is refused at boot: its providers are stubs. |
| `ALLOW_MOCK_PROVIDER` | `false` | Allows `mock` outside `local`. |
| `OPENAI_API_KEY` | none | Required in `openai` mode outside `local`. |
| `OPENAI_TEXT_MODEL` | `gpt-5.4-mini-2026-03-17` | Text model; must be in the catalog outside `local`. |
| `OPENAI_IMAGE_MODEL` | `gpt-image-2.5-flare` | Image model; a shut-down model fails at boot everywhere. |
| `OPENAI_IMAGE_QUALITY` | `medium` | `low`, `medium` or `high`. |
| `OPENAI_TIMEOUT_SECONDS` | `60` | Per-call timeout. |
| `OPENAI_MAX_RETRIES` | `3` | Attempts per OpenAI call; rate limits, timeouts and 5xx are retried with backoff. |
| `DATABASE_URL` | the compose database | asyncpg connection string. |
| `RDS_SECRET_ARN` | empty | When set, the database URL is built from this AWS Secrets Manager secret. |
| `JWT_SECRET` | a placeholder | Required outside `local`: `openssl rand -hex 32`. |
| `JWT_ACCESS_TOKEN_TTL_SECONDS` | `900` | 15 minutes. |
| `JWT_REFRESH_TOKEN_TTL_SECONDS` | `2592000` | 30 days. |
| `COOKIE_SAMESITE` | `lax` | `none` when the frontend and the API are on different sites. |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed origins. |
| `IMAGES_CDN_BASE_URL` | `http://localhost:8000/local-images` | URL prefix for stored images. |
| `S3_BUCKET_IMAGES` | `ai-content-images-dev` | Read by nothing yet: images are stored on local disk. |
| `SENTRY_DSN` | empty | Backend error reporting; off when empty. |
| `LOG_LEVEL` | `INFO` | structlog level. |
| `AWS_REGION` | `us-east-1` | AWS region, for a deployed stack only. |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000/api/v1` | Frontend only, read at build time from `frontend/.env.local` or the shell. |

[`.env.example`](./.env.example) has the commonly set ones with comments.

## Tests and CI

Each workflow runs more than tests. Run the same steps locally before pushing:

```bash
# Backend, as backend-ci.yml runs it (needs Postgres at DATABASE_URL)
cd backend
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run mypy app
uv run alembic upgrade head
REQUIRE_DB=1 uv run pytest --cov=app --cov-fail-under=80   # REQUIRE_DB=1 fails, not skips, without Postgres
uv run python -c "import json; from app.main import app; json.dump(app.openapi(), open('openapi-tmp.json', 'w'))"
npx openapi-typescript@7.4 openapi-tmp.json -o /dev/null && rm openapi-tmp.json

# Frontend, as frontend-ci.yml runs it
cd frontend
pnpm install --frozen-lockfile
pnpm lint
pnpm format:check
pnpm typecheck
pnpm test
NEXT_OUTPUT=export pnpm build

# Infra, as infra-ci.yml runs it
cd infra
npm ci
npm run build
npm test

# Licence headers, as reuse.yml runs it
uvx --from "reuse[charset-normalizer]==6.3.0" reuse lint
```

| Workflow | Runs on | Checks |
|---|---|---|
| [`backend-ci`](./.github/workflows/backend-ci.yml) | `backend/**` changes | ruff lint and format, mypy strict, migrations, pytest against Postgres with an 80% coverage gate, OpenAPI spec through openapi-typescript |
| [`frontend-ci`](./.github/workflows/frontend-ci.yml) | `frontend/**` changes | ESLint, Prettier, tsc, Vitest, the static export build and its 404 page |
| [`infra-ci`](./.github/workflows/infra-ci.yml) | `infra/**` changes | tsc, Jest with a snapshot per stack, `cdk synth` with placeholder context |
| [`model-lifecycle`](./.github/workflows/model-lifecycle.yml) | Mondays 06:17 UTC, manual, and PRs touching the catalog | Fails if a configured model is unknown, unpriced, shut down, shutting down within 30 days, or listed on OpenAI's deprecations page |
| [`audit-replay`](./.github/workflows/audit-replay.yml) | `audit/**` and `backend/**` changes, and manual | The four audit probes fail on the May tag and pass on the commit being built; the May suite still executes every faulty line |
| [`reuse`](./.github/workflows/reuse.yml) | pushes to `main` and working branches, and every PR | Every file states its copyright and licence |

## Deployment

The CDK app in [`infra/`](./infra/) describes the May 2026 deployment in five stacks: Network, Data (RDS Postgres, an S3 bucket, Secrets Manager), Compute (ECR, App Runner, a Fargate task for migrations), Edge (Amplify hosting) and Observability, which is an empty placeholder. Synth needs `cors_origins` and `images_cdn_base_url` context; infra-ci passes placeholders.

The stack was deployed by hand from [`infra/DEPLOY.md`](./infra/DEPLOY.md) in May 2026 and destroyed in June 2026. The runbook needs work before anyone reuses it. It relies on an egress security group that was created by hand and that no stack defines. Several of its commands also leave out the context synth now requires.

[`deploy.yml`](./.github/workflows/deploy.yml) has never completed a run. Its OIDC role was never configured. It deploys only the backend, and its migration task passes no security group.

## Known limits

- Rate limits are per process and per minute, so a fleet of instances multiplies them, and a restart resets them.
- Generated images live on the backend's local disk. They are lost on redeploy and not shared between instances.
- There is no password reset and no email verification.
- The Bedrock providers are stubs that raise on construction.
- One image generation holds a database row lock for the whole prompt, image and upload sequence. A second request for the same piece fails fast with `409 IMAGE_GENERATION_IN_PROGRESS`.
- Two browser tabs refreshing at the same moment look like token reuse, which signs the user out everywhere.

## Development log

[`DEVLOG.md`](./DEVLOG.md) is the build journal from 14 to 16 May 2026, up to [#147](https://github.com/Eslam93/FigureMatch/pull/147). Later changes are described in their pull requests.

## Licence

[MIT](./LICENSE). Every file states its copyright and licence by the [REUSE](https://reuse.software) convention. Files with no room for a header are covered by [`REUSE.toml`](./REUSE.toml).
