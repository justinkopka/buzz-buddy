# ADR-0010: Eval Framework Execution Architecture (Custom Runner + LangSmith for Traces Only)

**Status:** Accepted
**Date:** 2026-06-04

## Context

`backend/evals/README.md` already defines the eval framework's design — categories, grading strategies, YAML test case schema, six seed cases. What it doesn't document is how the framework actually *executes*: build a fully custom runner, or adopt LangSmith's native dataset/evaluation features (LangSmith is already the adopted observability tool per ADR-0007), or adopt a third-party eval framework built for this purpose.

## Decision

The repo is the source of truth for eval test cases and grading logic. YAML test cases live in `backend/evals/cases/`, executed by a custom Python runner (`runner.py`) with custom graders (programmatic + LLM-as-judge), wrapped by `backend/evals/test_eval_suite.py` so `pytest` runs deterministic tests and evals in one invocation for CI/release checks. LangSmith is used only for trace capture and visualization — never as the orchestrator or grading engine.

## Alternatives Considered

- **LangSmith-native evaluation** — upload test cases as a LangSmith Dataset, register graders with LangSmith, let LangSmith execute the suite and hold results in its UI.
- **Third-party eval frameworks** — DeepEval, Ragas, promptfoo.

## Reasoning

Four axes were weighed. **Source of truth was decisive:** with the custom runner, test cases are version-controlled files anyone can clone and read, and LangSmith disappearing costs nothing structurally. With LangSmith-native evaluation, cases are exportable but fundamentally live in someone else's database — eval logic as configuration in a SaaS UI rather than as code. For anyone evaluating this project's engineering, a self-built framework with YAML-driven cases, custom graders, and pytest integration demonstrates the underlying design directly, in readable code — uploading cases and graders through a SaaS UI mostly demonstrates familiarity with someone else's product instead.

**Grader flexibility** doesn't favor either option as strongly as it might seem. LangSmith's built-in and custom-via-SDK graders are genuinely capable. But the graders that actually matter here are domain-specific — "did the agent recognize this allocated bottle is worth grabbing even though it's over budget" isn't something a generic grader evaluates. Custom Python graders get written regardless of which platform runs them, so there's little marginal cost to also owning the execution layer.

**Run comparison is the one place LangSmith genuinely wins** — their side-by-side experiment comparison with per-case diffs is a strong, polished feature that a custom runner doesn't get for free. This is an acknowledged, real loss, not dismissed. The mitigation: the runner captures per-run metadata — timestamp, git commit hash, agent version, prompt template hashes, model used, KB version — stored as both a markdown summary and structured JSON, so runs stay programmatically comparable even without LangSmith's UI. This recovers most of the value, not all of it; building real cross-run comparison tooling is left as future work if it turns out to matter in practice.

**Integration effort is roughly a wash** — a custom runner is an estimated 1–2 days of work; the LangSmith-native path is less code but spends that time learning their dataset model and grader registration instead. Not a decisive factor either way.

DeepEval, Ragas, and promptfoo were considered and rejected on the same logic already established for LangChain in ADR-0004: since domain-specific graders get hand-written regardless, adopting one of these frameworks buys their built-in generic metrics (unlikely to be the primary graders actually used) at the cost of a dependency and its own configuration model to learn. Worth being precise here — these frameworks do support fully custom metrics, so it's not that they *can't* express bourbon-specific evaluation, just that doing so gets little marginal benefit from the framework once the interesting logic is custom either way.

What tipped it beyond the axes above: coupling. Eval logic living in a SaaS grader registry means a future platform migration requires rewriting testing infrastructure, not just swapping a configuration value. Keeping grading logic in the repo means LangSmith could be swapped for Langfuse or a self-hosted option later without touching eval logic at all — the same portability argument already made for observability generally in ADR-0007.

## Consequences

- **Not yet implemented.** No `runner.py`, `graders/`, `test_eval_suite.py`, or `backend/tests/` directories exist yet — confirmed empty as of this ADR. This documents intended architecture, consistent with the eval framework's broader "designed before built" status.
- The run-comparison gap versus LangSmith-native is real and only partially mitigated by metadata capture — building actual cross-run diff tooling, if ever needed, is deferred work, not solved by this decision.
- Portability is preserved: because grading logic lives in the repo rather than a SaaS registry, a future LangSmith → Langfuse (or self-hosted) migration wouldn't require rewriting eval logic — same posture as ADR-0007.
- Two distinct test surfaces going forward: deterministic tests in `backend/tests/unit/` and `backend/tests/integration/`, evals in `backend/evals/`. The pytest wrapper unifies them for a single CI invocation, but they're graded differently — evals are threshold-based (e.g., 75% of cases passing, or no regression versus the last release), not required to hit 100% the way deterministic tests are.
- LangSmith's trace budget is shared between eval runs and production traffic, per the cost analysis already in ADR-0007 — not repeated in full here.

## References

- `backend/evals/README.md` — the existing eval framework design this ADR provides the execution rationale for
- ADR-0004 — same custom-vs-framework reasoning pattern applied to DeepEval/Ragas/promptfoo
- ADR-0007 — LangSmith cost analysis and portability framing this decision builds on
- ADR-0008 — repo-as-source-of-truth reasoning this decision reinforces
