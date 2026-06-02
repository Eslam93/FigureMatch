# Deploying MagnaCMS to AWS — manual runbook

This document walks through the first `cdk deploy` and the post-deploy bootstrap steps. After that's done once, `deploy.yml` handles every subsequent push to `main`.

## Prerequisites

- AWS account with admin credentials (`aws configure` against the target account)
- Node 20+, Docker, AWS CDK CLI (`npm i -g aws-cdk@^2.180`)
- A funded OpenAI API key (sk-proj-…)
- Optional: a registered domain if you want `app.<your-domain>` / `api.<your-domain>` URLs instead of the AWS default `*.amplifyapp.com` / `*.awsapprunner.com`

## One-time setup

### 1. CDK bootstrap

```bash
cd infra
npm ci
aws configure  # if not already
npx cdk bootstrap aws://<ACCOUNT_ID>/us-east-1
```

This provisions the CDK toolkit stack (S3 bucket for assets, IAM roles) — required once per AWS account + region combination.

### 2. Deploy Network + Data stacks

Data must exist before the OpenAI secret can be populated, and the OpenAI secret must hold a real key before App Runner boots — the backend's config validator rejects the placeholder value in non-`local` environments. So Compute is split out into step 4.

> **Required CDK context for any non-local deploy:** `cors_origins` and `images_cdn_base_url`. The backend's config validator rejects localhost values in non-local envs and the LocalImageStorage adapter returns broken URLs when the base is empty — `bin/magnacms.ts` will fail synth if either is absent unless `-c allow_synthetic_endpoints=true` is set (intended for the first bootstrap before the Amplify URL is known). For the first-bootstrap path you can pass an Amplify-shaped placeholder; once the real URL is known, redeploy with the real values:
>
> ```bash
> # First bootstrap (no Amplify URL yet):
> npx cdk deploy --all -c env=dev -c allow_synthetic_endpoints=true
>
> # After Amplify URL is known, redeploy Compute with the real values:
> npx cdk deploy magnacms-dev-compute -c env=dev \
>   -c cors_origins=https://<your-app>.amplifyapp.com \
>   -c images_cdn_base_url=https://<your-apprunner-id>.us-east-1.awsapprunner.com/local-images
> ```

```bash
npx cdk deploy magnacms-dev-network magnacms-dev-data -c env=dev \
  -c cors_origins=https://<your-app>.amplifyapp.com \
  -c images_cdn_base_url=https://<your-apprunner-id>.us-east-1.awsapprunner.com/local-images
```

### 3. Populate the OpenAI API key

DataStack creates `magnacms-dev-openai-api-key` with an explicit placeholder string (`sk-proj-REPLACE_ME-...`). Populate it before Compute deploys so App Runner can pass the secret-strength validator on first boot:

```bash
aws secretsmanager put-secret-value \
  --secret-id magnacms-dev-openai-api-key \
  --secret-string '<your-sk-proj-key>'
```

### 4. Push a placeholder backend image to ECR, then deploy Compute

`cdk deploy` of the ComputeStack will fail at App Runner creation if the ECR repo is empty — App Runner needs an image to start the service. The bootstrap dance:

```bash
# Deploy Compute with --no-rollback so the ECR repo survives App
# Runner's expected first-boot failure. Without --no-rollback,
# CloudFormation rolls the whole stack back, deleting the ECR repo
# before we get a chance to push to it.
npx cdk deploy magnacms-dev-compute --no-rollback -c env=dev
# Compute will fail at App Runner creation — that's expected. The ECR
# repo survives in CREATE_COMPLETE state.

# Build + push the real backend image. ECR repo name is deterministic
# (`magnacms-dev-backend`) so look it up directly instead of digging
# CloudFormation outputs out of a failed-state stack.
ECR_URI=$(aws ecr describe-repositories \
  --repository-names magnacms-dev-backend \
  --query 'repositories[0].repositoryUri' --output text)
aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin "$ECR_URI"
docker build -t "$ECR_URI:latest" ../backend/
docker push "$ECR_URI:latest"

# Now retry the deploy — App Runner should succeed this time.
# Drop --no-rollback now; subsequent deploys want normal rollback behavior.
npx cdk deploy magnacms-dev-compute -c env=dev
```

### 5. Deploy remaining stacks

```bash
npx cdk deploy magnacms-dev-edge magnacms-dev-observability -c env=dev
```

If you ever need to rotate the OpenAI key after Compute is RUNNING, App Runner picks up the new value on next deploy. Force a redeploy with:

```bash
APPRUNNER_ARN=$(aws cloudformation describe-stacks \
  --stack-name magnacms-dev-compute \
  --query "Stacks[0].Outputs[?ExportName=='magnacms-dev-compute-apprunner-service-arn'].OutputValue" \
  --output text)
aws apprunner start-deployment --service-arn "$APPRUNNER_ARN"
```

