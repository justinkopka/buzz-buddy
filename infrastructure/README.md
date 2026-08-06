# BuzzBuddy Infrastructure

CDK (TypeScript) app that deploys the backend to AWS. One stack (`BuzzBuddyStack`, `lib/buzzbuddy-stack.ts`): a container-image Lambda function, a `live` alias, a public Function URL bound to that alias, and references to Secrets Manager secrets for the app's API keys.

Deploys are run locally by hand for now — there is no CI/CD pipeline yet (see `docs/adr/` notes for the planned GitHub Actions follow-up).

## Architecture summary

- **Compute:** `backend/` is packaged as a Docker image (`backend/Dockerfile`, based on `public.ecr.aws/lambda/python:3.13`) and deployed as a Lambda container-image function. CDK builds and pushes this image via `DockerImageCode.fromImageAsset()`, which lands in the shared ECR repo CDK creates during `cdk bootstrap` — not a dedicated repo.
- **Invocation:** a Lambda **Function URL**, `AuthType: NONE` (public). This is deliberate — the app already enforces auth itself (Supabase-issued JWTs, validated in `backend/app/auth.py` against Supabase's JWKS endpoint, gating the whole chat router in `backend/app/api/routes/chat.py`). `AWS_IAM` Function URL auth was considered and rejected: it authenticates AWS principals via SigV4, not end users, and would break browser access entirely.
- **Rollback:** the Function URL is bound to a `live` **Alias**, not to `$LATEST`. Every real deploy publishes a new immutable Lambda **Version**; the alias points at the current one. Rolling back means moving the alias pointer, not redeploying (see below).
- **Secrets:** the 5 backend API keys live in AWS Secrets Manager under `buzzbuddy/prod/*`, created manually outside CDK — the stack never creates or owns the secret values (so `cdk destroy` can never delete them). CDK references them by name and grants the Lambda execution role read access. `backend/app/main.py` fetches the actual values at cold start via `boto3`, not via a CloudFormation dynamic reference — this keeps plaintext keys out of the Lambda console and CloudFormation template.
- **CORS:** handled entirely by FastAPI's `CORSMiddleware` in `backend/app/main.py`, not at the Function URL layer — deliberately, to avoid two independent CORS layers producing conflicting headers.
- **IAM:** the Lambda execution role is CDK's default (`AWSLambdaBasicExecutionRole` for CloudWatch Logs) plus a scoped `secretsmanager:GetSecretValue`/`DescribeSecret` grant on exactly the 5 named secrets. No other AWS service permissions — all external calls (Anthropic, OpenAI, Supabase) are plain HTTPS, not AWS SDK calls.

## Prerequisites

- Node.js and npm
- Docker Desktop **running** (image builds happen locally, even for `cdk deploy`, not just for a separate build step)
- AWS CLI v2, authenticated with credentials for the target account
- The 5 secrets already created in Secrets Manager (see below) — the stack references them but doesn't create them

## One-time setup

```
cd infrastructure
npm install

# Once per AWS account/region — needs near-admin credentials, unlike routine deploys
npx cdk bootstrap aws://<ACCOUNT_ID>/us-east-2
```

Create the secrets (values are never stored in this repo):
```
aws secretsmanager create-secret --name buzzbuddy/prod/ANTHROPIC_API_KEY --secret-string "<value>" --region us-east-2
aws secretsmanager create-secret --name buzzbuddy/prod/SUPABASE_URL --secret-string "<value>" --region us-east-2
aws secretsmanager create-secret --name buzzbuddy/prod/SUPABASE_SECRET_KEY --secret-string "<value>" --region us-east-2
# Not created yet — deferred until the features that need them exist:
# aws secretsmanager create-secret --name buzzbuddy/prod/OPENAI_API_KEY --secret-string "<value>" --region us-east-2
# aws secretsmanager create-secret --name buzzbuddy/prod/LANGCHAIN_API_KEY --secret-string "<value>" --region us-east-2
```
Secret names must exactly match `SECRET_NAME_PREFIX` + key name in `lib/buzzbuddy-stack.ts`. `backend/app/main.py`'s secrets-fetch loop only requests the keys currently uncommented there — uncomment the corresponding line when a secret is actually created, otherwise the Lambda will crash on cold start trying to fetch a secret that doesn't exist.

## Day-to-day deploy

```
cd infrastructure
npx cdk diff        # sanity-check what will change
npx cdk deploy       # builds the image, pushes it, updates the stack
```
`cdk deploy` will prompt to confirm any IAM changes before applying them. The `FunctionUrl` output printed at the end should stay stable across normal deploys (see "Function URL stability" below) — worth a glance each time as a sanity check rather than assumed.

## Debugging

**Credentials aren't resolving / `Unable to resolve AWS account`:**
```
aws sts get-caller-identity
```
If this fails, your AWS CLI session has expired — re-authenticate however your account is set up (SSO login, `aws login`, etc.) and retry. CDK CLI commands must be run from this directory (`infrastructure/`), since that's where `cdk.json` lives — running them from the repo root or `backend/` will fail with a "cannot find app" style error.

**Checking logs:**
```
aws logs tail /aws/lambda/buzzbuddy-backend --follow --region us-east-2
```
Or via the CloudWatch console, log group `/aws/lambda/buzzbuddy-backend`. A clean cold start should show no missing-secret or missing-env-var errors — if `main.py`'s boto3 fetch loop errors, it'll show up here immediately.

**Checking the Function URL directly** (useful to isolate "is the backend actually broken" from "is the frontend/browser the problem"):
```
curl -X POST "<function-url>chat-message" -H "Authorization: Bearer <token>" -H "Content-Type: application/json" -d "{\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}]}"
```
A request with no/invalid token should return `401 {"detail": "Invalid or expired token"}` — that's the app's own auth working correctly, not a bug. Note: browser-based testing tools (e.g. the FastAPI Swagger docs UI) have been unreliable for sending a custom `Authorization` header in this setup — prefer curl or a real HTTP client for manual testing against the deployed endpoint.

**Rolling back a bad deploy:**
```
aws lambda list-versions-by-function --function-name buzzbuddy-backend --region us-east-2
aws lambda update-alias --function-name buzzbuddy-backend --name live --function-version <N> --region us-east-2
```
Takes effect immediately, no redeploy needed. This is tactical, not permanent — the next real `cdk deploy` publishes a new version and moves `live` forward again, overriding the manual rollback. Caveat: because images live in CDK's shared bootstrap ECR repo (not a repo this stack controls the retention policy for), how far back you can roll isn't guaranteed. Check current retention with:
```
aws ecr get-lifecycle-policy --repository-name cdk-hnb659fds-container-assets-<ACCOUNT_ID>-us-east-2 --region us-east-2
```

**Function URL stability:** the URL is tied to the `live` alias's `AWS::Lambda::Url` CloudFormation resource, which has a stable logical ID as long as the stack's construct structure doesn't change. Ordinary deploys (code changes, env var/CORS updates, etc.) update resources in place and don't change the URL. It would only change if the stack is destroyed and redeployed from scratch, or if the `LiveAlias`/Function URL constructs are renamed/restructured in `lib/buzzbuddy-stack.ts`.

## Not yet done (deliberate, not overlooked)

- **CI/CD:** deploys are local-only (`cdk deploy` by hand). GitHub Actions is a planned follow-up, deferred until the CDK stack itself is well understood.
- **Streaming:** `chat.py`'s `/chat-message` endpoint returns a `StreamingResponse`, but Lambda Function URLs only support real incremental response streaming for the Node.js runtime natively — Python needs the [Lambda Web Adapter](https://github.com/awslabs/aws-lambda-web-adapter) extension, not yet added.
- **ECR retention control:** using CDK's shared bootstrap asset repo trades away fine-grained control over image retention/rollback depth for deploy simplicity. A dedicated repo with an explicit lifecycle rule is the alternative if rollback guarantees become important later.
- **Rate limiting / abuse protection:** the Function URL is public with no throttling. Not urgent today, but a WAF or similar would be the next hardening step if abuse becomes a concern.
