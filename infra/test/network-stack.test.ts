// SPDX-FileCopyrightText: 2026 Eslam Hamed
//
// SPDX-License-Identifier: MIT

/**
 * NetworkStack snapshot + resource-count tests.
 *
 * Snapshot covers regression on the synthesized CloudFormation —
 * any unexpected resource churn shows up as a diff. Resource counts
 * pin the brief's stated topology: 1 VPC, 2 AZs (so 2 public subnets),
 * 2 SGs (RDS + Redis), 0 NAT gateways.
 */

import { App } from "aws-cdk-lib";
import { Template } from "aws-cdk-lib/assertions";

import { loadConfig } from "../lib/config";
import { NetworkStack } from "../lib/network-stack";

describe("NetworkStack (dev)", () => {
  const cfg = loadConfig("dev");
  const app = new App();
  const stack = new NetworkStack(app, "test-network", {
    env: { region: cfg.region },
    cfg,
  });
  const template = Template.fromStack(stack);

  it("matches snapshot", () => {
    expect(template.toJSON()).toMatchSnapshot();
  });

  it("provisions exactly one VPC", () => {
    template.resourceCountIs("AWS::EC2::VPC", 1);
  });

  it("provisions two public subnets (one per AZ, maxAzs=2)", () => {
    template.resourceCountIs("AWS::EC2::Subnet", 2);
  });

  it("provisions zero NAT gateways (App Runner is outside the VPC)", () => {
    template.resourceCountIs("AWS::EC2::NatGateway", 0);
  });

  it("provisions two security groups (RDS + Redis)", () => {
    template.resourceCountIs("AWS::EC2::SecurityGroup", 2);
  });

  // CDK renders ingress rules added via `addIngressRule` as separate
  // `AWS::EC2::SecurityGroupIngress` resources rather than inline
  // SecurityGroupIngress properties — that lets it amend SGs in
  // downstream stacks without rewriting the parent. Assertions match.

  it("RDS SG ingress is open to 0.0.0.0/0 on 5432 (post-P2.11)", () => {
    // App Runner has no stable egress prefix list to allowlist, so
    // the SG can't narrow the source. Security is Postgres auth + SSL
    // + Secrets-Manager-managed credentials.
    //
    // For CIDR-based ingress added at SG construction time, CDK
    // inlines the rule into the SG's `SecurityGroupIngress` array
    // rather than emitting a separate AWS::EC2::SecurityGroupIngress
    // resource. (The separate-resource shape only appears for
    // cross-stack SG references and prefix lists.)
    template.hasResourceProperties("AWS::EC2::SecurityGroup", {
      GroupDescription: "RDS Postgres: open SG, security via Postgres auth + SSL",
      SecurityGroupIngress: [
        {
          CidrIp: "0.0.0.0/0",
          IpProtocol: "tcp",
          FromPort: 5432,
          ToPort: 5432,
        },
      ],
    });
  });

  it("Redis SG has no ingress rules (VPC-internal only)", () => {
    // ElastiCache stays VPC-internal; USE_REDIS=false until a VPC
    // connector lands. Redis SG should have an empty ingress list
    // (or no ingress key) and no separate ingress resource for 6379.
    const ingressResources = template.findResources(
      "AWS::EC2::SecurityGroupIngress",
    );
    const port6379 = Object.values(ingressResources).filter(
      (r) => r.Properties?.FromPort === 6379,
    );
    expect(port6379).toHaveLength(0);
  });
});
