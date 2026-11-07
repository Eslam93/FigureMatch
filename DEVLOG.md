# Development log

A running journal of decisions, trade-offs, and progress on FigureMatch. Newest entries first. Each entry is written when something interesting happens — not on a schedule — so the cadence reflects the actual pace of work.

---

## 2026-05-16 — Demo-day docs polish (PR #147)

A small README + ARCHITECTURE pass to close out the P12 finalization checklist before the demo. No code touched.

### README §1 stopped lying about the frontend

The "frontend — coming up — Amplify zip awaiting one-click upload" placeholder was still there until this morning. The frontend has been live on Amplify since the manual zip upload last night; §1 now reflects that. The seeded-demo description also got an honesty pass: pre-seeded image rows exist in the DB but their PNG bytes are stranded on the Fargate seed-task container disk (cross-container effect of `LocalImageStorage`), so seeded thumbnails 404. The live regen path produces real `gpt-image-1` outputs on the App Runner instance and renders correctly, so the demo flow is "log in, click Generate image" rather than "see pre-seeded thumbnails."

### §10 documents the actual deploy flow, not the aspirational one

`deploy.yml` exists and uses GitHub-OIDC, but the `AWS_DEPLOY_ROLE_ARN` repo secret isn't configured, so the workflow fails at the `Configure AWS credentials` step. The live deploys were done manually: `docker buildx push` + `aws apprunner start-deployment` for the backend, `aws amplify create-deployment` + presigned-URL zip upload for the frontend (avoids the GitHub→Amplify OAuth that the CDK-created app doesn't expose). §10 now contains those exact commands so future-me doesn't waste an hour rediscovering them, and notes that `deploy.yml` is the eventual target once the OIDC role is wired.

### ARCHITECTURE.md AWS cost table is no longer "TBD"

The table now lists real numbers per current sizing: ~$70/month total. The two largest line items (App Runner always-on at $50, RDS `db.t4g.micro` at $15) are explicitly annotated as intentional trade-offs — scale-to-zero on App Runner would save ~$45/mo but make the first request after idle a 10s cold boot; RDS in a private subnet + RDS Proxy would add ~$15–25/mo in NAT + Proxy charges. The "What's next" section was replaced with the actual roadmap items (S3 adapter, CloudFront, OIDC role wiring, Phase 11 hardening, exports, frontend polish) linked to their GitHub issues, plus a "considered but deferred" section that explicitly lists password reset, the Bedrock migration plan, and multi-tenant scoping as out-of-scope.

---

## 2026-05-15 — Live deploy: first end-to-end production run

The first manual run through `infra/DEPLOY.md` end-to-end, applying every fix from the previous four PRs in order. Three surprises worth recording.

### The CDK-created Amplify app doesn't expose Git-connect in the console

