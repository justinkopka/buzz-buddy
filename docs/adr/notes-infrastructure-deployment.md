# Notes: Infrastructure & Deployment Decisions

Raw notes from the session where the backend's AWS infrastructure was rebuilt in CDK, replacing a fully hand-clicked setup. Not a formal ADR — intended as source material to split into proper numbered ADRs later (candidate splits marked below). Each section: what was decided, why, and what alternatives were considered or explicitly rejected.

---

## Candidate ADR: Infrastructure-as-code tool — CDK

**Decision:** AWS CDK (TypeScript), one stack, deployed locally.

**Why:** Matches the existing "AWS Lambda + API Gateway"-style tech stack decision already made pre-Sprint-1. CDK has purpose-built L2 constructs for container-image Lambda + Function URL, which mapped closely onto what was already running by hand, minimizing the gap between "what CDK models" and "what's actually deployed."

**Not seriously compared against:** Terraform, SAM, Pulumi, raw CloudFormation. The choice leaned heavily on the user already wanting to try CDK going in — worth doing a real comparison pass when writing the actual ADR, even if the conclusion doesn't change, so the ADR reflects genuine trade-off analysis rather than "we didn't look at alternatives."

---

## Candidate ADR: Compute & invocation — container-image Lambda + Function URL (not API Gateway)

**Decision:** Kept the existing shape — Lambda packaged as a Docker container image (base: `public.ecr.aws/lambda/python:3.13`), invoked via a Lambda Function URL rather than migrating to API Gateway.

**Why:** API Gateway's extra features (custom domains without a separate CloudFront setup, usage plans, request validation, native throttling) aren't needed yet. Function URLs are simpler and cheaper for the current single-endpoint, single-consumer shape.

**Revisit if:** rate limiting/throttling becomes necessary (Function URLs have no native per-client throttling — API Gateway does), or a custom domain is wanted without extra CloudFront wiring.

---

## Candidate ADR: Auth model — public Function URL (`NONE`) + app-level JWT

**Decision:** Function URL `AuthType: NONE` (public internet-reachable), with all real authorization enforced at the application layer — Supabase-issued JWTs validated against Supabase's JWKS endpoint (`backend/app/auth.py`), gating the chat router (`backend/app/api/routes/chat.py`).

**Why / explicitly rejected alternative:** `AWS_IAM` Function URL auth was considered and rejected. It authenticates AWS principals via SigV4 signing — meant for service-to-service calls within the AWS account, not a public browser client. Enabling it would break frontend access outright without adding meaningful protection for this use case.

**Known gap, not yet addressed:** no rate limiting or abuse protection on the public Function URL. A malicious actor can still spam invocations (each costs money even when rejected with a 401). Not urgent at current scale; a WAF or similar would be the natural next step if it becomes one.

---

## Candidate ADR: Rollback strategy — Lambda Alias + Versions

**Decision:** Function URL is bound to a `live` Alias, not `$LATEST`. Every deploy that changes `backend/` publishes a new immutable Lambda Version; rollback = repointing the alias (`aws lambda update-alias`) rather than redeploying.

**Real constraint underlying this:** container-image Lambda functions reference their image in ECR by digest at invoke time — they do not get a private copy. If the referenced image is deleted from ECR, that Lambda Version stops working, including for rollback purposes.

**Trade-off explicitly made:** chose CDK's shared bootstrap-managed ECR asset repo (`DockerImageCode.fromImageAsset()`) over a dedicated, stack-owned ECR repo with an explicit lifecycle/retention rule. The shared repo is simpler (zero extra build/push steps, `cdk deploy` handles everything), but its retention policy isn't something this stack can tune — so rollback depth is best-effort, not guaranteed. The alternative (a dedicated repo with e.g. "keep last 10 images") would give real control at the cost of an extra manual build-and-push step before every deploy. Revisit this trade-off if rollback depth ever actually matters in practice.

---

## Candidate ADR: Secrets management — Secrets Manager, runtime fetch via boto3

**Decision:** 5 API keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `LANGCHAIN_API_KEY`) live in AWS Secrets Manager (`buzzbuddy/prod/*`), created manually outside CDK — the stack never creates the secret values, only references them by name and grants the Lambda execution role read access. `backend/app/main.py` fetches actual values from Secrets Manager at cold start using `boto3`, rather than having CDK resolve them at deploy time via a CloudFormation dynamic reference.

**Why runtime fetch over dynamic reference:** a CloudFormation dynamic reference would resolve secret values at deploy time and write them as plaintext Lambda environment variables — visible to anyone who can read the function's config in the console. Runtime fetch keeps plaintext out of the console/CloudFormation template entirely, and is what makes the IAM `grantRead` permission actually do real work (with a dynamic reference, the grant would be functionally unused, since the *deploying* role resolves the value, not the Lambda's own role).

**Why secrets aren't CDK-managed resources:** if CDK created the `Secret` resources, a `cdk destroy` or stack replacement could delete/schedule-delete them — too much blast radius for credentials that should outlive any given infra deploy.

**Current state (as of this session), not a design decision — just status:** only `ANTHROPIC_API_KEY`, `SUPABASE_URL`, and `SUPABASE_SECRET_KEY` are actually created. `OPENAI_API_KEY` and `LANGCHAIN_API_KEY` are deferred until the features that need them (embeddings, LangSmith tracing) are implemented — commented out in `main.py`'s fetch loop with a `TODO` marker so the Lambda doesn't crash trying to fetch secrets that don't exist yet.

---

## Candidate ADR: CI/CD — deferred to a follow-up

**Decision:** deploys are run locally by hand (`cdk deploy` from a developer machine) for now. GitHub Actions (building the image in CI, pushing to ECR, running `cdk deploy`, likely via GitHub's OIDC provider assuming an IAM role rather than long-lived AWS keys as secrets) is planned but deliberately not done yet.

**Why:** first-time CDK learning curve was already a variable being managed; adding CI/CD + GitHub OIDC configuration at the same time would have compounded it. The plan is to get comfortable with the stack running locally first, then layer CI on top — the CDK code itself barely changes (the workflow just runs the same `cdk deploy`), so this isn't expected to require rework, just addition.

**Also noted, unresolved:** how to coordinate backend (AWS) and frontend (Vercel) deploys from the same push. Vercel's own git integration deploys independently by default; if strict ordering is ever wanted (e.g., don't deploy frontend until backend is confirmed healthy), a GitHub Actions step could call a Vercel Deploy Hook after the backend deploy succeeds — not needed today since they're currently decoupled.

---

## Other deferred items mentioned, not yet acted on

- **Lambda Web Adapter** (for real Python response streaming on Function URLs — `chat.py`'s `/chat-message` already returns a `StreamingResponse`, but Function URLs only stream natively for the Node.js runtime; Python needs this extension layered in). Explicitly deprioritized — not a current concern, but should not be forgotten when streaming UX becomes a priority.
- **CORS origins** are a static allowlist in `backend/app/main.py` (`CORSMiddleware`), currently `http://localhost:3000` + the Vercel production domain. Vercel preview-deployment URLs (unique per branch/PR) are not covered — would need `allow_origin_regex` instead of a static list if preview-deployment testing against the real backend is ever wanted.
