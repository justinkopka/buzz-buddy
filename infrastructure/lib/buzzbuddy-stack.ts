import * as path from 'path';
import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import * as logs from 'aws-cdk-lib/aws-logs';

const SECRET_NAME_PREFIX = 'buzzbuddy/prod/';
const SECRET_KEYS = [
  'ANTHROPIC_API_KEY',
  'OPENAI_API_KEY',
  'SUPABASE_URL',
  'SUPABASE_SECRET_KEY',
  'LANGCHAIN_API_KEY',
] as const;

export class BuzzBuddyStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // Secrets are created manually outside CDK (never in source control, never
    // owned by this stack) so a `cdk destroy` can never take them out.
    const secrets = Object.fromEntries(
      SECRET_KEYS.map((key) => [
        key,
        secretsmanager.Secret.fromSecretNameV2(this, `${key}Secret`, `${SECRET_NAME_PREFIX}${key}`),
      ]),
    ) as Record<(typeof SECRET_KEYS)[number], secretsmanager.ISecret>;

    const logGroup = new logs.LogGroup(this, 'BackendLogGroup', {
      logGroupName: '/aws/lambda/buzzbuddy-backend',
      retention: logs.RetentionDays.ONE_MONTH,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    const fn = new lambda.DockerImageFunction(this, 'BackendFunction', {
      functionName: 'buzzbuddy-backend',
      code: lambda.DockerImageCode.fromImageAsset(path.join(__dirname, '..', '..', 'backend')),
      memorySize: 512,
      timeout: cdk.Duration.seconds(30),
      logGroup,
      environment: {
        ANTHROPIC_API_KEY_SECRET_ARN: secrets.ANTHROPIC_API_KEY.secretArn,
        OPENAI_API_KEY_SECRET_ARN: secrets.OPENAI_API_KEY.secretArn,
        SUPABASE_URL_SECRET_ARN: secrets.SUPABASE_URL.secretArn,
        SUPABASE_SECRET_KEY_SECRET_ARN: secrets.SUPABASE_SECRET_KEY.secretArn,
        LANGCHAIN_API_KEY_SECRET_ARN: secrets.LANGCHAIN_API_KEY.secretArn,
      },
    });

    Object.values(secrets).forEach((secret) => secret.grantRead(fn));

    // Function URL is bound to this alias, not to $LATEST, so a bad deploy can
    // be rolled back with `aws lambda update-alias` without redeploying.
    const alias = new lambda.Alias(this, 'LiveAlias', {
      aliasName: 'live',
      version: fn.currentVersion,
    });

    // Public: app-level JWT auth (Supabase, validated in backend/app/auth.py)
    // already gates every route, so AWS_IAM auth here would only break the
    // browser client without adding real protection.
    const fnUrl = alias.addFunctionUrl({
      authType: lambda.FunctionUrlAuthType.NONE,
    });

    new cdk.CfnOutput(this, 'FunctionUrl', { value: fnUrl.url });
    new cdk.CfnOutput(this, 'FunctionName', { value: fn.functionName });
  }
}
