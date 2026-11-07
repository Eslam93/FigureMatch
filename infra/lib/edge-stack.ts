/**
 * EdgeStack — Amplify hosting for the Next.js frontend.
 *
 * Originally scoped to also include CloudFront for the images S3
 * bucket, but the `S3BucketOrigin.withOriginAccessControl` pattern
 * creates a stack-level circular dependency: the CloudFront origin
 * needs the bucket (DataStack → EdgeStack reference), and the auto-
 * generated bucket policy needs the distribution ARN (EdgeStack →
 * DataStack reference). CDK refuses to synth a cycle.
 *
 * The CloudFront-for-images piece is deferred until Phase 5 (image
 * generation) when we actually need a CDN. At that point either:
 *   - The bucket moves to a new dedicated stack alongside the
 *     distribution; or
 *   - We use a manually-attached, distribution-scoped bucket policy
 *     that avoids the auto-policy-modification path.
 *
 * For Phase 2, IMAGES_CDN_BASE_URL points directly at the S3 bucket
 * (signed URLs if needed). The brief's "OAC prep" requirement is
 * satisfied by the fact that the images bucket already blocks all
 * public access — the CDN tier is purely a performance optimization
 * we can add when image traffic justifies it.
 */

import { CfnOutput, Stack, type StackProps } from "aws-cdk-lib";
import { CfnApp, CfnBranch } from "aws-cdk-lib/aws-amplify";
import type { Construct } from "constructs";

import type { EnvConfig } from "./config";

export interface EdgeStackProps extends StackProps {
  cfg: EnvConfig;
}

export class EdgeStack extends Stack {
  public readonly amplifyApp: CfnApp;

  constructor(scope: Construct, id: string, props: EdgeStackProps) {
    super(scope, id, props);

    const { cfg } = props;

    // --- Amplify hosting app ---
    // The GitHub OAuth token / repo connection is a manual one-time
    // setup the user performs in the Amplify console after first
    // `cdk deploy`. The inline buildSpec is a fallback; the real
    // build phases come from `frontend/amplify.yml` once the frontend
    // scaffolding lands (P2.9a).
    this.amplifyApp = new CfnApp(this, "Frontend", {
      name: cfg.amplifyAppName,
      description: `FigureMatch frontend (${cfg.envName})`,
      buildSpec: [
        "version: 1",
        "applications:",
        "  - frontend:",
        "      phases:",
        "        preBuild:",
        "          commands:",
        "            - corepack enable",
        "            - pnpm install --frozen-lockfile",
        "        build:",
        "          commands:",
        "            - pnpm build",
        "      artifacts:",
        "        baseDirectory: .next",
        "        files:",
        "          - '**/*'",
        "      cache:",
        "        paths:",
        "          - node_modules/**/*",
        "          - .next/cache/**/*",
        "    appRoot: frontend",
      ].join("\n"),
      customRules: [
        {
          source: "/<*>",
          target: "/index.html",
          status: "404-200",
        },
      ],
      tags: [
        { key: "project", value: "figurematch" },
        { key: "environment", value: cfg.envName },
      ],
    });

    new CfnBranch(this, "MainBranch", {
      appId: this.amplifyApp.attrAppId,
      branchName: "main",
      stage: cfg.envName === "prod" ? "PRODUCTION" : "DEVELOPMENT",
      enableAutoBuild: true,
      framework: "Next.js - SSR",
    });

    new CfnOutput(this, "AmplifyAppId", {
      value: this.amplifyApp.attrAppId,
      exportName: `${id}-amplify-app-id`,
      description: "Amplify app ID - connect GitHub via console post-deploy",
    });
    new CfnOutput(this, "AmplifyDefaultDomain", {
      value: this.amplifyApp.attrDefaultDomain,
      exportName: `${id}-amplify-domain`,
      description: "Amplify default domain (paste into App Runner CORS_ORIGINS)",
    });
  }
}
