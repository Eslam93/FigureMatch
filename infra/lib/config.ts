/**
 * Per-environment infrastructure configuration.
 *
 * Single source of truth for instance sizes, retention, CIDR ranges, and
 * other knobs that differ between `dev`, `staging`, and `prod`. Stacks
 * read from this object rather than hard-coding values — adding a new
 * environment is a matter of adding a new entry here.
 *
 * Only `dev` is implemented for Phase 2. `prod` lands as a follow-up
 * with stricter defaults (multi-AZ RDS, longer retention, larger
 * instance types, no public dev-IP allowlist).
 */

import { Duration } from "aws-cdk-lib";

export type EnvName = "dev" | "staging" | "prod";

export interface EnvConfig {
  /** Environment name (matches the backend's `ENVIRONMENT` setting). */
  envName: EnvName;
  /** AWS account ID. Undefined → CDK falls back to current CLI context. */
  account?: string;
  /** AWS region for all resources. */
  region: string;
  /**
   * IP CIDRs (e.g. office, home) allowed to reach RDS directly in
   * addition to App Runner's egress prefix list. Empty array = locked
   * down to App Runner only. Recommended: keep empty in prod.
   */
  devIpAllowlist: string[];
  /** RDS instance class. */
  rdsInstanceClass: string;
  /** RDS allocated storage in GiB. */
  rdsAllocatedStorageGb: number;
  /** Days of RDS automated backup retention. 0 disables backups. */
  rdsBackupRetention: Duration;
  /** App Runner min/max instance count. */
  apprunnerMinInstances: number;
  apprunnerMaxInstances: number;
  /** App Runner CPU + memory per instance. */
  apprunnerCpu: string;
  apprunnerMemory: string;
  /** CloudWatch log retention in days. */
  logRetentionDays: number;
  /** Frontend / Amplify domain pattern (for CORS origins on App Runner). */
  amplifyAppName: string;
  /** S3 bucket logical name (env suffix appended). */
  imagesBucketBaseName: string;
}

const DEV_CONFIG: EnvConfig = {
  envName: "dev",
  // account intentionally undefined; CDK resolves from environment at deploy time
  region: "us-east-1",
  devIpAllowlist: [], // populated post-deploy via cdk context
  rdsInstanceClass: "db.t4g.micro",
  rdsAllocatedStorageGb: 20,
  rdsBackupRetention: Duration.days(0), // off in dev to keep tear-down clean
  apprunnerMinInstances: 1,
  apprunnerMaxInstances: 3,
  // Bumped from 0.25 vCPU / 0.5 GB after the hardening-pass review.
  // gpt-image-1 responses carry a 1-3 MB base64 PNG; with FastAPI +
  // Pydantic + the OpenAI SDK already resident (~200 MB), the
  // previous size was OOM-adjacent under any concurrent image-gen
  // load. 1 vCPU / 2 GB leaves headroom without changing the App
  // Runner pricing tier dramatically.
  apprunnerCpu: "1 vCPU",
  apprunnerMemory: "2 GB",
  logRetentionDays: 14,
  amplifyAppName: "figurematch-dev",
  imagesBucketBaseName: "ai-content-images",
};

const CONFIGS: Record<EnvName, EnvConfig> = {
  dev: DEV_CONFIG,
  // staging + prod: not implemented yet. Throwing on lookup is intentional
  // so a typo like `cdk deploy -c env=prdo` fails loudly rather than
  // silently building dev resources under the wrong stack name.
  staging: undefined as unknown as EnvConfig,
  prod: undefined as unknown as EnvConfig,
};

/**
 * Load env config by name. Throws on unknown env or unimplemented env.
 * The throw shape ("Unknown environment") is parseable in CI for clear
 * error reporting.
 */
export function loadConfig(envName: string): EnvConfig {
  if (envName !== "dev" && envName !== "staging" && envName !== "prod") {
    throw new Error(
      `Unknown environment: ${envName!}. Valid envs: dev, staging, prod.`,
    );
  }
  const cfg = CONFIGS[envName];
  if (!cfg) {
    throw new Error(
      `Environment ${envName} is documented but not implemented yet. ` +
        `Only "dev" is wired up for Phase 2.`,
    );
  }
  return cfg;
}
