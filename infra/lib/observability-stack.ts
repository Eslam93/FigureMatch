/**
 * ObservabilityStack — placeholder for CloudWatch alarms (P11.6) and
 * any other observability resources that DON'T have an App-Runner-
 * generated identifier baked into their name.
 *
 * Original P2.6 design: pre-create App Runner log groups with
 * explicit retention. That doesn't work — App Runner emits to
 * `/aws/apprunner/<service-name>/<service-id>/{service,application}`
 * where `service-id` is randomly assigned at create time. Pre-created
 * groups under `/aws/apprunner/<service-name>/{service,application}`
 * never receive traffic; App Runner creates its own groups with no
 * retention configured.
 *
 * The honest fix is to set retention post-deploy via a one-liner
 * `aws logs put-retention-policy` call. `DEPLOY.md` step 7a covers it.
 * The CloudWatch alarm sketch (P11.6) and any future SNS topics live
 * here when they land.
 */

import { Stack, type StackProps } from "aws-cdk-lib";
import type { Construct } from "constructs";

import type { EnvConfig } from "./config";

export interface ObservabilityStackProps extends StackProps {
  cfg: EnvConfig;
}

export class ObservabilityStack extends Stack {
  constructor(scope: Construct, id: string, props: ObservabilityStackProps) {
    super(scope, id, props);

    const { cfg } = props;
    void cfg;

    // Placeholder. P11.6 lands the CloudWatch 5xx-rate alarm here:
    //
    //   new cloudwatch.Alarm(this, "AppRunner5xxAlarm", {
    //     metric: new cloudwatch.Metric({
    //       namespace: "AWS/AppRunner",
    //       metricName: "5xxStatusResponses",
    //       dimensionsMap: { ServiceName: `figurematch-${cfg.envName}-backend` },
    //       statistic: "Sum",
    //       period: Duration.minutes(5),
    //     }),
    //     threshold: 5,
    //     evaluationPeriods: 1,
    //     comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
    //   });
    //
    // Plus the SNS topic + email subscription.
  }
}
