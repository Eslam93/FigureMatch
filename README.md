# MagnaCMS — AI Content Marketing Suite

A production-minded SaaS demo that helps marketers generate, manage, and improve marketing content using AI. Every generated piece can be paired with an AI-generated image in one flow.

> **Status:** in active development. The repo is functional from day one — see the dev log for what works today vs. what's next.

[![Backend CI](https://github.com/Eslam93/MagnaCMS/actions/workflows/backend-ci.yml/badge.svg)](https://github.com/Eslam93/MagnaCMS/actions/workflows/backend-ci.yml) [![Frontend CI](https://github.com/Eslam93/MagnaCMS/actions/workflows/frontend-ci.yml/badge.svg)](https://github.com/Eslam93/MagnaCMS/actions/workflows/frontend-ci.yml) [![Infra CI](https://github.com/Eslam93/MagnaCMS/actions/workflows/infra-ci.yml/badge.svg)](https://github.com/Eslam93/MagnaCMS/actions/workflows/infra-ci.yml) ![License](https://img.shields.io/badge/license-MIT-blue)

---

## 1. Live demo

The hosted demo was taken down after the submission window to avoid ongoing AWS charges. The full stack (Amplify static site + App Runner backend + RDS Postgres + Secrets Manager + ECR) is reproducible from scratch via [`infra/DEPLOY.md`](./infra/DEPLOY.md); locally, `docker compose up` runs Postgres + the backend and `pnpm dev` runs the frontend (see §4 below). The demo account is seeded with one brand voice, three content pieces (blog / LinkedIn / email), and one improvement so the dashboard renders real rows immediately on first run.

Demo credentials (local): `demo@magnacms.dev` / `DemoPass123`.

## For reviewers

If you're skimming the repo to evaluate engineering judgment, the load-bearing things this project demonstrates are:

- **Full-stack product delivery end-to-end** — Next.js 15 App Router frontend + FastAPI/async-SQLAlchemy backend + Postgres + AWS deploy, every layer shipped and live.
- **AI provider abstraction** — `ILLMProvider` + `IImageProvider` Protocols with OpenAI, Bedrock-stub, and Mock implementations behind a factory. Swapping providers is a one-class edit.
- **Three-stage parse fallback** for LLM JSON output (structured outputs → corrective retry → graceful degrade with status banner). Live demos don't surface model-misbehavior errors.
- **Custom JWT auth** — short-lived access token (in-memory) + httpOnly refresh cookie + rotation + Origin-based CSRF guard. No Cognito.
- **Async repositories + service-layer architecture** — clean boundaries, single-source-of-truth result projection, FOR UPDATE NOWAIT on image-regen contention.
- **CI gates** — ruff format + lint, mypy, pytest with 80% coverage gate, openapi-typescript spec validation, prettier, eslint, vitest, `next build`, jest snapshots for every CDK stack.
- **AWS CDK infrastructure** — five stacks (Network / Data / Compute / Edge / Observability), strict CDK context validation that fails synth on bad endpoint values, App Runner autoscaling explicitly capped to match RDS connection budget.
- **Honest engineering trade-offs** — every demo-acceptable compromise (public RDS endpoint, local image storage, deferred ElastiCache) is documented in [`ARCHITECTURE.md`](./ARCHITECTURE.md) with the production-grade alternative spelled out.
- **Living development log** — [`DEVLOG.md`](./DEVLOG.md) captures decisions, rejected reviewer findings (with the reason), and round-on-round refinements as PRs landed.

Suggested reading order: this README → [`ARCHITECTURE.md`](./ARCHITECTURE.md) (one page) → §12 "What I'd add next" below → [`DEVLOG.md`](./DEVLOG.md) newest entry.

## 2. What it does

Five core flows:

1. **Generate** — pick a content type (blog, LinkedIn, ad copy, email), describe topic/tone/audience, get polished output.
2. **Pair with image** — one click to auto-generate a matching image from the content.
3. **Improve** — paste existing text, pick a goal, get a refined version with an explanation of what changed.
4. **Manage** — dashboard of all past generations with search, filter, export, soft delete with undo.
5. **Brand voice** — saved profiles that pre-fill style across generations.

## 3. Tech stack

| Layer | Choice |
|---|---|
| Frontend | Next.js 15 + TypeScript + Tailwind + shadcn/ui + TanStack Query + Zod + React Hook Form |
| Backend | FastAPI + Python 3.12 + Pydantic v2 + async SQLAlchemy 2.0 + Alembic |
| Database | PostgreSQL 16 |
| Cache / rate limit / idempotency | Redis 7 _(planned, not wired yet: the backend runs with the in-memory fallback today. ElastiCache provisioning is deferred until the VPC-connector + refresh-token-blocklist work in Phase 11.)_ |
| AI — text | OpenAI `gpt-5.4-mini-2026-03-17` |
| AI — image | OpenAI `gpt-image-2.5-flare` |
| Object storage | S3 bucket provisioned (BlockPublic + SSE) _(generated images currently live on the App Runner local disk via `IImageStorage` → `LocalImageStorage`; the S3 + CloudFront adapter swap is tracked in [#49](https://github.com/Eslam93/MagnaCMS/issues/49).)_ |
| Auth | Custom JWT (httpOnly refresh cookie + rotation + Origin-based CSRF guard) |
| Hosting | AWS App Runner (backend) + Amplify Hosting (frontend) + RDS Postgres _(ElastiCache Serverless Redis lights up with Phase 11 — wired in NetworkStack, not yet provisioned.)_ |
| Infra-as-code | AWS CDK in TypeScript |
| Observability | structlog + CloudWatch + Sentry |
| CI/CD | GitHub Actions |

Rationale for each pick is in [`ARCHITECTURE.md`](./ARCHITECTURE.md).

## 4. Quick start (local)

```bash
git clone https://github.com/Eslam93/MagnaCMS.git
cd MagnaCMS
cp .env.example .env
# Fill in OPENAI_API_KEY and JWT_SECRET. Everything else has sane defaults.
docker-compose up --build
```

Services come up on:

| Service | URL |
|---|---|
| Backend | http://localhost:8000 |
| Postgres | `localhost:5432` (user/pass: `app` / `app`) |

First-time database setup + a seeded demo account:

```bash
docker-compose exec backend alembic upgrade head
docker-compose exec backend python -m app.scripts.seed
```

The frontend is not part of the compose stack; run it with `pnpm dev`:

```bash
cd frontend
pnpm install
pnpm dev   # http://localhost:3000, calls the backend at http://localhost:8000/api/v1
```

## 5. Architecture

Target architecture (CloudFront + Redis are the next-batch additions — see the caveats in §3):

```
Browser
  │
  ├─── app.<domain> ────────→ Amplify Hosting (Next.js SSR + static assets)
  │                              │
  │                              ▼
  │                          api calls to api.<domain>
  │
  └─── images.<domain> ────→ CloudFront ──→ S3 (private generated images)
                              (today: images served by App Runner's
                               `/local-images` static mount until the
                               S3 adapter ships in the deploy batch)

api.<domain>
  │
  ▼
App Runner — FastAPI containers (auto-scale, PUBLIC egress, no VPC connector)
  │
  ├──→ RDS Postgres (public endpoint; SG open on 5432, gated by `rds.force_ssl=1` + strong auto-generated password — App Runner's egress prefix list isn't stable enough to allowlist)
  ├──→ ElastiCache Redis (rate limit, cache, idempotency, refresh-token blocklist)
  │       (today: in-memory fallback until Phase 11)
  ├──→ OpenAI API (gpt-5.4-mini text, gpt-image-2.5-flare image)
  └──→ S3 (target; today: local-disk via IImageStorage protocol)
```

Full rationale and key trade-offs: [`ARCHITECTURE.md`](./ARCHITECTURE.md).

## 6. API documentation

FastAPI generates an OpenAPI 3.1 spec from the route signatures. The
live UI is **only exposed in `local` and `dev`** environments — the
`staging` and `production` builds hide `/docs`, `/redoc`, and
`/openapi.json` so the API surface isn't enumerable from the public
internet (see [`app/main.py`](./backend/app/main.py)).

- **Local / dev only:**
  - Swagger UI: `<api-url>/docs`
  - ReDoc: `<api-url>/redoc`
  - Raw spec: `<api-url>/openapi.json`
- **Staging / production:** live docs are disabled. Dump the spec from
  the source tree instead:

  ```bash
  uv run python -c "import json; from app.main import app; \
    print(json.dumps(app.openapi(), indent=2))" > openapi.json
  ```

  Load the resulting `openapi.json` into a local Swagger viewer or any
  OpenAPI tool.

### Available today

| Group | Endpoints |
|---|---|
| Auth | `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me` |
| Content | `POST /content/generate` (blog post, LinkedIn post, email, ad copy), `GET /content`, `GET /content/:id`, `DELETE /content/:id` (soft delete), `POST /content/:id/restore` (24-hour window) |
| Images | `POST /content/:id/image` (generate or regenerate), `GET /content/:id/images` (every version, newest first) |
| Improver | `POST /improve` (analyze → rewrite), `GET /improvements`, `GET /improvements/:id`, `DELETE /improvements/:id` |
| Brand voices | `GET /brand-voices`, `POST /brand-voices`, `GET /brand-voices/:id`, `PATCH /brand-voices/:id`, `DELETE /brand-voices/:id` |
| System | `GET /health`, `GET /meta` (always on); `GET /openapi.json`, `GET /docs`, `GET /redoc` (local/dev only — gated in `app/main.py`) |

### Planned

| Group | Endpoints |
|---|---|
| Usage | `GET /usage/summary` |
| Exports | `GET /content/:id/export?format=pdf\|docx\|markdown` |

## 7. Repository layout

```
MagnaCMS/
├── README.md                  # this file
├── ARCHITECTURE.md            # key trade-offs + cost estimate
├── DEVLOG.md                  # running journal of decisions and progress
├── docker-compose.yml         # local-dev orchestration
├── .env.example               # environment template
├── .github/workflows/         # CI pipelines
├── backend/                   # FastAPI service
├── frontend/                  # Next.js App Router
└── infra/                     # AWS CDK in TypeScript
```

## 8. Environment variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `AI_PROVIDER_MODE` | yes | `openai` | `openai` / `bedrock` / `mock` |
| `OPENAI_API_KEY` | yes (unless mode=mock) | — | OpenAI key, prepaid |
| `OPENAI_TEXT_MODEL` | no | `gpt-5.4-mini-2026-03-17` | Pinned text model |
| `OPENAI_IMAGE_MODEL` | no | `gpt-image-2.5-flare` | Image gen model (GPT Image, billed per token) |
| `OPENAI_IMAGE_QUALITY` | no | `medium` | `low` / `medium` / `high` |
| `DATABASE_URL` | yes | local compose default | asyncpg connection string |
| `JWT_SECRET` | yes | — | `openssl rand -hex 32` |
| `JWT_ACCESS_TOKEN_TTL_SECONDS` | no | `900` | 15 min |
| `JWT_REFRESH_TOKEN_TTL_SECONDS` | no | `2592000` | 30 days |
| `S3_BUCKET_IMAGES` | yes in prod | dev default | Image bucket |
| `IMAGES_CDN_BASE_URL` | yes in prod | local fallback | CloudFront base URL |
| `NEXT_PUBLIC_API_BASE_URL` | yes (frontend) | `http://localhost:8000/api/v1` | API base URL |
| `SENTRY_DSN` | optional | — | If unset, Sentry silently no-ops |
| `LOG_LEVEL` | no | `INFO` | structlog level |
| `AWS_REGION` | yes for deploy | `us-east-1` | AWS region |

Full annotated set in [`.env.example`](./.env.example).

## 9. Running tests & local CI parity

The CI workflows (`.github/workflows/backend-ci.yml`, `frontend-ci.yml`,
`infra-ci.yml`) run more than just the test suites — they also gate on
**formatting** (`ruff format --check`, `prettier --check`), **type-checks**,
**coverage thresholds**, and the **production build**. Run the full set
locally before pushing to avoid the "tests passed locally but CI failed
on prettier" trap:

```bash
# Backend — mirrors backend-ci.yml exactly (needs Postgres at DATABASE_URL)
cd backend
uv sync --frozen
uv run ruff check .
uv run ruff format --check .            # format gate (CI fails if dirty)
uv run mypy app
uv run alembic upgrade head
# REQUIRE_DB=1 fails the integration tests, instead of skipping them, if Postgres is unreachable
REQUIRE_DB=1 uv run pytest --cov=app --cov-fail-under=80   # 80% coverage gate
# OpenAPI spec must be consumable by the frontend's codegen:
uv run python -c "import json; from app.main import app; \
  json.dump(app.openapi(), open('openapi-tmp.json', 'w'))"
npx openapi-typescript@7.4 openapi-tmp.json -o /dev/null
rm openapi-tmp.json

# Frontend — mirrors frontend-ci.yml exactly
cd frontend
pnpm install --frozen-lockfile
pnpm lint
pnpm format:check                       # format gate (CI fails if dirty)
pnpm typecheck
pnpm test
pnpm build                              # next build must succeed

# Infra — mirrors infra-ci.yml exactly
cd infra
npm ci
npm run build
npm test
```

Fix surfaces:

| If this fails | Run |
|---|---|
| `ruff format --check` | `uv run ruff format .` |
| `pnpm format:check` | `pnpm format` |
| `pnpm lint` (auto-fixable) | `pnpm lint --fix` |

Playwright E2E (`@playwright/test` + a happy-path spec) is on the backlog
but not wired yet — see [the open backlog](https://github.com/Eslam93/MagnaCMS/issues/86).

## 10. Deployment

Infrastructure is defined in [`infra/`](./infra/) using AWS CDK in TypeScript. Five stacks compose linearly:

| Stack | Owns |
|---|---|
| `magnacms-dev-network` | VPC + 2 AZs (public subnets only) + RDS/Redis security groups |
| `magnacms-dev-data` | RDS Postgres, S3 images bucket, Secrets Manager (JWT + OpenAI key). ElastiCache Serverless Redis was previously here but is currently dropped pending the Phase-11 VPC-connector work. |
| `magnacms-dev-compute` | ECR repo, App Runner backend service, IAM roles, Fargate task definition for migrations |
| `magnacms-dev-edge` | Amplify hosting app (CloudFront-for-images deferred to Phase 5; see [DEVLOG.md](./DEVLOG.md)) |
| `magnacms-dev-observability` | CloudWatch log groups with 14-day retention |

### First deploy (manual)

See [`infra/DEPLOY.md`](./infra/DEPLOY.md) for the 11-step runbook. Highlights:

```bash
aws configure
cd infra && npm ci
npx cdk bootstrap aws://<account>/us-east-1
npx cdk deploy --all -c env=dev
# Paste OpenAI API key into Secrets Manager
# Run migrations as one-off Fargate task
# Smoke-test /api/v1/health
# IP-identity preflight (DEPLOY.md step 8 — critical)
```

### Subsequent deploys

`.github/workflows/deploy.yml` is `workflow_dispatch`-only and uses an OIDC-assumed role (no long-lived AWS keys in GitHub Secrets). The OIDC trust relationship + `AWS_DEPLOY_ROLE_ARN` repo secret aren't yet configured, so until that's wired the deploy path is manual:

```bash
# Manual deploy (current path) — full sequence in infra/DEPLOY.md
ECR_URI=$(aws ecr describe-repositories --repository-names magnacms-dev-backend --query 'repositories[0].repositoryUri' --output text)
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin "$ECR_URI"
docker buildx build --platform linux/amd64 --provenance=false \
  -t "$ECR_URI:$(git rev-parse --short HEAD)" -t "$ECR_URI:latest" --load backend/
docker push "$ECR_URI:$(git rev-parse --short HEAD)"
docker push "$ECR_URI:latest"
# Run alembic via the migration Fargate task (DEPLOY.md §6 has the full command)
APPRUNNER_ARN=$(aws cloudformation describe-stacks --stack-name magnacms-dev-compute \
  --query "Stacks[0].Outputs[?ExportName=='magnacms-dev-compute-apprunner-service-arn'].OutputValue" --output text)
aws apprunner start-deployment --service-arn "$APPRUNNER_ARN"
```

Frontend deploys via `aws amplify create-deployment` + presigned-URL zip upload (avoids needing GitHub→Amplify OAuth):

```bash
cd frontend
NEXT_OUTPUT=export NEXT_PUBLIC_API_BASE_URL=<api-base> pnpm build
python -c "import os, zipfile; root='out'; \
  z = zipfile.ZipFile('magnacms-frontend.zip','w',zipfile.ZIP_DEFLATED); \
  [z.write(os.path.join(d,f), os.path.relpath(os.path.join(d,f), root).replace(os.sep,'/')) \
   for d,_,files in os.walk(root) for f in files]; z.close()"
CREATE=$(aws amplify create-deployment --app-id $AMPLIFY_APP_ID --branch-name main)
ZIP_URL=$(echo "$CREATE" | jq -r '.zipUploadUrl'); JOB_ID=$(echo "$CREATE" | jq -r '.jobId')
curl -fsS -X PUT --data-binary @magnacms-frontend.zip "$ZIP_URL"
aws amplify start-deployment --app-id $AMPLIFY_APP_ID --branch-name main --job-id "$JOB_ID"
```

Once the OIDC role is wired, `deploy.yml` (manual or push-triggered) supersedes both of the above.

### CI gates (no AWS touch)

| Workflow | Triggers on | Runs |
|---|---|---|
| [`backend-ci`](./.github/workflows/backend-ci.yml) | `backend/**` changes | uv sync, ruff, mypy, alembic upgrade, pytest |
| [`frontend-ci`](./.github/workflows/frontend-ci.yml) | `frontend/**` changes | pnpm install, lint, prettier, tsc, vitest, next build |
| [`infra-ci`](./.github/workflows/infra-ci.yml) | `infra/**` changes | npm ci, jest snapshots, `cdk synth --all -c env=dev` |
| [`model-lifecycle`](./.github/workflows/model-lifecycle.yml) | Weekly (Mon 06:17 UTC), manual, and PRs touching the model catalog, the check script or `config.py` | `python -m app.scripts.check_model_lifecycle`: fails if a configured OpenAI model is unknown, unpriced, shut down, shutting down within 30 days, or listed on OpenAI's deprecations page |

### Teardown

```bash
cd infra && npx cdk destroy --all -c env=dev
# Plus delete the Amplify app manually from console (CDK has trouble with
# Amplify apps connected to GitHub)
```

## 11. Architecture decisions

Detailed in [`ARCHITECTURE.md`](./ARCHITECTURE.md). Headlines:

- **OpenAI direct over AWS Bedrock** — one key covers text + image, no Anthropic use-case form, no Nova Canvas LEGACY/EOL story.
- **No VPC connector on App Runner** — keeps AWS APIs and OpenAI reachable without NAT Gateway.
- **Public RDS, SG open on 5432, gated by TLS + strong password** — App Runner has no stable egress prefix list to allowlist, so security relies on `rds.force_ssl=1` + the auto-generated Secrets-Manager-managed password.
- **Custom JWT over Cognito** — full control over refresh rotation + Redis blocklist; smaller IAM surface.
- **Non-streaming content generation** — structured JSON outputs don't stream cleanly; staged loading UI gives the perceived-performance benefit without the bug surface.

## 12. What I'd add next

If the clock kept running, in priority order:

### Deploy-batch follow-ups (1–2 days of work each)

1. **S3-backed `IImageStorage` adapter** ([#49](https://github.com/Eslam93/MagnaCMS/issues/49)). The protocol seam already exists — `LocalImageStorage` lives behind `IImageStorage`, and the projection layer already builds image URLs from `s3_key` + storage config at response time (not from a persisted `cdn_url`). The swap is a one-class implementation (`S3ImageStorage` calling `boto3.upload_fileobj`), a config flag, and an alembic-safe column-nullable migration. Removes the only known limitation in the demo flow (the cross-container caveat where Fargate-seeded image bytes never reach the App Runner instance).
2. **CloudFront in front of S3.** Public-read distribution with signed-URL option for protected images. Drops App Runner egress charges, adds CDN caching, and the existing `IMAGES_CDN_BASE_URL` env var already isolates the change to a CDK + config update — no application code needs to know.
3. **Real OIDC role for `deploy.yml`** so the manual `docker push` + `aws apprunner start-deployment` + `aws amplify create-deployment` dance becomes one workflow click. The workflow exists but the IAM trust relationship isn't wired; ~30 min of one-time AWS setup.

### Submission-bonus items

4. **Markdown export** for content pieces ([#75](https://github.com/Eslam93/MagnaCMS/issues/75), size:S). The brief asks for view/copy/**download**/delete in the dashboard; download isn't shipped. Markdown lift is small because `rendered_text` is already the canonical Markdown — it's a `GET /content/:id/export?format=md` route + a download button. PDF/DOCX exports are the bigger lift; tracked separately as [#73](https://github.com/Eslam93/MagnaCMS/issues/73) / [#74](https://github.com/Eslam93/MagnaCMS/issues/74).

### Production hardening (Phase 11 — VPC connector territory)

5. **Move RDS into a private subnet + add RDS Proxy + IAM-auth.** The current `0.0.0.0/0` SG + `rds.force_ssl=1` + strong-password posture is acceptable for a demo behind custom auth with no regulated data; not production-grade. Requires an App Runner VPC connector (~$32/mo NAT or per-service VPC endpoints), so this also unlocks ElastiCache (which is provisioned in the network stack but not in the data stack — see PR #143's removal).
6. **Redis-backed refresh-token blocklist** ([#88](https://github.com/Eslam93/MagnaCMS/issues/88)) and **idempotency middleware** ([#89](https://github.com/Eslam93/MagnaCMS/issues/89)) — both wait on the VPC connector. Today's in-memory fallback covers the demo but won't survive App Runner instance restarts.
7. **Job-table dedupe for image regeneration.** PR #144 added a NOWAIT lock that fails the second concurrent request fast with `409 IMAGE_GENERATION_IN_PROGRESS`, but the winner still holds the DB connection through ~20s of upstream LLM + image-gen + storage calls. The proper fix is a `generation_jobs` table with the in-flight job ID returned to subsequent callers; out of scope while the demo budget is small.

### Frontend polish I'd want before "ship to real marketing teams"

8. **Loading skeletons** on the dashboard and detail modal ([#87](https://github.com/Eslam93/MagnaCMS/issues/87)). Today the dashboard shows "Loading…" text — fine for a demo, jarring in a real product.
9. **Mobile responsive pass** ([#84](https://github.com/Eslam93/MagnaCMS/issues/84)). The layout works on a phone but the dashboard cards are awkward; needs a sweep, not a redesign.
10. **Accessibility audit** ([#85](https://github.com/Eslam93/MagnaCMS/issues/85)). Buttons are keyboard-reachable and the form inputs have proper labels, but I haven't run axe or screen-readered the flows.

### Explicitly deferred (not on the roadmap)

- **Password reset / email verification.** Would need an SES domain identity and transactional templates — out of scope for the deliverable. Users who forget their password today get told to re-register; not great, intentional.
- **AWS Bedrock Nova Canvas migration plan.** Nova Canvas is `LEGACY` with EOL **2026-09-30**, so the longer-term migration is "wait for Nova Image v2." OpenAI's GPT Image models (default `gpt-image-2.5-flare`) are the only image-gen path today; if Bedrock becomes cheaper or required, the `IImageProvider` interface accepts a one-class swap (the Bedrock stub is already in `app/providers/image/bedrock.py`).
- **Multi-tenant / org scoping.** Current auth is per-user. Org/workspace scoping would touch every owner-filter in the repositories — not on the roadmap unless a real customer asks.

## 13. Development log

See [`DEVLOG.md`](./DEVLOG.md) — an ongoing journal of decisions, trade-offs, and progress (newest entries first). Includes actual elapsed time per phase as the project moves forward.

## 14. License

[MIT](./LICENSE).
