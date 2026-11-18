# 0013. Cut what only pretended to work

- **Status:** Accepted
- **Decided:** 2026-11-18
- **Written:** 2026-11-18

## Context

Four things in the tree looked like working parts and were not. Each made the repository
claim more than it could do, and each had to be explained away in the documents:

- **The Bedrock providers.** `BedrockClaudeProvider` and `BedrockNovaCanvasProvider`
  raised on construction and had no implementation. `AI_PROVIDER_MODE=bedrock` was
  refused at boot outside `local`; in `local` the backend booted and failed at the first
  model call.
- **The deploy workflow.** `deploy.yml` ran once, on 15 May 2026, and failed: its OIDC
  role was never configured. Every deploy was done by hand.
- **The Redis switches.** No Redis cluster has existed since May, and the backend has no
  Redis code. Still, App Runner was given `USE_REDIS=false`, a setting the backend does
  not read, and the network stack defined a Redis security group nothing used.
- **The usage model.** The `usage_events` table and its model were created in the
  baseline migration for a usage page that was never built. Nothing wrote to the table or
  read from it.

## Decision

All four are removed:

- The two Bedrock classes, their test, and the `bedrock` value of `AI_PROVIDER_MODE`.
  Any value other than `openai` or `mock` now stops the backend at boot, in every
  environment.
- `.github/workflows/deploy.yml`, and the runbook steps that set it up.
- `USE_REDIS` in the compute stack and the Redis security group in the network stack,
  with its export.
- The `UsageEvent` model and its enum. A migration, `927951a9d585`, drops the
  `usage_events` table and its `usage_event_type` type; its downgrade recreates both, empty.

The studio itself stays as it is.

## Alternatives

Keeping them, documented as stubs, is what the repository did until now. It required
every document to carry a caveat, and a reader skimming the tree still saw a provider
choice, a deploy pipeline and a cache that did not exist.

## Consequences

- Two tests that only checked the stubs raised were deleted with them; tests of the
  factory, of startup validation, of the API schema and of the mock-mode banner changed
  from three provider modes to two. The startup test is stricter than before: it now
  also checks that `bedrock` is refused in `local`.
- The database's `image_provider` type still has a `nova_canvas` value, and the Python
  enum keeps it to match. Removing a value from a Postgres enum means rebuilding the
  type, which is not worth it for a value nothing writes.
- Backend CI now runs `alembic check`, so models and migrations cannot drift apart
  unnoticed.
- The snapshots of two CDK stacks changed. The difference is only the removed security
  group, its export and the `USE_REDIS` variable.
- Restoring any of these means writing it for real.
