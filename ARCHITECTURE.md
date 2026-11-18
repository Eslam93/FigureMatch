# Architecture

The choices behind the studio, and the trade-offs that came with them. Most were made in
May 2026, when the studio was built and briefly hosted on AWS; the sections below say
which still hold. The changes made in November 2026 each have a record of their own in
[`docs/decisions/`](./docs/decisions/).

## What runs today

Nothing is deployed. The stack described under [The May deployment](#the-may-deployment)
was taken down in June 2026. The studio runs on one machine:

- The backend (FastAPI) and Postgres start with `docker compose`; the frontend is a
  Next.js app served by `pnpm dev`, or built as a static export.
- Text and images come from OpenAI, or from canned mock output with no key.
- Generated images are written to the backend's local disk and served from
  `/local-images`. `IImageStorage` is the seam an S3 adapter would plug into; no S3
  adapter exists.
- Rate limits are counters in each backend process's memory. There is no Redis.

## Stack

| Concern | Choice | Alternatives the May plan rejected |
|---|---|---|
| Text generation | OpenAI `gpt-5.4-mini-2026-03-17` | AWS Bedrock with Claude (an access form per AWS account, and a cross-region inference profile); Anthropic direct (no image model) |
| Image generation | OpenAI `gpt-image-2.5-flare`, since November. In May it was `gpt-image-1`, which OpenAI shut down on 2026-10-23 | AWS Bedrock Nova Canvas (listed by AWS as legacy in May); Replicate or fal.ai (another account and bill) |
| Auth | Custom JWT, refresh token in an httpOnly cookie, single-use rotation | Cognito (more moving parts, less control over rotation); Auth0 (cost) |
| Content generation | Not streamed | Server-sent events (structured JSON does not stream cleanly; a partial parse is broken output) |
| Database | PostgreSQL 16 | |

## Decisions that still hold

### 1. OpenAI direct, behind two interfaces

In May, Bedrock needed a per-account access form for Claude and a cross-region inference
profile, and its image model was listed as legacy. One OpenAI key covered text and
images. The backend calls models only through `ILLMProvider` and `IImageProvider`, with
an OpenAI and a mock implementation of each. The Bedrock classes beside them are stubs
that raise on construction, and the backend refuses to boot in `bedrock` mode: no
Bedrock call has ever been written. Adding a provider means implementing the two
interfaces, not swapping one class.

### 2. Custom JWT, not Cognito

Single-use refresh-token rotation with reuse detection is easier to express in
application code than in Cognito's lifecycle hooks. Presenting a spent refresh token
revokes every refresh token the user holds. Until November that revocation was rolled
back by the request's own error handling, so it never took effect; see
[`audit/`](./audit/) and [decision 0002](./docs/decisions/0002-commit-reuse-revocation-before-the-401.md).
There is no token blocklist and no Redis behind any of this.

### 3. Three stages for structured output

1. The model is asked for JSON under a strict schema (`response_format: json_schema,
   strict: true`) and the reply is validated with Pydantic.
2. If validation fails, one corrective retry runs under the same strict schema, with the
   reply shown back and each failing field named.
3. If that fails too, the raw reply is stored as `rendered_text` with
   `result_parse_status = failed`, and the frontend shows it with a banner.

A first reply cut off at the length limit or refused by the content filter does not
reach stage 2: the request fails with a typed error (`AI_OUTPUT_TRUNCATED`,
`AI_CONTENT_REJECTED`). So the user usually, not always, gets something to work with.
Until November, stage 2 dropped the schema and told the model its JSON was invalid,
which was rarely the problem; see
[decision 0005](./docs/decisions/0005-corrective-retry-keeps-the-strict-schema.md).

### 4. No streaming, a staged loader instead

A partial JSON parse is broken output, so generation is not streamed. The frontend
cycles "Analyzing topic…", "Drafting…", "Polishing…" while the request runs. The
improver is not streamed either.

## The May deployment

From 15 May to June 2026 the studio ran on AWS: the backend on App Runner, the frontend
as a static export on Amplify, Postgres on RDS. [`infra/`](./infra/) holds the CDK app
that described it, and [`infra/DEPLOY.md`](./infra/DEPLOY.md) the runbook it was
deployed with by hand. Both are kept as a record; neither has been run since, and the
runbook is known to be incomplete. Two of its choices are worth stating plainly, because
they were acceptable for a short demo and would not be for anything else.

### App Runner without a VPC connector

With a VPC connector, App Runner loses public egress unless a NAT gateway (about $32 a
month) or a VPC endpoint per AWS service is added, and the backend must reach OpenAI.
App Runner stayed public instead. AWS publishes no stable egress range for App Runner in
that mode, so the database's security group could not be narrowed to it.

### A public RDS endpoint

As a consequence, the database's security group allowed `0.0.0.0/0` on port 5432. What
protected it was TLS required on both sides (`rds.force_ssl=1`, and `?ssl=require` in
the DSN) and a strong password generated by CDK and kept in Secrets Manager, with
password rotation never set up. That is a demo's trade-off. A service with users would
use a VPC connector, RDS Proxy, IAM authentication and rotation.

### What it was estimated to cost

Estimated in May from the AWS pricing pages, for one environment with one App Runner
instance always on. It was never compared with a bill in this repository, and today's
AWS cost is nil because nothing is deployed.

| Service | Sizing | Estimated monthly cost (USD) |
|---|---|---|
| App Runner | 1 vCPU, 2 GB, autoscaling from 1 to 3 instances | about $50 |
| RDS Postgres | `db.t4g.micro`, 20 GB gp3, public endpoint, no backups kept | about $15 |
| S3 | A bucket created and never written to | about $0 |
| Amplify Hosting | Static export, a few manual deploys a day | under $1 |
| Secrets Manager | 3 secrets | about $1.20 |
| CloudWatch Logs | 14-day retention | about $2 |
| ECR | One image repository, last 10 tags kept | under $1 |
| **Total** | | **about $70** |

OpenAI is billed per token at the dated rates in
[`backend/app/core/model_catalog.py`](./backend/app/core/model_catalog.py). Every call's
cost is computed from the token counts the API reports. The per-piece estimates the May
documents gave were computed from a wrong price table and were removed, not re-estimated.

## Not built

These were in the May plan and do not exist. Some still have open issues from that plan.

- An S3 image storage adapter and CloudFront in front of it
  ([#49](https://github.com/Eslam93/FigureMatch/issues/49)).
- A deploy pipeline. `deploy.yml` ran once, on 15 May 2026, and failed: its OIDC role was
  never configured. Every deploy was done by hand.
- A refresh-token blocklist, idempotency keys, per-endpoint and per-account rate limits,
  all of which the plan put on Redis
  ([#88](https://github.com/Eslam93/FigureMatch/issues/88),
  [#89](https://github.com/Eslam93/FigureMatch/issues/89),
  [#90](https://github.com/Eslam93/FigureMatch/issues/90)).
- PDF and DOCX export ([#73](https://github.com/Eslam93/FigureMatch/issues/73),
  [#74](https://github.com/Eslam93/FigureMatch/issues/74)). Markdown export exists.
- Usage accounting in a table of its own. Cost and tokens are recorded on each content
  piece, improvement and image.
- Password reset, email verification, and anything beyond one user per account.
- End-to-end browser tests.