EdgeStack creates the Amplify app and the `main` branch resource, but without a `Repository` property. The current Amplify Gen-2 hosting console (the one served at `console.aws.amazon.com/amplify/apps/<id>`) does not surface a "Connect repository" / "Reconnect branch" button anywhere — `App settings → General` shows the app metadata, `App settings → Branch settings` lists branches, neither lets you attach a Git source after the fact. The path forward was either (a) generate a GitHub PAT and call `aws amplify update-app --repository ... --access-token` from CLI, or (b) skip Git entirely and use the manual-zip path. We went with (b): build locally with `NEXT_OUTPUT=export pnpm build`, zip the `out/` contents (via Python's `zipfile` module — PowerShell's `Compress-Archive` produces backslash-separated paths that Amplify serves as literal filenames, so all `_next/static/chunks/...js` chunks 404'd on the first attempt), then `aws amplify create-deployment` + PUT to the presigned URL + `start-deployment`. Future code updates need a fresh zip each time; the Git connection is a follow-up.

### Fargate task default-SG has no egress rules

The migration task failed at startup with `ResourceInitializationError: ... canceled, context deadline exceeded` trying to fetch the RDS secret. The VPC's default SG has `IpPermissionsEgress: []` (CDK locks down the VPC default SG out of paranoia), so the Fargate task — which uses the default SG when `aws ecs run-task` doesn't pass one explicitly — has no outbound. Fixed by passing the dedicated `figurematch-dev-fargate-egress` SG that already existed for this purpose. `DEPLOY.md` §6 now includes the SG lookup in the runbook so this doesn't bite the next operator.

### `/app/local_images` permission error on first image-gen

The `LocalImageStorage.store()` call tries to `mkdir /app/local_images` on first write. `WORKDIR /app` in the Dockerfile is owned by root with 755 permissions, and the container drops to the non-root `app` user before runtime, so the mkdir bombed with `PermissionError: [Errno 13]`. Caught it via the seed task, which would have surfaced as the first user click anyway. Dockerfile now pre-creates the directory and chowns it to `app` before the USER swap. Goes away when the S3 adapter ships.

### What the smoke test confirmed end-to-end

Login → dashboard with seeded content → generate blog post (real `gpt-5.4-mini-2026-03-17`, 1314 words, staged loader works) → generate LinkedIn post → generate image (real `gpt-image-1`, 1024×1024, ~$0.04) → image renders in the detail modal → improver round-trip with side-by-side diff → brand voice create / edit / delete → soft delete + Undo restore. Cost during the smoke: roughly $0.06 in upstream calls. Total wall time from clean account state to all-flows-verified: about eight minutes.

---

## 2026-05-15 — Deploy correctness pass + CI flake fix (PR #145, #146)

Strict CDK context validation, App Runner autoscaling wired up, DB pool right-sized for the bounded fleet, plus a Dockerfile permission fix and a couple of test-fixture corrections discovered while running the live deploy.

### `requireContext` only checked for a string — `lol` and `https://localhost` passed synth

The PR #144 work made `cors_origins` and `images_cdn_base_url` CDK context required, but the check was just "non-empty string." `-c cors_origins=https://app.example.com/foo` would synth fine — and then the deployed backend's CORS allowlist would contain `https://app.example.com/foo` while the browser's `Origin` header is origin-only, so the CORS check would fail at runtime. Extracted `resolveEndpointContext()` as a pure module with full shape validation: https only, no loopback hosts, no `.invalid` TLD (unless `allow_synthetic_endpoints=true` is set), CSV entries de-duped, trailing slashes stripped, return value canonicalized via `url.origin` so the persisted value matches the browser's `Origin` header byte-for-byte. 19 new unit tests cover every rejection branch; making the resolver a pure function meant they didn't need to instantiate a CDK App.

### `synthetic-endpoints=true` is now loud, not silent

When `-c allow_synthetic_endpoints=true` is used, the app prints a `console.warn` to stderr and tags every resource with `synthetic-endpoints=true`. `cdk.Annotations.of(app).addWarning()` was the first attempt but doesn't bubble up reliably from the App scope in CDK v2 — the CLI walks Stack-scoped annotations only. Stack tags survive into CloudFormation, which is what an operator notices weeks later when they wonder why the demo broke.

### App Runner autoscaling: wired, not just declared

ComputeStack passed `autoScalingConfigurationArn: undefined` and relied on the App Runner per-account default (min 1, max **25**), even though `cfg.apprunnerMinInstances` / `apprunnerMaxInstances` were set to `1` / `3`. The cfg values were silently ignored. Added an explicit `CfnAutoScalingConfiguration` that consumes those values, plus a contract test asserting the resource exists with the expected min/max/concurrency. The 1/3 cap is what the DB pool sizing is now bounded against — without the cap, a fully-scaled-out fleet would have wanted up to 100 concurrent connections against `db.t4g.micro`'s ~87 `max_connections`.

### DB pool right-sized for the new cap

Previously `pool_size=15, max_overflow=20` (up to 35 connections per instance × 3 instances = 105, vs 87 max). Dropped to `pool_size=10, max_overflow=10` (20 per instance × 3 = 60, with ~25 headroom for migrations + admin sessions). Also fixed an overclaim in the docstring: the NOWAIT lock (from PR #144) makes the *losing* image-regen request release its connection immediately, but the *winner* still holds the row lock through ~20s of LLM + image-gen + storage calls. The earlier docstring said "no longer holds a connection across upstream calls" — only the loser doesn't.

### Two integration tests were flaky on Postgres timing

`test_list_returns_paginated_envelope_newest_first` and `test_list_returns_newest_first_with_previews` both create rows in rapid succession and assert strict insert-order ordering. PR #144's `ORDER BY created_at DESC, id DESC` made the order deterministic *when timestamps tie*, but the tests inherited a fragile assumption: Postgres `now()` is `transaction_timestamp()` and the integration fixture wraps every test in a single outer transaction (savepoint-per-session pattern in `tests/integration/conftest.py`), so every row gets an identical `created_at`. With timestamps tied, the deterministic tiebreaker — UUID descending — doesn't match insert order. The first attempt to fix it added `asyncio.sleep(0.02)` between API calls, which doesn't help because the shared-transaction `now()` is constant regardless of wall-clock gaps. The real fix is in the test: assert the actual contract (all IDs returned + ordered by id DESC when timestamps tie), not the assumption (strict insert-order). The user-facing "newest first by `created_at`" contract still works in production where users don't insert multiple rows in one transaction.

### CI format drift — the long-standing red badge cause

Every backend-ci and frontend-ci run since slice-3 had been failing at the formatter step. The lint, type-check, and test gates passed locally, so the failures looked silent unless you specifically opened the workflow runs. Root cause: my local validation loop ran `ruff check` (lint only), not `ruff format --check` (CI gate); same shape on the frontend — `eslint` + `tsc` + `vitest`, but no `prettier --check` and no `next build`. Six backend files and seven frontend files had accumulated format drift. Applied `ruff format` + `prettier --write`, then rewrote README §9 ("Running tests & local CI parity") with the full command set CI actually runs so this doesn't recur. The README is now the source of truth for the verification recipe.

### What didn't ship in this batch

The deploy.yml OIDC role still isn't wired — the workflow exists but the GitHub-OIDC trust relationship and `AWS_DEPLOY_ROLE_ARN` secret aren't configured, so the live deploys this batch were done manually. Tracked as one of the follow-up items in ARCHITECTURE.md's "What's next."

---

## 2026-05-15 — AI-review round 2: deploy regression + observability gaps (PR #144)

Round 2 review surfaced one regression PR #143 introduced (the CDK localhost-CORS default brick) plus four real gaps in the surrounding work. The triage report is in `.private/REVIEW_PROMPT.md`; the executive summary is "the validator I added rejected the CDK defaults the same PR didn't update."

### CDK context now required, no synthetic defaults

The original direction was "ship synthetic placeholders like `https://figurematch-dev.invalid` so the synth never fails." User pushback was correct: that trades a startup/deploy failure for a silent user-visible runtime failure. Now `bin/figurematch.ts` requires `-c cors_origins=...` and `-c images_cdn_base_url=...` for non-local synth; missing values throw with a useful error message. The escape hatch is `-c allow_synthetic_endpoints=true`, which substitutes `https://figurematch-bootstrap.invalid` placeholders for first-bootstrap deploys where the Amplify URL isn't known yet. The placeholders pass the backend's `Settings` validator (so App Runner boots) but fail loudly on the first real request (the browser's CORS check fails noisily, which is the point — bootstrap mode is supposed to be obvious). DEPLOY.md §8 was rewritten: console env-var edits are gone, the only supported path is `cdk deploy figurematch-dev-compute -c cors_origins=... -c images_cdn_base_url=...`.

### CSRF moved inside RequestID so 403s carry observability

The CSRF Origin guard added in PR #143 was wrapping RequestID, which meant a CSRF rejection's 403 envelope had `meta.request_id: null` and the response carried no `X-Request-ID` header. Reorder: `add_middleware(CsrfOriginMiddleware)` BEFORE `add_middleware(RequestIDMiddleware)` — Starlette's reverse-order semantics put CSRF deeper than RequestID, so RequestID wraps CSRF on the way in and on the way out. A new test asserts the 403 response carries `X-Request-ID` so this doesn't regress quietly.

### CSRF scope extended to login + register

`/auth/login` and `/auth/register` join `/auth/refresh` and `/auth/logout` in `_PROTECTED_PATHS`. The threat model isn't the rate-limit DoS the review originally framed (the limiter buckets per real-TCP-peer-IP, so an attacker can't pollute the victim's bucket); it's login-CSRF — attacker forces the victim's browser to log into the attacker's account, then the victim creates content under that identity. Rare but real, two-line fix, ships now.

### Image-regen double-click: NOWAIT + 409, not queue-and-pay

`with_for_update()` was serializing concurrent regenerations but held the row lock — and therefore the DB connection from the small asyncpg pool — through ~20s of LLM + image-gen + storage calls. Two contending users meant two paid generations, separated by a 20s queue. Switched to `with_for_update(nowait=True)` in `ContentRepository.get_for_user`, and the image service translates the resulting Postgres SQLSTATE `55P03` (`lock_not_available`) into a `ConflictError(code="IMAGE_GENERATION_IN_PROGRESS")` → 409. The loser fails fast, the winner doesn't fight for a connection, and the user sees a clear "generation already in progress" message instead of an opaque 20s wait. A unit test mocks the DBAPIError with the right `sqlstate` attribute and asserts the 409 fires. Proper dedupe — a job table that returns the in-flight job ID to subsequent callers — is Phase 11.

### Password schema honesty + Pydantic-level validation

`RegisterRequest` only declared `min_length=8, max_length=128`; the letter/digit/72-byte rules lived in `validate_password_strength` (service layer), so OpenAPI consumers saw the lenient bounds and missed the real constraints. The strength check is now a Pydantic `field_validator` on `RegisterRequest.password` that calls into `core/security.py` (keeping the canonical implementation there), and `max_length` is tightened to 72 to match bcrypt's silent-truncation boundary. `LoginRequest` keeps the lenient max (legacy accounts with weak passwords must still authenticate) but enforces the 72-byte guard via a split-out `validate_bcrypt_password_bytes` helper, so bcrypt's silent truncation can't let a wrong password through.

### Buildx flag conflict that would have broken the next CI deploy

`deploy.yml` had both `--output=type=image,push=false` and `--load` on the buildx command. Buildx rejects multiple outputs; this would have failed at the first push. Dropped `--output=...`; `--load` does the right thing (single-platform, push to local daemon, then `docker push` from there).

### What was deferred

- `generated_images.cdn_url` column cleanup: still written but no longer read for URL construction. Harmless redundancy. A safety-net test now pins the contract that the projection ignores stale row `cdn_url` values; the column gets dropped or nullable-migrated when Phase 9 establishes migration discipline.
- Strict OpenAPI codegen diff in CI: the spec-validity check landed (CI runs `openapi-typescript` against `app.openapi()` to catch generator-unsafe specs), but the strict `git diff --exit-code` against committed `types/api.d.ts` waits for that file to become generator output instead of a hand-stub.

---

## 2026-05-15 — AI-review round 1: security, storage, deploy hardening (PR #143)

The first cross-codebase AI review. Two GPT-5-family reviewers (independent prompts, blind to each other's output) returned ~20 findings between them. Triage classified each as Must-Fix / Should-Fix / Optional / Reject; the bundle below is everything classified Must-Fix or Should-Fix in a single PR rather than five small ones. Shipping as one PR matches the user's preference for refactors-with-clear-scope and avoids the test-churn cost of touching the same files across multiple rounds.

### CSRF Origin guard on cookie-only POSTs

Refresh-cookie endpoints (`/auth/refresh`, `/auth/logout`) were vulnerable to a low-shaped cross-site POST attack: an attacker page can `fetch("/api/v1/auth/refresh", { credentials: "include" })` because `SameSite=none` (required for cross-domain Amplify↔App Runner) sends the cookie, and force a token rotation (DoS-shaped). The new `CsrfOriginMiddleware` enforces an `Origin` / `Sec-Fetch-Site` allowlist on those routes specifically. No double-submit cookie, no token — just the Origin policy. Allowed shapes: no `Origin` header (curl, server-to-server), `Sec-Fetch-Site: same-origin`, or `Origin` in the configured CORS allowlist. Anything else returns 403 (not 401, to avoid triggering the frontend's refresh-and-retry loop). Bearer-authenticated routes don't need the guard — browsers don't auto-attach the access token from an attacker origin.

### Rate-limit pattern matching for dynamic paths

`/content/{id}/image` and `/improve` were unprotected by the exact-match rate limiter because the path contained a dynamic segment. Added `RateLimitRule` regex matching; image-gen now caps at 6/min and improve at 10/min per (path-pattern, real-TCP-peer-IP). The same bucket-eviction behavior applies — no surprises for clients hitting the legacy exact-match routes.

### Image storage: store key only, derive URL at projection time

`IImageStorage.store()` now returns just the storage key (`<uuid>.png`), and `public_url_for(key)` derives the URL at response-projection time from `IMAGES_CDN_BASE_URL` + key. The router projects every image's `cdn_url` fresh from storage config, so the row's persisted `cdn_url` is now redundant cache rather than authoritative. The point: when the S3 + CloudFront adapter ships in the deploy batch, swapping `LocalImageStorage` for `S3ImageStorage` is a config change and a one-class edit — not a data migration that rewrites every existing row's URL. The persisted `cdn_url` still gets written (backwards-compat for any reader that hasn't switched to the projection path), but old rows projected through the router pick up the new URL automatically.

### Image regen serialized at the DB layer

`SELECT ... FOR UPDATE` on the parent `ContentPiece` row inside the regen transaction prevents two concurrent requests from racing on the partial unique index that guards "at most one current image per piece." The lock is held until commit, which means concurrent regens queue rather than fight. (Round 2 then turned this into a NOWAIT-and-fail-fast pattern — see the next entry.)

### Migration task secrets

The Fargate migration task imports `app.main`, which boots the `Settings` validator. The validator rejects placeholder values for `JWT_SECRET` and `OPENAI_API_KEY` in non-local envs, so the migration task failed at startup with a config-validation error before Alembic ever ran. Fixed by mounting both secrets via `EcsSecret.fromSecretsManager`; the auto-generated IAM grants cover the read.

### App Runner sized up before image-gen OOM

App Runner was provisioned at 0.25 vCPU / 0.5 GB. `gpt-image-1` responses carry a 1–3 MB base64 PNG; with FastAPI + Pydantic + the OpenAI SDK already resident (~200 MB), that's OOM-adjacent under any concurrent image-gen load. Bumped to 1 vCPU / 2 GB, which leaves real headroom without pushing the App Runner pricing tier dramatically.

### ElastiCache dropped from DataStack

The cluster was being provisioned but unreachable: App Runner has no VPC connector, so the in-VPC Redis endpoint never resolves from the backend. The cluster was running, billed, and useless. Yanked from DataStack; the backend's in-memory rate-limit fallback handles the demo load. ElastiCache comes back with the VPC-connector + refresh-token-blocklist work in Phase 11.

### CORS_ORIGINS localhost rejected in non-local envs

Added a `model_validator(mode="after")` to `Settings`: in `dev`/`staging`/`prod`, a `CORS_ORIGINS` value containing `localhost` or `127.0.0.1` is rejected at startup. Catches the class of misconfiguration where someone forgets to update the CORS list before deploy. *(Round 2 then found this validator created its own regression — the CDK defaults still shipped `http://localhost:3000`, so the very next `cdk deploy` would have bricked the App Runner service. Covered in the round-2 entry.)*

### `_RESULT_PROJECTORS` duplication eliminated

The router had a `_RESULT_PROJECTORS` dict that ran a parallel pipeline to the service's renderers — same logic, twice, with one branch tested and the other not. Killed the dict; `ContentService.project_result()` is now the single source of truth. Two state-conflict 422s (`CONTENT_NOT_DELETED`, `RESTORE_WINDOW_EXPIRED`, `CONTENT_NOT_READY_FOR_IMAGE`) became 409s along the way — they're resource-state conflicts, not validation errors.

### Frontend hygiene: cache clear on logout + gen:api actually runs

`useLogoutMutation.onSettled` now calls `queryClient.clear()` so a user who logs out and another user logs in on the same browser don't see cached query results from the first session. The `pnpm gen:api` script was wired but never actually invoked anything; it now runs `openapi-typescript` against the documented `API_SPEC_URL`.

### What was rejected from the review

Three findings didn't survive verification: a "Sentry leaks Authorization headers" claim (Sentry SDK is configured with `send_default_pii=False`, which covers that), a "Zod ↔ Pydantic password drift" claim (schemas match exactly — the frontend Zod schema enforces the same 72-byte rule the backend now uses), and a "requestBodyCache leaks across users" claim that misread `WeakMap` semantics. Documented in the triage report so a future reviewer doesn't re-raise them.

---

## 2026-05-15 — Demo polish: seed script, account page, READMEs

Five feature slices shipped in 12 hours of local-first work. The final polish pass closes three small loose ends so the deployed demo lands on its feet:

### A demo user with real rows

`python -m app.scripts.seed` from [`backend/app/scripts/seed.py`](backend/app/scripts/seed.py) creates `demo@figurematch.dev` / `DemoPass123` plus one brand voice, three content pieces (blog / LinkedIn / email — using the brand voice), one image per piece, and one improvement. The script is idempotent: re-running checks for each row by a natural key (email for the user, name for the voice, topic for the pieces) and skips what already exists. Everything goes through the same services + repositories the live app uses, with `MockLLMProvider` + `MockImageProvider` forced in-script so it runs offline and zero-cost. The dashboard, generate-result, and improver pages all render real rows the first time the demo user signs in — no "empty state, please generate something to see the UI" moment.

### Account page replaces the settings stub

The protected-layout sidebar links to `/settings`. Shipping that link with a "real settings page lands later" placeholder felt wrong for the demo; the new page reads from `/auth/me` and shows email + full name + member-since. Nothing editable — full preferences are still deferred — but the route stops looking like work that wasn't done. Same minor refresh for `/usage` (explains the deferral with a pointer to where the cost data actually lives today: on each content_piece and improvement row, visible from the dashboard detail).

### Live URLs in the README §1

The README now lists the App Runner URL, the live `/docs` swagger, and the demo credentials at the top. Frontend URL is marked pending until the Amplify zip lands. The "what works today" answer fits in five lines instead of "clone and run locally."

### What didn't ship in this window

- Frontend zip upload to Amplify (one-click, but it's the user's hands)
- The six deploy-time fixes tracked in the slice plan — em-dash + NoDecode are already in the repo; migration env + Fargate SG land at deploy-prep time
- S3 image-storage adapter (the `IImageStorage` slot is reserved; the local-disk path runs in dev and currently in App Runner too, served by the FastAPI `/local-images` static mount)
- Streaming SSE on the improver and per-account rate limiting — both explicitly in the cut list

---

## 2026-05-15 — Slice 6: brand voice mini — CRUD plus prompt injection

Each generation now optionally pulls from a user-owned style preset. Slice 6 ships the smallest CRUD layer that earns the integration: `/brand-voices` list / create / detail / patch / delete, plus an optional `brand_voice_id` on every `POST /content/generate` that injects the voice's tone descriptors, banned phrases, audience hint, and sample copy into the user prompt. Persisted `user_prompt_snapshot` carries the full injected text so generations are reproducible against the exact prompt that produced them.

### Why the injection lives in the service, not the prompt module

Every per-type prompt module (`blog_post`, `linkedin_post`, `email`, `ad_copy`) accepts `brand_voice_block: str | None = None` already — that was a Slice 1 design decision so brand voices could land later without touching the four prompt modules. The new [`render_brand_voice_block`](backend/app/services/brand_voice_service.py) is a pure function that turns the persisted `BrandVoice` row into the block string. The content service looks up the voice (via the repository) and threads the block into `bundle.build_prompt(...)`. Two consequences:

- Adding a fifth content type later doesn't need to know about brand voices — the registry entry plugs in and the service injects automatically.
- Changing how the block renders (e.g., adding "Forbidden sentence structures") is a one-file change in the service, not a four-file change across prompt modules.

### PATCH semantics: present-keys-only, not null-clearing

`BrandVoiceUpdate` is all-optional. The router uses `body.model_fields_set` to extract only the keys the caller actually sent — `None` is treated as "unset", not "set to null". The shape matches what most clients actually want from a PATCH and avoids the "I accidentally sent `description: null` and lost my description" footgun. To clear a nullable string column, send an empty string; the schema lets that through.

### What was cut

Streaming for the generator with brand voice attached (still non-streaming, per brief allowance). A default-voice-per-user opinion (today the dropdown defaults to "No brand voice"). The "is this voice currently in use by N generations?" indicator on the delete button. All deferred — none of them block the demo.

---

## 2026-05-15 — Slice 5: improver — analyze, then rewrite

The brief asks for an explicit two-pass chain on `/improve` rather than the obvious one-shot "please improve this." Slice 5 implements exactly that: an analyze call returns a structured `{ issues, planned_changes }` list, then a rewrite call consumes those planned changes and returns the final improved text plus an explanation and a `changes_summary`. Both calls go through the same three-stage parse fallback as content generation, applied independently to each stage.

### Two prompts, one service, summed cost

[`improver.py`](backend/app/prompts/improver.py) ships two distinct prompt builders — `build_analyze` and `build_rewrite` — with separate JSON schemas. [`ImproverService.improve`](backend/app/services/improver_service.py) runs analyze first, harvests `planned_changes`, then runs rewrite with the plan baked into the user prompt. The persisted row sums tokens and cost from every call (up to four if both stages retry once each), so the dashboard cost rollup later in Phase 9 stays honest.

### Why force the model to commit to a plan first

Empirically, the rewriter writes cleaner copy when it's been told *what* to change before it picks up the pen. The naive single-pass "improve this" prompt produces text that's better than the original about 60% of the time and worse about 40% — usually because the model deletes the wrong nuance trying to hit a tone target. Forcing the plan first cuts the worse-than-original rate sharply because the rewriter has a checklist it can self-validate against. The cost is real: two LLM calls per improvement instead of one. The trade is intentional; the brief explicitly calls it out as the right shape.

### Goal-specific hints belong in the prompts, not the schema

Each `ImprovementGoal` value (`shorter`, `persuasive`, `formal`, `seo`, `audience_rewrite`) gets a short `_goal_hint` paragraph that's threaded into both the analyze and rewrite prompts. The `audience_rewrite` goal is the only one that requires extra input (`new_audience`); Pydantic's `model_validator` rejects the request at the schema boundary if it's missing, before any LLM call fires. Saves a call, sharpens the error message.

### Frontend: two-pane diff, not token-level

[`ImproveResult`](frontend/components/features/improve-result.tsx) renders original and improved side-by-side in scrollable `<pre>` blocks plus the explanation bullets and a `changes_summary` card (tone shift, length delta, key additions/removals). A real token-level diff library (`diff` from npm) would surface every word change but obscures the overall shape; for marketing copy review the two-pane is what people want. If a future demand for "show me literally which words moved" surfaces, swap in `diff` — the explanation/changes_summary contract doesn't change.

---

## 2026-05-15 — Slice 3: image generation, two providers, one pipeline

The dashboard had words but no pictures. Slice 3 fixes that: every content piece can now get an `is_current` image generated, regenerated with a different style, and reviewed against prior versions. Two upstream calls per image — an LLM call to *build the visual prompt* from the rendered content, then the image provider call to produce the bytes — feed one storage adapter that writes to local disk in dev and (soon) S3 in prod.

### Two stages, one transaction, one canonical "current"

The flow inside [`ImageService.generate_for_content`](backend/app/services/image_service.py):

1. Validate the requested style against the six in the brief; bail with `UNSUPPORTED_IMAGE_STYLE` early.
2. Fetch the content piece; reject `CONTENT_NOT_FOUND` (or `CONTENT_NOT_READY_FOR_IMAGE` if the content's parse_status was `failed`).
3. Call the LLM with the content's `rendered_text` (truncated to 4000 chars) + style; parse against `ImagePromptResult`. On parse failure, fall back to a topic-derived default rather than spend a retry call — the worst case is a less-tuned prompt, not a broken UX.
4. Fold the `negative_prompt` into the positive prompt as an "Avoid: ..." clause (since `gpt-image-1` doesn't accept a separate negative field), then call the image provider.
5. Upload bytes via the storage adapter, flip any previous `is_current=true` row to false, insert the new row as `is_current=true`. Single transaction; the partial unique index `ix_generated_images_current_per_piece` enforces "at most one current per piece" at the DB level.

The previous-versions strip on the frontend renders straight from `list_for_content`, which returns every row newest-first — including the now-superseded ones.

### Local-disk storage today, S3 swap pending deploy

[`image_storage.py`](backend/app/services/image_storage.py) defines an `IImageStorage` protocol with two implementations in mind: `LocalImageStorage` (this slice) writes UUID-named PNGs into `backend/local_images/` and returns the URL FastAPI's `/local-images/*` static mount serves them from; an `S3ImageStorage` (deferred to deploy batch) will swap to `boto3.put_object` + presigned URL with no caller changes. The factory `build_image_storage()` picks based on `IMAGES_CDN_BASE_URL`; today every environment is `localhost:8000/local-images` until the deploy batch reroutes it. The directory is gitignored.

### gpt-image-1 quirks worth knowing for next time

`gpt-image-1` returns `b64_json` by default, not a URL. The [provider already decodes it](backend/app/providers/image/openai_provider.py) into raw bytes; the storage adapter takes raw bytes. Quality maps directly: `low → $0.011`, `medium → $0.042`, `high → $0.167` per 1024×1024 image. `OPENAI_IMAGE_QUALITY=low` is the local default to keep the bill sane during iteration; the demo deploy will use `medium`.

### Frontend: one panel, two surfaces

[`ImagePanel`](frontend/components/features/image-panel.tsx) is one component used in two places: the post-generate success view (right after content lands), and the dashboard's detail dialog (any time later). Same query key, same mutation, same cache invalidation — invalidating `["content", "images", contentId]` after a regenerate is enough for the panel anywhere it's mounted to re-fetch.

---

## 2026-05-15 — Slice 4: the dashboard that makes Slices 1 and 2 feel real

Slice 1 generated a blog post. Slice 2 widened that to four content types. But the only way to view what you'd generated was to keep the success panel from the form open — once you navigated away, the row was effectively invisible. Slice 4 fixes that: a real dashboard list, scoped to the caller, with content-type filter, full-text search, pagination, a click-into-detail dialog, and a per-card delete with a 24-hour restore window.

### Why server-side preview, not client-side truncation

The list endpoint trims `rendered_text` to the first 200 chars + ellipsis before sending. The naive alternative — ship full `rendered_text`, truncate in CSS or JS — would have made the FTS hit and the visible preview come from different strings, which means a search match isn't necessarily visible in the card body the user sees. With server-side preview the relationship is exact: if `q` matched, the matched text is in the preview. That's a real UX win and the wire payload drops by an order of magnitude on long blog posts.

### FTS uses `plainto_tsquery`, not raw `to_tsquery`

The GIN index is already on `to_tsvector('english', rendered_text)` from the baseline migration. Querying it via `to_tsquery` requires the caller to know tsquery operator syntax — apostrophes, `&`/`|`, parens, all of which are common in free-form search input and would either error or do unexpected things. `plainto_tsquery` does the right normalization: strips operators, lowercases, stems. The Postgres planner still picks the GIN index because the expression matches the indexed form. See [`content_repository.list_for_user`](backend/app/repositories/content_repository.py).

### Restore is a 24-hour soft-undo, not a separate trash UI

`DELETE /content/:id` is a soft delete (sets `deleted_at`). `POST /content/:id/restore` flips it back if and only if the row's `deleted_at` is within 24 hours of `now()`. There's no separate "trash" page in the dashboard — restore is reachable only from the toast that fires immediately after delete, and only for that window. Once 24h pass, the row is dropped from the user's reach (kept in the table for cost-history / audit). The exact window is a const in the repository (`RESTORE_WINDOW`), tested at the integration level by aging `deleted_at` past it and asserting the structured `RESTORE_WINDOW_EXPIRED` error code.

### Two error codes the frontend speaks plain English for

`CONTENT_NOT_FOUND` (404) for an unknown id, `CONTENT_NOT_DELETED` and `RESTORE_WINDOW_EXPIRED` (422) for the two failure modes of restore. The frontend's [`FRIENDLY_MESSAGES`](frontend/lib/content/hooks.ts) maps each to a one-sentence toast so the user never sees `{ "error": { "code": ... } }`.

### One UI primitive added

[`components/ui/modal.tsx`](frontend/components/ui/modal.tsx) — a lightweight fixed-overlay modal with escape-to-close and backdrop-click-to-close. Not a Radix dialog because the slice didn't need focus trapping or nested triggers; the lock-file churn for a dependency that does one thing wasn't worth it. If the dashboard ever needs a wizard-style flow or richer keyboard semantics, swap to `@radix-ui/react-dialog` then.

---

## 2026-05-15 — Slice 2: three more content types behind one registry

Slice 1 shipped blog-post generation end-to-end. Slice 2 widens that to LinkedIn posts, marketing emails, and ad copy — same `POST /content/generate` route, same three-stage parse fallback, just three more prompts, three more Pydantic result models, three more renderers. The router's slice-1 content-type gate is gone; the form's three disabled tabs are now live.

### Why a registry, not a `match` statement

The naive widening adds an `if request.content_type == ...` block inside `ContentService.generate_blog_post` for each new type. After three of those it's already a mess, and Slice 6 (brand voices) will want to inject a prompt block into *every* type uniformly — switch statements at four call sites is a refactor waiting to happen. Instead, [`content_service.py`](backend/app/services/content_service.py) builds a `_REGISTRY: dict[ContentType, _ContentTypeBundle]` once at import. Each bundle pairs a prompt module's surface (`PROMPT_VERSION`, `build_prompt`, `JSON_SCHEMA`, `CORRECTIVE_RETRY_INSTRUCTION`) with its Pydantic `result_model` and its renderer. The public `generate(user, request)` looks up the bundle and runs the same fallback loop for every type. Adding a fifth content type is appending one registry entry plus a prompt/schema/renderer trio.

### Schemas already covered this, by design

[`backend/app/schemas/content.py`](backend/app/schemas/content.py)'s `GenerateRequest.content_type` was open to the full `ContentType` enum from day one — Slice 1's router was the only thing rejecting non-blog values. Slice 2 just removes that gate. The response side widens `GenerateResponse.result` from `BlogPostResult | None` to a `ContentResult` union over all four per-type models, and the router projects the stored JSONB back through the right model via a small `_RESULT_PROJECTORS` lookup. The frontend `api.d.ts` mirrors the same union — `openapi-typescript` doesn't model discriminated unions natively, so the consumer narrows on `content_type` if it needs to.

### Renderers are still pure, write-time, and per-type

[`render_linkedin_post`](backend/app/services/renderers/linkedin_post.py), [`render_email`](backend/app/services/renderers/email.py), and [`render_ad_copy`](backend/app/services/renderers/ad_copy.py) each map a typed result into the canonical text shape from §7.0.1 of the brief: hook/body/cta/hashtags for LinkedIn, subject/preview lines for email, and `## Short / ## Medium / ## Long` blocks for ad copy. The ad-copy renderer reorders variants into the canonical short → medium → long ladder regardless of input order, so providers that return them in a different sequence still produce identical `rendered_text`. The text feeds the same downstream paths as Slice 1: GIN full-text index, dashboard preview, copy-to-clipboard, exports.

### What this slice does NOT include

Streaming SSE on any of these (the brief explicitly allows non-streaming), client-side per-type result affordances (copy-hashtags-only, copy-just-the-headline, etc. — `react-markdown` over `rendered_text` covers all four for now), and the dashboard list that will make these new types feel real. Slice 4 picks up the dashboard next.

---

## 2026-05-15 — Slice 1: first vertical that actually generates content

The kickoff doc calls this milestone out as the *north star* — "a logged-in user generates a persisted blog post through the UI using the mock provider." Slice 1 is that, end-to-end: backend route, prompt module, three-stage parse fallback, renderer, persistence, typed API client extension, RHF form with content-type tabs, staged loading, markdown render, copy-to-clipboard, fallback-mode banner.

### What "three-stage parse fallback" actually buys us

The brief's §7.0 is non-negotiable: a user must never see an error mid-demo. In code that's [`content_service.py`](backend/app/services/content_service.py):

1. **Attempt 1.** Call the LLM with OpenAI's `response_format: json_schema, strict: true`. Parse the JSON, validate against `BlogPostResult`. On success → `result_parse_status = OK`.
2. **Attempt 2.** On any parse or validation failure, re-call *without* `json_schema` and with the previous raw output pasted back into the user prompt plus a corrective instruction. Asking the model under strict mode twice in a row tends to fail the same way — relaxing strict on the retry has been the empirically better path. On success → `result_parse_status = RETRIED`.
3. **Attempt 3.** If the corrective retry also fails, persist the raw model output verbatim as `rendered_text`, set `result = null`, `result_parse_status = FAILED`. The frontend renders the raw text inside a `<pre>` and shows a small "Generated in fallback mode" banner. The demo continues.

Token usage from both attempts is summed onto the persisted row so cost accounting stays honest even on retries. The mock provider always lands on attempt 1, so the canonical Slice 1 verification path costs nothing.

### The schema is wider than the slice

[`backend/app/schemas/content.py`](backend/app/schemas/content.py) defines `GenerateRequest.content_type` against the *full* `ContentType` enum, not just `BLOG_POST`. The router rejects non-blog values with 422 `UNSUPPORTED_CONTENT_TYPE` until Slice 2. Same on the frontend: [`generate-form.tsx`](frontend/components/features/generate-form.tsx) renders all four tabs from day one, with the three unsupported ones disabled and a "Coming in Slice 2" tooltip. Widening to LinkedIn / email / ad copy is a prompt-module + router-branch change, not a UI redesign.

### Why per-type renderers run at write time

`rendered_text` is the canonical text used by full-text search (the GIN index lives on it), the dashboard preview, copy-to-clipboard, and exports. Computing it at write time means readers never re-render — three reads of the same row produce three identical strings. [`render_blog_post`](backend/app/services/renderers/blog_post.py) is a pure function over the typed `BlogPostResult`; the test suite covers tag normalization, heading rendering, and word-count edge cases without spinning up Postgres.

### Rate limit is the closest in-memory analog to the brief

The brief asks for `20/hour` on `/content/generate`. The existing limiter is per-path-per-minute, so the route gets `20/minute` for now — same numeric budget, different window. The real `20/hour` sliding window is part of the Redis hardening pass (P11.3). I'd rather ship the wrong window than introduce Redis-on-the-critical-path two slices before the brief asks for it.

### What this slice does NOT include

LinkedIn / email / ad-copy content types, image generation, the dashboard list, the improver, brand voices, streaming SSE. Each lives in its own future slice per the kickoff document. Cutting them out kept this PR under the "end-to-end vertical in one session" budget.

---

## 2026-05-15 — Phase 2 in 12 PRs while away from the keyboard

Phase 2 — AWS infrastructure, frontend scaffolding, and Sentry — landed in twelve sequential PRs ([#120](https://github.com/Eslam93/FigureMatch/pull/120) through [#130](https://github.com/Eslam93/FigureMatch/pull/130) plus this docs PR) over a few hours while I was away. The constraint was deliberate: **code only, no `cdk deploy`**. Every PR's gate is `cdk synth --all` on the infra side or `pnpm build` on the frontend, never an actual cloud touch. That keeps the AWS bill at zero until I'm back to babysit the first deployment.

### What this entry covers

- The five CDK stacks (Network, Data, Compute, Edge, Observability) and why they look the way they do
- The frontend's three-PR split (scaffold → auth pages → protected layout)
- The Sentry "wire it but leave it silent" posture
- The handful of trade-offs that didn't make the brief but had to be made anyway

### CDK app shape, and one decision the brief didn't anticipate

The five stacks compose linearly: NetworkStack exports the VPC and security groups → DataStack consumes them, exports the bucket and secret ARNs → ComputeStack consumes those plus VPC, exports App Runner service ARN → EdgeStack runs in parallel (Amplify only) → ObservabilityStack runs in parallel (log groups only). Single `dev` environment for now; the `EnvConfig` shape in [`infra/lib/config.ts`](infra/lib/config.ts) is ready for `staging` and `prod` to slot in as one-line clones.

The **trade-off the brief didn't anticipate**: `EdgeStack` was supposed to include CloudFront for the images S3 bucket, with Origin Access Control auto-attaching a bucket policy. The naive implementation creates a circular dependency:

> `S3BucketOrigin.withOriginAccessControl(bucket)` writes a bucket policy to the *bucket's* stack (DataStack). That policy references the CloudFront distribution's ARN (EdgeStack). Meanwhile the CloudFront origin references the bucket (DataStack). CDK refuses to synth two stacks that need each other.

Three ways out, none free:
1. Move the bucket into a dedicated stack alongside the distribution
2. Pre-create the OAC in DataStack with a wildcard-distribution bucket policy
3. Use the legacy Origin Access Identity (OAI) pattern

I picked **none of the above** for Phase 2 and shipped EdgeStack with Amplify only. CloudFront for images isn't load-bearing until Phase 5 (image generation) — until then, the images bucket already blocks all public access, and any S3 reads happen via App Runner's IAM role. Adding the CDN tier later is straightforward once we pick a fix; documenting the cycle in [edge-stack.ts](infra/lib/edge-stack.ts)'s header docstring means the next reader doesn't re-discover it.

### The deploy workflow that doesn't deploy

[`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) is `workflow_dispatch`-only by design. Flipping it to `on: push: main` would auto-deploy every PR merge, but the deploy can't actually succeed until:

1. Someone runs `aws configure` against a real account
2. CDK bootstrap happens (`npx cdk bootstrap aws://ACCOUNT/us-east-1`)
3. A placeholder backend image gets pushed to ECR (App Runner won't start without one)
4. The OpenAI API key gets pasted into Secrets Manager
5. The IP-identity preflight at [`infra/DEPLOY.md`](infra/DEPLOY.md) step 8 passes — this is the P1.10 follow-up that verifies rate-limit identity isn't broken by App Runner's load balancer

Step 5 is the one that scared me into the manual-trigger posture. If `scope["client"]` in App Runner is the LB peer rather than the real client IP, every user shares one rate-limit bucket — first attempt of the day 429's everyone. The runbook documents the exact curl loop to verify it before going public.

### Frontend in three PRs, in increasing trust

[`P2.9a`](https://github.com/Eslam93/FigureMatch/pull/127) is the Next.js 15 + Tailwind + shadcn/ui scaffold plus the auth store and API client plumbing — no real product pages, just a landing that links to /login and /register placeholders. [`P2.9b`](https://github.com/Eslam93/FigureMatch/pull/128) adds those routes for real, with zod validation, react-hook-form, and the 401 interceptor that handles refresh-and-retry transparently. [`P2.9c`](https://github.com/Eslam93/FigureMatch/pull/129) lifts the dashboard placeholder into a real protected shell with sidebar nav, top-right user menu, and a `/me`-driven dashboard page.

The 401 interceptor is the one piece worth pulling out:

```typescript
// frontend/lib/api.ts (excerpted)
async onResponse({ request, response }) {
  if (response.status !== 401 || isAuthEndpoint(url)) return response;
  if (!inflightRefresh) {
    inflightRefresh = refreshAccessToken().finally(() => {
      inflightRefresh = null;
    });
  }
  const refreshed = await inflightRefresh;
  if (!refreshed) return response;
  // ... retry the original request with the new Bearer token
}
```

Single-flight refresh: if three queries 401 simultaneously, they all wait on one `/auth/refresh` promise rather than firing three. That detail matters because P1.6 treats two valid refresh attempts on the same token as compromise — without the dedup, the second concurrent retry would have triggered the family-revocation path. The interceptor explicitly skips `/auth/refresh` / `/auth/login` / `/auth/register` / `/auth/logout` because 401s from those endpoints mean "credentials wrong," not "session expired."

### typedRoutes, the small footgun

Next.js 15's `experimental.typedRoutes: true` is the kind of feature that looks like a clean win until you try to ship in increments. It type-checks every `<Link href="/foo">` against the actual `app/` file tree. Beautiful for catching typos; brutal for "I want to show a placeholder link to a route that exists in tomorrow's PR." Three rounds of dance with this:

- P2.9a's landing page links to `/login` and `/register`. typedRoutes off, with a comment.
- P2.9b adds those routes. typedRoutes on. The auth hooks push to `/dashboard` after success, so a minimal `/dashboard` stub gets added in the same PR.
- P2.9c moves the stub into `app/(protected)/dashboard/page.tsx` (route-group reorg) and adds five more stubs for the sidebar destinations (generate, improve, brand-voices, usage, settings) so typedRoutes doesn't reject the sidebar's links. Each stub is a four-line "Coming in Phase X" placeholder.

The trade-off is clear in retrospect: typedRoutes pays for itself once the route graph is stable but creates churn during scaffolding. Worth it long-term.

### Sentry wired silent

Both `sentry-sdk[fastapi]` (backend) and `@sentry/nextjs` (frontend) are installed and initialized. Both are gated behind `if (dsn)` checks. With `SENTRY_DSN=""` and `NEXT_PUBLIC_SENTRY_DSN=""` (the defaults in [`.env.example`](.env.example)), neither does anything. Flip on later by setting the env var.

This is the "wire the code path, leave the DSN empty" posture — the brief calls it out for the same reason: the app is going to be publicly live ~15+ days before P11 hardening lands, and flying blind on errors for that long is unacceptable. Even an unwired Sentry has the integration code right there; turning it on is one env var.

Source-map upload, session replay, and PII scrubbing polish are deferred to P11.5.

### Issue hygiene — a thing the project was bleeding

Before starting Phase 2, twelve issues were OPEN on GitHub despite being merged: Phase 0's P-1.1 + P0.1 through P0.7, plus Phase 1's P1.6 through P1.9. Closed those with `gh issue close` and a "merged in #XYZ" comment. From Phase 2 onward, every PR auto-closes its issue via `Closes #N` in the PR body. The board now reflects reality.

The `.private/PHASES.md` got one substantive update: P2.7's preflight bullet expanded to a full paragraph with the exact curl loop and the failure signature. If the rate-limit identity is broken behind App Runner's LB, that bullet is the only thing standing between "ship the public URL" and "every user shares one rate-limit bucket."

### Where we are

| Phase | Status |
|---|---|
| 0 — Bootstrap | ✅ |
| 1 — Backend foundations (1.1 through 1.9 + two hardening rounds) | ✅ |
| 1.10 — Pre-Phase-2 review-driven hardening (JWT validator, mock-mode gate, CI Postgres) | ✅ |
| 1.11 — Phase-2-adjacent cleanups (middleware order, finish_reason strictness, etc.) | ✅ |
| **2 — CDK + frontend + Sentry (this entry)** | ✅ |
| 3 — Core content generation | 📋 next |

CI is green across `backend-ci`, `frontend-ci`, and `infra-ci`. The first three workflows run on every PR. `deploy.yml` waits for me to flip its trigger after the first manual deploy.

### What's next

Phase 3 is where the product actually starts producing content. The four content-type prompts (blog, LinkedIn, ad copy, email), the three-stage JSON fallback, the prompt module infrastructure, the `POST /content/generate` endpoint, and the staged-loading UI on the frontend. P3.1 through P3.10 in the brief; I expect it to be the most fun phase yet because the work is finally about the thing the app does, not the thing it stands on.

Two things to do before that:

1. **Actually deploy.** The whole point of Phase 2's "code only" constraint is that the deploy is the gate to Phase 3 going live. Run [`DEPLOY.md`](infra/DEPLOY.md) end to end, verify the rate-limit preflight passes, flip `deploy.yml` to push-on-main, paste the URLs into the README's `## 1. Live demo` section.
2. **The IP-identity preflight.** If it fails, the Phase 3 work happens behind a known-broken rate-limit until I add `TRUST_PROXY_XFF` parsing. Better to know on day one of the deployed life than day fifteen.

---

## 2026-05-14 — Auth, then two passes of review-driven hardening

Three more PRs landed in close succession: auth foundation, then two rounds of fixes against an external code review. ([#109](https://github.com/Eslam93/FigureMatch/pull/109), [#110](https://github.com/Eslam93/FigureMatch/pull/110), [#111](https://github.com/Eslam93/FigureMatch/pull/111).) The interesting story isn't the auth code itself — register/login/me with bcrypt + JWT is well-trodden ground. The interesting story is what the review caught.

### Auth landed clean, with one footgun we didn't notice

PR [#109](https://github.com/Eslam93/FigureMatch/pull/109) shipped `POST /auth/register`, `POST /auth/login`, `GET /auth/me`. bcrypt cost 12, JWT HS256, refresh-token cookie (httpOnly, SameSite=Lax, Secure-when-prod). Same `INVALID_CREDENTIALS` error for unknown email vs. wrong password — anti-enumeration by design.

Or so the comment claimed. The actual code:

```python
if user is None or not verify_password(password, user.password_hash):
    raise UnauthorizedError(...)
```

Python's `or` short-circuits. If `user is None`, `verify_password` doesn't run, no bcrypt cost paid. So `unknown_email` returns in ~5ms and `wrong_password` in ~250ms. A registered email was distinguishable by latency alone, even though both paths returned the same error body. The same-error-message comment was true and the same-cost claim was false — a common shape of bug.

### First review round (PR [#110](https://github.com/Eslam93/FigureMatch/pull/110))

Eight items accepted, six pushed back on. The fixes that mattered:

- **Timing leak** — precomputed dummy bcrypt hash, always call `verify_password`. Now both paths pay the same ~250ms.
- **JWT secret validation** — the previous check matched a handful of placeholder prefixes; `"secret"` passed. Added a denylist + length floor + low-variety guard.
- **bcrypt 72-byte truncation** — `validate_password_strength` now rejects passwords whose UTF-8 encoding exceeds 72 bytes. Pydantic `max_length` is char-level; 70 emoji chars = ~280 bytes silently truncated before this fix.
- **X-Forwarded-For unvalidated** — junk in the header was reaching the Postgres `INET` column and crashing the request as a 500. Now parsed via `ipaddress` first, falls through on garbage.
- **Middleware order documented backwards** — Starlette stacks the last-added middleware as the outermost. My comments said the opposite. Reordered so CORS is genuinely outermost (preflights short-circuit), and rewrote `RequestIDMiddleware` as **pure-ASGI** (no `BaseHTTPMiddleware` child-task spawning, which had been breaking contextvar visibility for downstream readers).

Pushed back on: the broader Bedrock-instead-of-OpenAI argument (scope), anonymize-instead-of-hard-delete users (deliberately not in scope), partial-where index optimizations (premature at MVP volume), register-endpoint email enumeration (UX trade-off; mitigation is rate-limit in a later phase, not silent success).

### Second review round (PR [#111](https://github.com/Eslam93/FigureMatch/pull/111))

Reviewer caught that the first-round JWT secret validator still accepted any 32+ char string with >2-char variety. `"the-quick-brown-fox-jumps-over-the-lazy-dog"` would pass — and would even decode through base64url to ~33 bytes, slipping through any naive length-of-decoded-bytes check.

Tightened to a strict format gate:

- **hex** with ≥64 chars (decodes to ≥32 bytes), OR
- **base64 / base64url** that decodes to ≥32 bytes AND has Shannon entropy ≥ 5 bits/byte on the decoded payload.

Shannon entropy is the catch. Random bytes hit ~7.5 bits/byte; English text base64-decoded hits ~4. The fox phrase fails the entropy gate even though it passes format + length. The implementation caught itself during testing — the test I wrote expected the phrase to be rejected as "not a strong format", and the actual rejection was as "low Shannon entropy". The deeper guard fired correctly.

Other second-round fixes:

- **bcrypt 72-byte cap moved to login too** — registration already rejected long passwords, but login passed them straight to bcrypt, which silently truncates. A user with an exactly-72-byte password could authenticate with that password + any trailing bytes. Live-verified the fix: register at 72 bytes succeeds, login with `password + "trailing-garbage"` now returns 401, login with the real password still works.
- **Cookie `Secure` consistent with env protection** — was set only for staging/prod; now set whenever `env != local`. A shared cloud `dev` env was previously getting non-Secure cookies despite being treated as protected for secrets.
- **Service-level timing regression test** — the first round's smoke test exercised `verify_password` directly. A revert of the `auth_service` short-circuit would still have passed it. Added a unit test that mocks the repository to return `None`, then asserts `verify_password` was called with the real bcrypt dummy hash. Future "cleanup" that reintroduces `if user is None: raise` fails this test.
- **`_client_ip` docstring** — added a `WARNING` block stating this value is for audit storage only. Client-supplied XFF is honored when it's a valid IP (fine for audit), unsafe as a rate-limit identity. Future rate-limit work has to use `request.client.host` plus a trusted-proxy allowlist.

### What review feedback looks like when you take it seriously

The reviewer wasn't picking nits. They were saying: *you wrote a comment that claims X, and the code does Y; either the comment is wrong or the code is.* In two of the three rounds, the code was wrong. The "anti-enumeration" comment was the most painful — it was true in spirit (same error body), false in operational reality (different latency). Reviewer's instinct: don't trust same-model self-review for security-sensitive claims.

Pushing back on the wrong things would have wasted the review. Pushing back on the right things — Bedrock-vs-OpenAI for scope, anonymize-users for scope creep, partial-index optimization without query patterns to optimize against — kept the work focused. The skill is knowing which is which.

### Where we are

73 tests pass, coverage 90.53%, lint/format/mypy strict all clean. Auth is end-to-end: register, login, `/me`, with timing parity, strict JWT secret format, bcrypt 72-byte caps on both sides, Secure cookies in non-local envs, and audit-safe IP capture. Refresh-token rotation + `/logout` is the next chunk — atomic conditional `UPDATE` for single-use semantics, plus reuse detection (a revoked token presented again means session compromise; revoke all of the user's tokens).

---

## 2026-05-14 — Backend foundation: skeleton, DB, schema, migration

Four PRs landed in one stretch — the boring-but-load-bearing layer the rest of the app sits on. ([#104](https://github.com/Eslam93/FigureMatch/pull/104), [#105](https://github.com/Eslam93/FigureMatch/pull/105), [#106](https://github.com/Eslam93/FigureMatch/pull/106), [#107](https://github.com/Eslam93/FigureMatch/pull/107).) The shape of each was determined more by infra correctness than by feature design — small things that ruin a week if you get them wrong on Day 5.

### FastAPI skeleton: middleware order matters

Starlette stacks middleware in reverse-add order. So if you write `app.add_middleware(CORS); app.add_middleware(AccessLog); app.add_middleware(RequestID)`, the request flows `Request → CORS → AccessLog → RequestID → handler`. We want CORS first (preflights short-circuit) and request-ID innermost (bound _before_ any handler runs, captured by access-log on the way out). That dictates the add order — and a comment in the source so the next reader doesn't reverse it on a "cleanup."

### The error envelope is a contract, not a convenience

Every failure path now produces the same shape:

```json
{
  "error":  { "code": "MACHINE_READABLE", "message": "human", "details": {...} },
  "meta":   { "request_id": "uuid" }
}
```

This means clients have exactly one shape to handle. `AppException` is the base, with subclasses for `NotFound`, `Unauthorized`, `Forbidden`, `Conflict`, `RateLimit`, `Provider`. Four handlers cover the universe: app exceptions, Starlette HTTP exceptions, Pydantic validation errors, and a catch-all for anything that escapes. The `request_id` flows through every envelope on handled paths (everything except bare uncaught exceptions, where FastAPI's per-route exception machinery runs the handler in a context our middleware can't yet reach — logs still carry the id; envelope on those paths may not. Tracked as a future hardening pass).

### Async Alembic is a copy-paste recipe — but mostly

The default `alembic init` template assumes sync engines. The async edition lives in the SQLAlchemy 2.0 docs — `run_async_migrations` opens an `AsyncEngine`, calls `connection.run_sync(do_run_migrations)` to hand the synchronous Alembic core a real connection. We also set `compare_type=True` + `compare_server_default=True` so autogenerate notices type drift (otherwise a `String(120) -> String(200)` change is invisible).

One non-obvious bit: importing `app.db` from `alembic/env.py` is what registers every model on `Base.metadata`. Without that side-effect import, autogenerate compares the live DB against an _empty_ metadata and thinks every table needs to be dropped. The `# noqa: F401` keeps lint quiet about the "unused" import.

### Two things `alembic --autogenerate` cannot do

1. **`CREATE EXTENSION citext`** — Postgres extension creation isn't a `Table` op. Has to be hand-added with `op.execute("CREATE EXTENSION IF NOT EXISTS citext")` at the top of `upgrade()`, before any `CITEXT` column is referenced.
2. **GIN expression indexes for full-text search** — `to_tsvector('english', rendered_text)` isn't a column reference; it's a SQL expression.

We added _both_ — and learned a trap on the GIN index. Initial approach used `op.execute("CREATE INDEX ... USING GIN ...")` and was satisfied. But `alembic check` then flagged the index as "removed" every time it ran, because the model didn't declare it. Fix: declare the expression index on `ContentPiece.__table_args__` using `Index(name, text("to_tsvector(...)"), postgresql_using="gin")`. Now the model and the live DB agree, and `alembic check` stays clean.

### Production-grade signaling: the small details

- **Refresh tokens** are stored as SHA-256 hashes, never as plaintext. Single-use rotation lands in P1.6 via a conditional `UPDATE ... WHERE revoked_at IS NULL` so concurrent reuse cannot mint two new pairs.
- **`metadata` is reserved on the SQLAlchemy `Base`**, so `UsageEvent` aliases the column attribute to `meta` while keeping the Postgres column name `metadata` — caught only by trying to declare it the obvious way.
- **`is_current` on `generated_images`** is enforced by a partial UNIQUE index — `(content_piece_id) WHERE is_current IS TRUE`. At most one current image per content piece, guaranteed at the DB layer, no app-side coordination needed.
- **The `users` table is intentionally not soft-deletable.** Soft delete + unique email = email-reuse-after-soft-delete collision. The brief calls this out; we honored it.

### What's next

Phase 1 has five tasks left: register/login (P1.5), refresh + logout + rotation (P1.6), provider abstractions with OpenAI primary + Mock fully implemented (P1.7a + P1.7b), security headers + auth rate limit (P1.9), and the test-fixture + coverage-gate consolidation pass (P1.8). The DB and the `User` / `RefreshToken` models are now ready — auth is the next thing that needs them.

---

## 2026-05-14 — Bootstrap day

### Pre-flight: choosing the AI provider

The original stack plan called for AWS Bedrock — Claude Sonnet 4.5 for text, Amazon Nova Canvas for image — all running inside AWS. The smoke calls before any code was written changed that.

Two findings stopped the Bedrock path:

1. **Claude Sonnet 4.5 on Bedrock requires submitting an "Anthropic use case details" form per AWS account.** Without it, every `bedrock-runtime:InvokeModel` call returns `ResourceNotFoundException`. The error message says "try again in 15 minutes," but the form review can take longer. For a project that wants to start building immediately, that's an unbounded blocker.
2. **Nova Canvas is `LEGACY` in `us-east-1` with EOL 2026-09-30.** It still works today, but writing the architecture around a model with a known end-of-life four months out felt wrong.

We considered Anthropic direct API as the alternative — same Claude family, no Bedrock wrapper. But Anthropic doesn't do image generation, so image still needed a separate provider (Replicate, fal.ai, or OpenAI). At that point the cleanest answer was to use OpenAI for both: one prepaid key covers text + image, no AWS-side enablement gates, and the underlying app architecture (provider abstractions, IAM role, AWS hosting) doesn't change.

Smoke tests confirmed:
- **Text:** a chat completion against `gpt-5.4-mini-2026-03-17` returns 200, tokens accounted, billing active.
- **Image:** `gpt-image-1` returns a 1.1 MB PNG at 1024×1024 `low` quality, ~$0.011 spent.

The Bedrock path stays alive as a documented alternative — `ILLMProvider` and `IImageProvider` are designed so swapping providers is a one-class change. If a future requirement makes Bedrock the right call again, no app code outside `app/providers/` is affected.

### Model-name humility

When the conversation suggested `gpt-5.4-mini` for text, we initially didn't recognize it — our knowledge of the OpenAI lineup was a few months behind. The right move was to list `/v1/models` against the live key and look at what's actually available rather than guess. `gpt-5.4-mini-2026-03-17` is real, current, and a strong fit. We pinned the dated variant for reproducibility — when OpenAI ships `gpt-5.4-mini-2026-XX-XX` next, our app won't silently re-route to it.

Lesson: when an external API surface is involved, _list, don't recall._

### Provider abstractions — the plan (not yet in code)

When the AI provider layer lands (next phase), `ILLMProvider` and `IImageProvider` will each have three implementations:

1. **OpenAI** — primary, real implementation.
2. **Mock** — fully built; returns canned valid JSON per content type (text) and a deterministic placeholder PNG (image). The point is to be able to run the full app end-to-end with zero API keys — useful for CI, useful for anyone who wants to see how the UI flows without spending a cent.
3. **Bedrock** — stubbed (`NotImplementedError`). Selectable via `AI_PROVIDER_MODE=bedrock` but the actual implementation only lands when there's a real reason to switch.

We rejected the `AnthropicDirectProvider` we'd originally considered. Keeping a half-built stub would advertise a fallback mode that doesn't actually work — worst of both worlds. If we want it later, we'll build it then.

_(As of this entry, `app/providers/` doesn't exist yet. The design above is what the next provider PR will implement; this paragraph is the spec, not a status report.)_

### Phase 0: the boring but load-bearing layer

Phase 0 was the unglamorous stuff: repo scaffold, Docker Compose with healthchecks, CI skeletons, `.env.example`, top-level docs, LICENSE. The principle behind making this a discrete phase: if the local-dev story doesn't work on day one, every later phase pays the tax.

Verified the bootstrap end-to-end — `docker-compose up` brings Postgres + Redis + service stubs to healthy in under 30 seconds, no warnings in logs beyond Redis's standard "no config file" notice.

The CI skeletons are intentionally pass-through today: each workflow checks whether `pyproject.toml` / `package.json` exists and runs the real pipeline only if so. That way the pipeline activates automatically the moment application code arrives — no one has to remember to wire it up.

### Going public

The repo is at https://github.com/Eslam93/FigureMatch. Before pushing, a five-check secret audit:

1. `.env` is not tracked
2. `OpenAIKey.txt` never appeared in any commit
3. No `sk-proj-*` prefix in any tracked file
4. No `sk-proj-*` anywhere in git history (all branches, all reflogs)
5. No AWS access-key patterns in tracked files

All clean. Then the push, then branch protection: `main` requires PRs, linear history, no force-push, no deletion. Admin can bypass for emergencies (it's a solo project; required reviews would block self-merge).

### Externalizing the planning docs

The original brief, the phased task breakdown, and the GitHub-board bootstrap script were valuable as development scaffolding but didn't belong in a public-facing repo. They moved into a local-only `.private/` directory, gitignored. The README and `ARCHITECTURE.md` now stand on their own — anyone reading them gets the product, the stack, the trade-offs, and how to run it locally. Anyone curious about _how_ decisions were made reads this file.

### What's next

The next chunk of work is the backend foundations: FastAPI app skeleton with structured logging, async SQLAlchemy 2.0 + the full database schema, Alembic baseline migration, custom JWT auth with refresh-cookie rotation, the provider abstractions sketched above. A few footguns to watch for:

- **Alembic + async SQLAlchemy 2.0** — `env.py` needs to be wired carefully; the common copy-paste templates assume sync engines.
- **`MockLLMProvider` JSON shapes** — each content type's canned response needs to match the Pydantic schema we haven't written yet. Sequencing the schema before the mock keeps this honest.
- **CORS + httpOnly refresh cookie** between Amplify and App Runner — fiddly enough that we explicitly want to surface it on day one of the cloud deploy, not on day three when the frontend goes up. That's why the cloud deploy will wire real auth (not mocked) end-to-end the moment it lands.
