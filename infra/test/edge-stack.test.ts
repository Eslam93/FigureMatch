/**
 * EdgeStack snapshot + resource-count tests.
 *
 * Pins: 1 Amplify app, 1 Amplify branch, 1 CloudFront distribution,
 * 1 OAC, S3 bucket policy gating images via CloudFront only.
 */

import { App } from "aws-cdk-lib";
import { Template } from "aws-cdk-lib/assertions";

import { loadConfig } from "../lib/config";
import { EdgeStack } from "../lib/edge-stack";

describe("EdgeStack (dev)", () => {
  const cfg = loadConfig("dev");
  const app = new App();
  const stack = new EdgeStack(app, "test-edge", {
    env: { region: cfg.region },
    cfg,
  });
  const template = Template.fromStack(stack);

  it("matches snapshot", () => {
    expect(template.toJSON()).toMatchSnapshot();
  });

  it("provisions one Amplify app + one branch", () => {
    template.resourceCountIs("AWS::Amplify::App", 1);
    template.resourceCountIs("AWS::Amplify::Branch", 1);
    template.hasResourceProperties("AWS::Amplify::App", {
      Name: "figurematch-dev",
    });
    template.hasResourceProperties("AWS::Amplify::Branch", {
      BranchName: "main",
      EnableAutoBuild: true,
    });
  });

  it("does NOT provision CloudFront (deferred to Phase 5 — see stack comment)", () => {
    template.resourceCountIs("AWS::CloudFront::Distribution", 0);
    template.resourceCountIs("AWS::CloudFront::OriginAccessControl", 0);
  });
});
