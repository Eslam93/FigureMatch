# Infrastructure (AWS CDK, TypeScript)

The CDK app that described the studio's AWS deployment in May 2026: five stacks for one
environment, `dev`. It was deployed by hand from [`DEPLOY.md`](./DEPLOY.md) on 15 May
2026 and taken down in June 2026. Nothing is deployed from it today, and it has not been
deployed since.

CI still builds it, tests it and synthesises it on every change, so it stays a valid CDK
app. It is kept as a record of that deployment, not as a ready path to a new one.

## Stacks

| Stack | What it defines |
|---|---|
| `figurematch-dev-network` | A VPC with public subnets and no NAT gateway, and the database's security group |
| `figurematch-dev-data` | RDS Postgres (`db.t4g.micro`, public endpoint, TLS required), an S3 bucket nothing writes to, and Secrets Manager entries |
| `figurematch-dev-compute` | An ECR repository, the App Runner service with autoscaling from 1 to 3 instances, and a Fargate task definition for migrations |
| `figurematch-dev-edge` | An Amplify app for the static frontend, with no Git connection |
| `figurematch-dev-observability` | Nothing: a placeholder for alarms that were never written |

There is no Redis, no CloudFront distribution and no `prod` environment. A Redis security
group is still defined in the network stack, although no cluster exists.

## Commands

```bash
npm ci
npm run build    # tsc
npm test         # Jest, with a snapshot of each stack's template
npx cdk synth --all -c env=dev \
  -c cors_origins=https://ci.example.com \
  -c images_cdn_base_url=https://ci.example.com/local-images
```

`synth` needs `cors_origins` and `images_cdn_base_url` in the context; CI passes
placeholders. It needs no AWS account.

## Before deploying anything

Read the status note at the top of [`DEPLOY.md`](./DEPLOY.md). The runbook relies on a
security group that was created by hand and that no stack defines, and several of its
commands leave out context that synth now requires.