### 6. Run initial migrations

```bash
MIGRATION_CLUSTER=$(aws cloudformation describe-stacks \
  --stack-name magnacms-dev-compute \
  --query "Stacks[0].Outputs[?ExportName=='magnacms-dev-compute-migration-cluster-arn'].OutputValue" \
  --output text)
MIGRATION_TASK_DEF=$(aws cloudformation describe-stacks \
  --stack-name magnacms-dev-compute \
  --query "Stacks[0].Outputs[?ExportName=='magnacms-dev-compute-migration-task-arn'].OutputValue" \
  --output text)
SUBNETS=$(aws ec2 describe-subnets \
  --filters "Name=tag:environment,Values=dev" \
            "Name=map-public-ip-on-launch,Values=true" \
  --query 'Subnets[].SubnetId' --output text | tr '\t' ',')

# The VPC's default security group has no egress rules (CDK locks it
# down by default), so a Fargate task launched without an explicit
# `securityGroups` field will fail to reach Secrets Manager and
# bail with: "ResourceInitializationError: ... canceled, context
# deadline exceeded". Pass the dedicated egress SG provisioned for
# this purpose.
SG_FARGATE=$(aws ec2 describe-security-groups \
  --filters "Name=group-name,Values=magnacms-dev-fargate-egress" \
  --query 'SecurityGroups[0].GroupId' --output text)

aws ecs run-task \
  --cluster "$MIGRATION_CLUSTER" \
  --task-definition "$MIGRATION_TASK_DEF" \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SG_FARGATE],assignPublicIp=ENABLED}"
```

Watch for the task to reach STOPPED with exit code 0 in the ECS console. Logs are in the `magnacms-dev-compute-MigrationTaskmigrateLogGroup*` CloudWatch group.

### 6a. (Optional) Seed demo data

The same Fargate task definition runs `python -m app.scripts.seed`
when the command is overridden, populating `demo@magnacms.dev /
DemoPass123` plus a handful of content pieces (mock provider — no
OpenAI cost). **Caveat:** the seed currently generates demo images
to `/app/local_images` on the Fargate task's container filesystem,
which is then thrown away. The image rows land in the DB but the
PNG bytes never reach App Runner's container, so seeded thumbnails
404. Until the S3 image-storage adapter ships, plan to demo live
image generation from the UI instead of relying on seeded
thumbnails.

```bash
aws ecs run-task \
  --cluster "$MIGRATION_CLUSTER" \
  --task-definition "$MIGRATION_TASK_DEF" \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SG_FARGATE],assignPublicIp=ENABLED}" \
  --overrides '{"containerOverrides":[{"name":"migrate","command":["python","-m","app.scripts.seed"]}]}'
```

### 7. Smoke test `/health`

```bash
APPRUNNER_URL=$(aws cloudformation describe-stacks \
  --stack-name magnacms-dev-compute \
  --query "Stacks[0].Outputs[?ExportName=='magnacms-dev-compute-apprunner-service-url'].OutputValue" \
  --output text)
curl -fsSL "https://$APPRUNNER_URL/api/v1/health"
```

Expected: `{"status":"ok","version":"0.1.0","environment":"dev","dependencies":{...}}`.

### 8. Update post-deploy env vars (App Runner + Amplify)

Since PR #145 the App Runner env vars `CORS_ORIGINS` and
`IMAGES_CDN_BASE_URL` are driven entirely by CDK context — do NOT
edit them in the App Runner console. Editing the runtime config there
desyncs from the CDK template and the next `cdk deploy` will overwrite
your manual change. The only path is:

```bash
cd infra
npx cdk deploy magnacms-dev-compute --exclusively \
  -c env=dev \
  -c cors_origins=https://<your-app>.amplifyapp.com \
  -c images_cdn_base_url=https://<your-apprunner-id>.us-east-1.awsapprunner.com/local-images
```

App Runner force-redeploys when the CDK template changes the env vars.

`IMAGES_CDN_BASE_URL` MUST be set — the old runbook said to leave it
empty until CloudFront lands, but `LocalImageStorage` (still the
current adapter; see `app/services/image_storage.py`) builds image
URLs by concatenating this prefix with the storage key. An empty
value produces relative `<img src>` paths that 404 from the Amplify
origin. For the current demo, point it at the App Runner URL's
`/local-images` static mount; swap it for the CloudFront distribution
when that ships.

