# Architectural Decision Records

Index of ADRs documenting major technical decisions for BuzzBuddy — what
was decided, why, and what alternatives were considered. Use
`_template.md` as the starting point for a new one.

## Foundational ADRs

| # | Title | Status |
|---|---|---|
| [0001](0001-database-and-auth.md) | Database and auth choice (Supabase) | Accepted |
| [0002](0002-backend-stack.md) | Backend stack (Python/FastAPI on Lambda) | Accepted |
| [0003](0003-frontend-stack.md) | Frontend stack (Next.js PWA on Vercel) | Accepted |
| [0004](0004-agent-framework-approach.md) | Agent framework approach (Custom loop + selective LangChain) | Accepted |
| [0005](0005-embedding-strategy.md) | Embedding strategy (Multi-resolution with pgvector) | Accepted |
| [0006](0006-knowledge-base-curation.md) | Knowledge base curation approach (Hybrid manual + LLM-assisted) | Accepted |
| [0007](0007-observability-stack.md) | Observability stack (LangSmith + CloudWatch + loguru) | Accepted |
| [0008](0008-repo-structure-and-tracking.md) | Repo structure and tracking approach | Accepted |
| [0009](0009-lambda-function-url-over-api-gateway.md) | Lambda Function URL over AWS API Gateway | Accepted |
| [0010](0010-eval-framework-execution.md) | Eval framework execution architecture (custom runner + LangSmith for traces only) | Accepted |
| [0011](0011-product-schema-structure.md) | Single-table multi-vertical product schema | Accepted |
| [0012](0012-hybrid-retrieval-architecture.md) | Hybrid retrieval architecture (three-arm weighted RRF) | Accepted |

`notes-infrastructure-deployment.md` in this directory has raw material
from the CDK deployment work — most directly relevant to ADR 0009, but
also covers several infrastructure topics (IaC tool choice, auth model,
rollback strategy, secrets management, CI/CD) not currently accounted
for in the list above. Worth revisiting once the foundational 9 are done
to decide if any of those warrant their own ADR.
