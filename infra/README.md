# FigureMatch Infrastructure (AWS CDK, TypeScript)

This directory holds the AWS CDK app that defines every cloud resource FigureMatch uses: the VPC, RDS Postgres, ElastiCache Redis (provisioned but not yet used — see [DEVLOG.md](../DEVLOG.md)), App Runner backend service, ECR repository, Amplify-hosted frontend, and CloudWatch alarm scaffolding (CloudFront-for-images is deferred to Phase 5; see [P2.5 PR](https://github.com/Eslam93/FigureMatch/pull/124) for the circular-dependency reasoning).

## Status

| Stack | PR | Status |
|---|---|---|
| `figurematch-dev-network` | P2.2 | ✅ shipped |
| `figurematch-dev-data` | P2.3 | ✅ shipped |
| `figurematch-dev-compute` | P2.4 | ✅ shipped |
| `figurematch-dev-edge` | P2.5 | ✅ shipped (Amplify only — CloudFront deferred to Phase 5) |
| `figurematch-dev-observability` | P2.6 | ✅ shipped (placeholder; CloudWatch alarm lands in P11.6) |

All five stacks `cdk synth --all -c env=dev` cleanly on every PR via `.github/workflows/infra-ci.yml`. Actual `cdk deploy` is a manual step — see [`DEPLOY.md`](./DEPLOY.md).

## Layout

```
infra/
├── bin/
│   └── figurematch.ts              # CDK app entry; reads --context env=dev
├── lib/
│   ├── config.ts                # per-env config loader
│   ├── network-stack.ts         # → P2.2
│   ├── data-stack.ts            # → P2.3
│   ├── compute-stack.ts         # → P2.4
│   ├── edge-stack.ts            # → P2.5
│   └── observability-stack.ts   # → P2.6
├── test/
│   ├── config.test.ts           # current
│   ├── network-stack.test.ts    # → P2.2
│   └── ...
├── cdk.json
├── package.json
├── tsconfig.json
├── jest.config.js
└── README.md
```

## Local commands

```bash
# Install deps
npm ci

# Build TS → JS (CDK's ts-node also handles this on-the-fly)
npm run build

# Run unit + snapshot tests
npm test

# Synthesize CloudFormation templates (no AWS account needed)
npm run synth          # cdk synth --all -c env=dev
npm run synth:diff     # cdk diff --all -c env=dev (requires deployed stacks)
```

## Deploy

See `DEPLOY.md` (added in P2.7) for the manual runbook. Short version:

```bash
aws configure                                # admin creds for target account
npx cdk bootstrap aws://ACCOUNT/us-east-1    # one-time per account/region
npx cdk deploy --all -c env=dev
```

## Environments

Only `dev` is wired up in Phase 2. The `EnvConfig` shape in `lib/config.ts` already accommodates `staging` and `prod`; adding those is a single-PR follow-up (copy the dev entry, tighten instance sizes + retention + dev IP allowlist).

Switch environments at deploy time:

```bash
npx cdk deploy --all -c env=dev
# Later, once prod is wired:
npx cdk deploy --all -c env=prod
```

Stack names are namespaced by env: `figurematch-dev-network`, `figurematch-prod-network`, etc. — multiple envs can coexist in one AWS account.

## CI

`.github/workflows/infra-ci.yml` runs on every PR that touches `infra/**`:

1. `npm ci`
2. `npm test` (jest snapshot + unit tests)
3. `npx cdk synth --all -c env=dev`

No AWS credentials are needed — `cdk synth` is purely local code generation. The real `cdk deploy` requires the user's AWS credentials and happens manually via `DEPLOY.md`.

## References

- Architecture rationale: [`../ARCHITECTURE.md`](../ARCHITECTURE.md)
- Phase 2 task spec: `../.private/PHASES.md` §P2.1–P2.10 (gitignored)
- Brief §11 (Infrastructure): `../.private/PROJECT_BRIEF.md` (gitignored)