**Amplify** → `magnacms-dev` → App settings → Environment variables
(this part IS console-driven because EdgeStack doesn't manage them):

1. Add `NEXT_PUBLIC_API_BASE_URL` = `https://<apprunner-url>/api/v1`
2. (Optional) `NEXT_PUBLIC_SENTRY_DSN` once you provision a Sentry project

Without `NEXT_PUBLIC_API_BASE_URL`, the built frontend defaults to `http://localhost:8000/api/v1` and every request fails in production. Trigger a fresh Amplify build after the env update so the new value is baked into the bundle.

### 8a. Set CloudWatch log retention manually

ObservabilityStack pre-creates two log groups, but App Runner ignores them and creates its own under `/aws/apprunner/<service-name>/<service-id>/...` where the service-id is randomly assigned. After App Runner is RUNNING, find the real log groups and set retention:

```bash
SERVICE_ID=$(aws apprunner describe-service \
  --service-arn "$APPRUNNER_ARN" \
  --query 'Service.ServiceId' --output text)
for stream in service application; do
  aws logs put-retention-policy \
    --log-group-name "/aws/apprunner/magnacms-dev-backend/$SERVICE_ID/$stream" \
    --retention-in-days 14
done
```

The pre-created groups can be deleted (`aws logs delete-log-group ...`) — they're never used.

### 9. **PREFLIGHT: Verify rate-limit IP identity** (P1.10 follow-up — critical)

The rate limiter in `app/middleware/rate_limit.py` keys on `scope["client"]`. Verify that App Runner forwards the real client IP rather than its internal load-balancer peer:

```bash
# From a single source IP, hit /auth/login 11 times in 60s.
for i in $(seq 1 11); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -X POST "https://$APPRUNNER_URL/api/v1/auth/login" \
    -H "Content-Type: application/json" \
    -d '{"email":"test@example.com","password":"x"}'
done
```

Expected: ten 401s (invalid credentials), then a 429 (rate-limited) on attempt 11.

**If you get 429 immediately on attempt 1 or 2, the limiter is keying on App Runner's load-balancer peer IP, not the real client.** Every user shares one bucket — global throttling at 10 req/min. Fix before going public:

1. Add `TRUST_PROXY_XFF=true` env var to App Runner
2. Update `rate_limit.py` to read `X-Forwarded-For` when the flag is set, scoped to App Runner egress IPs as trusted proxies

(See P1.10 plan notes for the follow-up code change.)

### 10. Connect Amplify to GitHub

CDK creates the Amplify app shell but can't auto-connect to a GitHub repo without an OAuth token. From the Amplify console:

1. Amplify → `magnacms-dev` → App settings → Repository settings → Reconnect repository
2. Authorize the GitHub App for `Eslam93/MagnaCMS`
3. Confirm the `main` branch is detected and auto-deploys are enabled

First Amplify build runs against the current `main` HEAD.

### 11. Record the live URLs in README

In the project root `README.md` §1 "Live demo":

```markdown
- **Backend**: https://<apprunner-url>/api/v1/health
- **Frontend**: https://<amplify-branch>.<amplify-app-id>.amplifyapp.com
```

### 12. Flip `deploy.yml` to auto-trigger

Once the manual deploy succeeds end-to-end (above), update `.github/workflows/deploy.yml`:

```yaml
on:
  workflow_dispatch:
    inputs:
      env: ...
  push:
    branches: [main]
    paths:
      - 'backend/**'
      - '.github/workflows/deploy.yml'
```

Also add the required GitHub Secrets:

- `AWS_DEPLOY_ROLE_ARN` — OIDC role ARN from your bootstrap. Create with `aws iam create-role` + the GitHub OIDC trust policy (see [AWS docs](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_create_oidc.html)).

## Routine deploys (after first-deploy bootstrap)

Once everything is set up, every push to `main` that touches `backend/` triggers `deploy.yml` automatically. The workflow:

1. OIDC-assumes the deploy role
2. Builds + pushes the backend Docker image to ECR (`:latest` + `:<sha>`)
3. Runs migrations as a Fargate one-off task
4. Triggers App Runner deployment
5. Waits for RUNNING status
6. Smoke-tests `/health`

If any step fails, the workflow exits non-zero and notifies on the PR / commit.

## Teardown

```bash
cd infra
npx cdk destroy --all -c env=dev
# Plus: delete the Amplify app manually from the console
#       (CDK has trouble removing Amplify apps connected to GitHub)
```

## Known issues

- **App Runner first deploy without a pushed image fails.** That's expected (see step 4). Push the image, then retry.
- **`amplify.yml` not yet present.** Lands in P2.9a (frontend scaffold). Until then, the inline buildSpec in EdgeStack serves as the build config.
- **CloudFront for images is deferred to Phase 5.** EdgeStack ships Amplify only because of a circular dependency between DataStack and CloudFront-for-S3 OAC. See PR #124 for the full reasoning.
- **The `prod` environment isn't wired.** `loadConfig('prod')` throws at startup. Adding prod is a single-PR follow-up — copy the dev entry in `lib/config.ts`, tighten instance sizes/retention/devIpAllowlist, switch removalPolicy to RETAIN, set `multi-AZ: true` on RDS.
