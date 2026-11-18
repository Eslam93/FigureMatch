// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

/**
 * ObservabilityStack tests.
 *
 * The stack is currently a placeholder — App Runner log-group
 * pre-creation was removed in P2.12 (the names had no service-id, so
 * App Runner ignored them and created its own without retention).
 * Log-retention setup is now a post-deploy `aws logs put-retention-policy`
 * step documented in DEPLOY.md §7a.
 *
 * The stack will gain content again in P11.6 (CloudWatch 5xx alarm
 * + SNS topic). Until then these tests just assert it synths cleanly
 * with no resources.
 */

import { App } from "aws-cdk-lib";
import { Template } from "aws-cdk-lib/assertions";

import { loadConfig } from "../lib/config";
import { ObservabilityStack } from "../lib/observability-stack";

describe("ObservabilityStack (dev)", () => {
  const cfg = loadConfig("dev");
  const app = new App();
  const stack = new ObservabilityStack(app, "test-observability", {
    env: { region: cfg.region },
    cfg,
  });
  const template = Template.fromStack(stack);

  it("matches snapshot", () => {
    expect(template.toJSON()).toMatchSnapshot();
  });

  it("provisions no log groups (pre-creation removed — names had no service-id)", () => {
    template.resourceCountIs("AWS::Logs::LogGroup", 0);
  });

  it("provisions no resources yet (P11.6 will add the 5xx alarm)", () => {
    const resources = template.toJSON().Resources ?? {};
    expect(Object.keys(resources)).toEqual([]);
  });
});
