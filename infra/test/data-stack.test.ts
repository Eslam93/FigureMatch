/**
 * DataStack snapshot + resource-count tests.
 *
 * Pins the data topology: one RDS instance, one S3 bucket, two
 * Secrets Manager secrets (JWT + OpenAI key — RDS auto-creates its
 * own secret so the count is 3 from CDK's perspective). The
 * ElastiCache Serverless Redis cluster was dropped in the
 * security-and-storage hardening pass; if it returns, re-add the
 * resource-count assertion.
 */

import { App } from "aws-cdk-lib";
import { Template } from "aws-cdk-lib/assertions";

import { loadConfig } from "../lib/config";
import { DataStack } from "../lib/data-stack";
import { NetworkStack } from "../lib/network-stack";

describe("DataStack (dev)", () => {
  const cfg = loadConfig("dev");
  const app = new App();
  const network = new NetworkStack(app, "test-network", {
    env: { region: cfg.region },
    cfg,
  });
  const stack = new DataStack(app, "test-data", {
    env: { region: cfg.region },
    cfg,
    vpc: network.vpc,
    sgRds: network.sgRds,
  });
  const template = Template.fromStack(stack);

  it("matches snapshot", () => {
    expect(template.toJSON()).toMatchSnapshot();
  });

  it("provisions exactly one RDS Postgres instance", () => {
    template.resourceCountIs("AWS::RDS::DBInstance", 1);
    template.hasResourceProperties("AWS::RDS::DBInstance", {
      Engine: "postgres",
      DBInstanceClass: "db.t4g.micro",
      PubliclyAccessible: true,
      StorageEncrypted: true,
    });
  });

  it("does not provision an ElastiCache cluster (deferred to Phase 11)", () => {
    template.resourceCountIs("AWS::ElastiCache::ServerlessCache", 0);
    template.resourceCountIs("AWS::ElastiCache::SubnetGroup", 0);
  });

  it("provisions one S3 images bucket with public access blocked", () => {
    template.resourceCountIs("AWS::S3::Bucket", 1);
    // BucketName is templated as `ai-content-images-dev-${AWS::AccountId}`
    // — CDK renders this as a CloudFormation Fn::Join. Assert on the
    // public-access configuration shape instead of the exact name.
    template.hasResourceProperties("AWS::S3::Bucket", {
      PublicAccessBlockConfiguration: {
        BlockPublicAcls: true,
        BlockPublicPolicy: true,
        IgnorePublicAcls: true,
        RestrictPublicBuckets: true,
      },
    });
  });

  it("provisions three Secrets Manager entries (JWT + OpenAI + RDS-auto)", () => {
    // CDK auto-creates an RDS password secret in addition to the two
    // we explicitly define, so the count is 3.
    template.resourceCountIs("AWS::SecretsManager::Secret", 3);
  });

  it("JWT secret uses generateSecretString with 64 chars (hex pattern)", () => {
    template.hasResourceProperties("AWS::SecretsManager::Secret", {
      Name: "figurematch-dev-jwt-secret",
      GenerateSecretString: {
        PasswordLength: 64,
        ExcludePunctuation: true,
      },
    });
  });

  it("OpenAI key secret has no generateSecretString (manual population)", () => {
    template.hasResourceProperties("AWS::SecretsManager::Secret", {
      Name: "figurematch-dev-openai-api-key",
    });
  });
});
