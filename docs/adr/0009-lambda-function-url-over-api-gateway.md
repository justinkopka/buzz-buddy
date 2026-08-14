# ADR-0009: Lambda Function URL over AWS API Gateway

**Status:** Accepted
**Date:** 2026-08-09

## Context

Needed to choose how the backend Lambda is invoked over the network, with streaming chat UX as a primary constraint on the choice.

## Decision

Lambda Function URL, with `InvokeMode: RESPONSE_STREAM` and `AuthType: NONE`, rather than API Gateway.

## Alternatives Considered

- **API Gateway (REST or HTTP API)** — the standard, more feature-rich front door for Lambda, rejected specifically for this use case.

## Reasoning

API Gateway has a hard 30-second integration timeout, and — separately, more fundamentally — buffers the entire response before returning it to the client regardless of how fast the Lambda runs. For a streaming chat UX, that's disqualifying on its own; it's not just a timeout risk, it means no response ever arrives incrementally through API Gateway at all. Function URLs support the Lambda function's full timeout (up to 15 minutes) and, critically, support `RESPONSE_STREAM` invoke mode, which streams the response back as it's produced.

The trade-off accepted: losing API Gateway's built-in throttling and native auth integration (Cognito authorizers, API keys, usage plans).

Mitigation for losing built-in auth: Supabase JWT validation inside the Lambda handler becomes the real auth boundary — the frontend sends the access token as a Bearer header, and the handler verifies it against Supabase's JWKS before doing anything else. `AuthType: NONE` at the Function URL level is defensible specifically because every request is rejected without a valid token — the security boundary moves into application code, it doesn't disappear.

Mitigation for losing built-in throttling: reserved concurrency caps blast radius, since without API Gateway there's no request throttling and a fully public Function URL means anyone can trigger Lambda invocations (and associated cost) without a valid token. The auth check happens before any Anthropic call, so this is invocation-volume exposure, not per-request LLM spend — but it's still real cost and a way to exhaust the account's concurrency pool without a cap in place. Set to 10 — comfortably covers realistic usage at this stage while bounding worst-case abuse cost, and trivial to raise later as real traffic patterns emerge. Per-user rate limiting (distinguishing one abusive authenticated user from normal traffic) is a related but separate concern, tracked as its own follow-up rather than covered by this decision.

CloudFront with Origin Access Control in front, to hide the raw Function URL, is a future option — explicitly polish, not a prerequisite for this decision.

## Consequences

- **The deployed version isn't actually streaming yet — a known drawback, not an oversight.** `infrastructure/lib/buzzbuddy-stack.ts` doesn't set `invokeMode` on the Function URL (defaults to `BUFFERED`), and Mangum — the ASGI adapter currently wrapping the FastAPI app — has no code path for Lambda's streaming response protocol regardless of invoke mode. The fix is scoped and not expected to be a large effort: swap Mangum for the Lambda Web Adapter, which runs the app as a persistent Uvicorn server inside the container and bridges its native HTTP streaming to Lambda's Runtime API. `chat.py`'s existing `StreamingResponse` code doesn't need to change — only the container's runtime model and `Dockerfile` CMD do. Tracked as a near-term follow-up, not deferred indefinitely.
- **Reserved concurrency is configured at 10.** Caps both the function's worst-case cost/blast-radius under abuse and protects the rest of the AWS account's concurrency pool from being consumed by this function. Does not address per-user abuse (a single authenticated user could still consume the whole reserved slice) — that's tracked as a separate GitHub issue for future app-level rate limiting, not part of this decision.
- **Lambda timeout raised to 60 seconds** (from an initial 30s that coincidentally matched the exact API Gateway ceiling this decision was meant to escape) — still well under the 15-minute Lambda maximum, set conservatively since responses aren't expected to ever approach that duration, with room to raise further if needed.
- `AuthType: NONE` + Supabase JWT-in-handler *is* correctly implemented as designed (`backend/app/auth.py`, router-level dependency in `chat.py`) — this part of the decision matches reality.
- CloudFront/OAC remains undone, consistent with being explicitly deferred rather than required.

## References

- `infrastructure/lib/buzzbuddy-stack.ts` — current Function URL, timeout, and reserved concurrency configuration
- `infrastructure/README.md` — "Not yet done" section, already tracks the Lambda Web Adapter/streaming gap
- `backend/app/auth.py`, `backend/app/api/routes/chat.py` — the actual auth boundary this decision relies on
- ADR-0002 — backend stack decision, notes the container-image packaging this Lambda uses
