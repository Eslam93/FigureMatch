#!/usr/bin/env node
/**
 * CDK app entry for FigureMatch infrastructure.
 *
 * Reads `--context env=dev` (or staging/prod once wired) and constructs
 * the five stacks (Network → Data → Compute → Edge → Observability) in
 * dependency order. Each stack is named `figurematch-${env}-${stack}` so
 * multiple environments can coexist in one AWS account if needed.
 *
 * # Required context for non-local deploys
 *
 * The backend's `Settings` validator rejects `CORS_ORIGINS` containing
 * `localhost` or `127.0.0.1` in any non-local environment, and an
 * empty `IMAGES_CDN_BASE_URL` makes generated images render as
 * relative paths that 404 from the Amplify origin. Both must be
 * passed explicitly:
 *
 *   npx cdk deploy --all \
 *     -c env=dev \
 *     -c cors_origins=https://<your-app>.amplifyapp.com \
 *     -c images_cdn_base_url=https://<your-apprunner-id>.us-east-1.awsapprunner.com/local-images
 *
 * `cors_origins` accepts a CSV string and lands on App Runner's
 * `CORS_ORIGINS` env var verbatim. `images_cdn_base_url` is the
 * scheme + host + path prefix the frontend will use for `<img src>`
 * tags; today that's the App Runner URL + `/local-images` until the
 * S3 + CloudFront adapter ships.
 *
 * Both values are validated by `resolveEndpointContext` (strict: https
 * only, no loopback hosts, no `.invalid` TLD). Synth aborts on bad
 * shape — see `lib/endpoint-context.ts` for the rule set.
 *
 * The escape hatch `-c allow_synthetic_endpoints=true` lets a bootstrap
 * deploy run before the real Amplify URL is known. In that mode the
 * resolver fills missing values with clearly-synthetic placeholders
 * (`https://figurematch-bootstrap.invalid`), the app prints a loud CDK
 * warning, and every resource is tagged `synthetic-endpoints=true` so
 * the placeholder state is visible from the CloudFormation console.
 * The placeholders pass the backend's `Settings` validator but produce
 * a loud user-visible failure on the first real request — exactly the
 * intended trade.
 */

import "source-map-support/register";
import * as cdk from "aws-cdk-lib";

import { ComputeStack } from "../lib/compute-stack";
import { loadConfig } from "../lib/config";
import { DataStack } from "../lib/data-stack";
import { EdgeStack } from "../lib/edge-stack";
import {
  resolveEndpointContext,
  type EndpointContextInput,
} from "../lib/endpoint-context";
import { NetworkStack } from "../lib/network-stack";
import { ObservabilityStack } from "../lib/observability-stack";

const app = new cdk.App();
const envName = app.node.tryGetContext("env") ?? "dev";
const cfg = loadConfig(envName);

const awsEnv: cdk.Environment = {
  account: cfg.account,
  region: cfg.region,
};

// Tag every resource with the env so it's easy to grep AWS console.
cdk.Tags.of(app).add("project", "figurematch");
cdk.Tags.of(app).add("environment", cfg.envName);
cdk.Tags.of(app).add("managed-by", "cdk");

// --- Resolve required context for non-local envs ---
const allowSyntheticRaw = app.node.tryGetContext("allow_synthetic_endpoints");
const allowSyntheticEndpoints =
  allowSyntheticRaw === "true" || allowSyntheticRaw === true;

const corsOriginsCtx = app.node.tryGetContext("cors_origins");
const imagesCdnBaseUrlCtx = app.node.tryGetContext("images_cdn_base_url");

const resolverInput: EndpointContextInput = {
  corsOrigins: typeof corsOriginsCtx === "string" ? corsOriginsCtx : undefined,
  imagesCdnBaseUrl:
    typeof imagesCdnBaseUrlCtx === "string" ? imagesCdnBaseUrlCtx : undefined,
  allowSyntheticEndpoints,
};

const { corsOrigins, imagesCdnBaseUrl, syntheticEndpointsUsed } =
  resolveEndpointContext(resolverInput);

if (syntheticEndpointsUsed) {
  // Surface the placeholder state two ways:
  //
  //   1. console.warn → immediate, unmissable visibility at the cdk
  //      synth/deploy command line. `Annotations.of(app).addWarning`
  //      doesn't bubble up reliably from the App scope in CDK v2 (the
  //      CLI walks Stack-scoped annotations only), so we print
  //      directly to stderr instead. Using stderr (not stdout) keeps
  //      `cdk synth | tee template.json` clean.
  //   2. A `synthetic-endpoints=true` tag on every resource so the
  //      placeholder state is visible from the CloudFormation console
  //      long after the synth log has scrolled away.
  //
  // A deploy that ships synthetic endpoints will not produce a working
  // app on the first request, so the operator must see this signal.
  // eslint-disable-next-line no-console
  console.warn(
    "\n⚠️  [FigureMatch] synthetic endpoints in effect.\n" +
      "    CORS_ORIGINS and/or IMAGES_CDN_BASE_URL are populated from\n" +
      "    placeholder values (either resolver-supplied or a `.invalid`\n" +
      "    value passed through the escape hatch). The deployed backend\n" +
      "    will reject browser requests until you redeploy with real\n" +
      "    CDK context. This mode is for first-bootstrap only.\n",
  );
  cdk.Tags.of(app).add("synthetic-endpoints", "true");
}

const network = new NetworkStack(app, `figurematch-${envName}-network`, {
  env: awsEnv,
  cfg,
});

const data = new DataStack(app, `figurematch-${envName}-data`, {
  env: awsEnv,
  cfg,
  vpc: network.vpc,
  sgRds: network.sgRds,
  // sgRedis kept on NetworkStack but unused by DataStack today — the
  // ElastiCache cluster was removed pending Phase 11 + a VPC connector.
});

const compute = new ComputeStack(app, `figurematch-${envName}-compute`, {
  env: awsEnv,
  cfg,
  vpc: network.vpc,
  imagesBucket: data.imagesBucket,
  jwtSecret: data.jwtSecret,
  openaiApiKeySecret: data.openaiApiKeySecret,
  rdsInstance: data.rdsInstance,
  corsOrigins,
  imagesCdnBaseUrl,
});

const edge = new EdgeStack(app, `figurematch-${envName}-edge`, {
  env: awsEnv,
  cfg,
});

const observability = new ObservabilityStack(
  app,
  `figurematch-${envName}-observability`,
  {
    env: awsEnv,
    cfg,
  },
);

void compute;
void edge;
void observability;

app.synth();
