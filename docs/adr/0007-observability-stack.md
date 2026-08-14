# ADR-0007: Observability Stack (LangSmith + CloudWatch + loguru)

**Status:** Accepted
**Date:** 2026-06-04

## Context

Needed an observability strategy covering three distinct concerns: LLM/agent-specific behavior (traces, tool calls, prompts and completions), AWS infrastructure health, and general application-level errors and logging that fall entirely outside LLM calls.

## Decision

Three separate layers, not one unified tool: LangSmith for LLM/agent tracing, AWS CloudWatch for infrastructure, and loguru for application-level Python logging, configured to emit structured JSON that CloudWatch Logs Insights can query.

## Alternatives Considered

- **Datadog** — full observability platform unifying traces, infra, and logs.
- **Helicone** — LLM-focused, but positioned more as a gateway/proxy than an observability tool.
- **Langfuse** — LangSmith's most direct competitor for LLM tracing specifically.
- **structlog** — Python structured logging alternative to loguru.

## Reasoning

The reason for three layers instead of one unified tool: observability tooling only covers what you actually instrument. An LLM tracing tool like LangSmith only sees LLM calls — it has no visibility into, say, an unhandled exception in a FastAPI route that never touches a model, or a Lambda timeout. Relying on an LLM-focused tool alone would leave real classes of failure invisible. That gap is what drove adopting a third, general-purpose logging layer rather than assuming LangSmith or CloudWatch alone would cover everything.

LangSmith over Langfuse came down to synergy with the LangChain-ecosystem components already used elsewhere in the stack (document loaders and text splitters in KB ingestion, per ADR-0004/ADR-0006) — LangSmith is built by the same team and integrates most naturally there. This is a soft preference, not a hard dependency: both tools work fine with non-LangChain code via their own SDKs, and LangSmith's `@traceable` decorator specifically traces plain Python functions with no LangChain involvement at all.

CloudWatch wasn't really a contested choice — the app already runs on Lambda, and CloudWatch is where Lambda's execution logs land by default with zero additional setup. Introducing a separate infra-monitoring tool would duplicate something already available for free.

loguru over structlog was a deliberate simplicity call: less configuration ceremony to get structured output working, and its JSON output integrates directly with CloudWatch Logs Insights, which expects structured log lines it can query and filter — giving queryable application logs without a heavier logging setup.

Cost detail worth capturing precisely: LangSmith's free tier is 5,000 traces/month, and that quota isn't only consumed by production traffic — eval runs produce traces too. Per the eval framework's design (`backend/evals/README.md`), a 100-case suite run three times a week alone accounts for roughly 1,200 traces/month, a meaningful chunk of the free tier before any real user traffic is counted. The paid tier is $39/mo past that. The documented fallback if cost becomes a real problem is self-hosting Langfuse (~$5–10/mo in compute) — a genuine planned exit path, not a hypothetical, made credible specifically because the LangSmith preference above is soft rather than architecturally locked in.

Datadog was rejected as expensive and overkill — its value proposition is unifying observability across much larger, more complex systems than a single Lambda function and a Next.js frontend. Helicone was rejected because it's positioned more as an LLM gateway/proxy (routing, caching) than as an observability/tracing tool — it doesn't match the actual need as precisely as LangSmith does.

## Consequences

- **CloudWatch is the only layer already partially live** — the Log Group exists (`infrastructure/lib/buzzbuddy-stack.ts`) and Lambda's default execution logs flow there, but structured application logging and Logs Insights integration aren't set up yet.
- **LangSmith tracing and loguru are both not yet implemented** — no matching dependencies in `backend/pyproject.toml`, no tracing decorators or structured logging calls anywhere in the codebase.
- Eval runs and production traffic share the same LangSmith trace quota — as the eval suite grows toward its planned 30–50 case target, trace consumption from evals alone grows too, worth monitoring rather than assuming the free tier is solely a production-traffic concern.
- Because the LangSmith preference is soft (not deeply coupled via LangChain-specific integration), migrating to self-hosted Langfuse later is a real, low-friction option if cost becomes a problem — not just a theoretical alternative.
- Three separate tools means three separate places to look when debugging — a real coordination cost, accepted because each layer covers a distinct failure mode the others don't.

## References

- CLAUDE.md — tech stack table, observability row already documents this decision
- `infrastructure/lib/buzzbuddy-stack.ts` — CloudWatch Log Group, the one piece already live
- `backend/evals/README.md` — eval framework design, source of the trace-volume math
- `.env.example` — `LANGCHAIN_API_KEY` placeholder
