# ADR-0004: Agent Framework Approach (Custom Loop + Selective LangChain)

**Status:** Accepted
**Date:** 2026-06-04

## Context

Needed an architecture for the agent's core reasoning/tool-use loop: build directly on the LLM provider's native tool-use API, adopt an existing agent framework wholesale, or some deliberate split between the two. This decision is specifically about the runtime, request-serving chat loop — the path a live user request travels.

## Decision

A custom agent loop for the core, request-serving reasoning/tool-use flow, built directly on Claude's native tool-use API — not a LangChain agent, and not a third-party orchestration framework. LangChain is used selectively, only where it's genuinely load-bearing: document loaders and text splitters in the offline knowledge-base ingestion pipeline (see ADR-0006), and LangSmith — a separate product from the LangChain framework itself — for observability (see ADR-0007). This decision governs the runtime chat loop specifically; knowledge base curation is a separate, offline system with different constraints and isn't bound by this reasoning.

## Alternatives Considered

- **Full LangChain agent framework** — build the core loop on LangChain's agent/executor abstractions rather than the raw Claude API.
- **No LangChain at all** — the initial position, later revised once the trade-off was weighed more carefully.
- **LangGraph now**, rather than deferring it — considered and pushed to a later phase.

## Reasoning

Full LangChain for the core loop was rejected on technical grounds, sharpened by weighing it against what v1 actually needs: the request-serving loop only requires a handful of tools and no complex branching, cycles, or multi-agent coordination — meaning even a hand-rolled version with proper retry and error handling is realistically on the order of 100–150 lines. LangChain's real differentiating value (LangGraph's more specifically) — state machines, conditional branching, multi-agent delegation — solves a problem this loop doesn't have yet. Simplicity is also valuable on its own terms here, not just as a side effect of avoiding dependency risk: a small, linear loop is easier to read, easier to reason about, and easier to pick back up and modify quickly, precisely because it doesn't require learning a framework's abstractions before understanding what the code actually does. That only holds because the current user-interaction loop is genuinely simple — a handful of tools, no branching, no multi-agent coordination — so there's no complexity being hidden or mismanaged by keeping it flat; LangChain or LangGraph's abstraction has no problem to solve yet, and would add a layer to read through rather than remove one. Taking on a framework dependency to save a modest amount of loop code, without using the features that would justify the trade-off, isn't a good deal — especially given LangChain's documented history of breaking changes across major version boundaries (0.0.x → 0.1 → 0.2 → 0.3, package splits), and the fact that a framework's abstraction layer (agent executors, callback managers, memory objects) sits between the code and the actual API request/response exactly when debugging matters most. With the raw loop, there's one layer: the loop code itself and Anthropic's documented API — nowhere for a bug to hide. (Anthropic's SDK has also introduced a higher-level "tool runner" helper for this exact request-execute-loop pattern, which could shrink the hand-rolled portion further without pulling in a third-party framework — worth evaluating against current Anthropic documentation at implementation time rather than committing to raw dispatch code prematurely.)

The "no LangChain at all" position was revised because LangChain's ecosystem shows up in real, load-bearing places elsewhere in the project — not the runtime loop, but the knowledge base curation pipeline, which is a fundamentally different system. Curation is offline and asynchronous, off any user's critical path, which means it can tolerate more experimentation and even justify agentic curation strategies (an agent that scrapes distillery sites, cross-references community sources, reasons about what's worth keeping) without contradicting the reasoning above — that reasoning is specifically about the request-serving loop, not about agentic techniques in general. Document loaders and text splitters are genuinely useful there: commodity, well-solved problems where LangChain's implementations are good and reimplementing them by hand has no corresponding payoff, unlike the agent loop itself, which is exactly the part worth owning directly.

There's also a real difference in what the work demonstrates: describing the runtime agent as a thin wrapper around a framework's agent executor is a materially weaker showcase of engineering depth than describing it as designing the orchestration — tool-use dispatch, retry logic, error handling, trace logging — directly. The custom loop makes the stronger description true, while LangChain's real presence in ingestion and LangSmith's presence in observability still give genuine, honest exposure to that ecosystem rather than window dressing.

I also have prior experience with Google's Agent Development Kit (ADK), which is complementary here — it demonstrates general fluency with agent frameworks as a category, even though ADK is less widely recognized than LangChain specifically.

## Consequences

- **Not yet implemented.** `backend/app/api/routes/chat.py` currently makes a single direct call to `anthropic.AsyncAnthropic().messages.stream()` with no tool-use, no multi-step loop, and no retry/error-handling logic. This ADR documents the intended architecture; the custom loop itself has not been built yet.
- Owning the agent loop directly means owning all retry logic, error handling, and trace logging around tool-use — no upstream framework absorbing bug fixes or improvements to that orchestration code. Realistically ~100–150 lines for the core dispatch loop; Anthropic's SDK-provided tool-runner helper, if adopted, could shrink this further.
- Because the tools themselves (`search_knowledge_base` and future tools) are plain, independent Python functions regardless of orchestrator, migrating to LangGraph later is low-regret: LangGraph's nodes follow the same call-model/execute-tools/route pattern, just with more structure layered on. Adopting it later means wrapping existing tools in a more structured orchestrator, not rewriting them.
- Two separate dependency surfaces to track instead of one: Anthropic's SDK for the runtime loop, and LangChain's document-loader/text-splitter APIs for ingestion — a breaking change in either needs separate attention. LangSmith is a third, independent surface (its own SDK, usable without LangChain-the-framework).
- Sets up a deliberate future migration: LangGraph is the planned orchestration layer once multi-agent coordination is genuinely needed (v1.5+) — building the custom loop first and adopting a framework only once complexity actually warrants it is a deliberate sequencing choice, not an oversight to fix later.
- **Scope boundary:** this decision governs the runtime, request-serving chat loop only. Knowledge base curation (ADR-0006) is a separate offline system and may use LangChain/LangGraph agentic techniques more liberally without contradicting this ADR.

## References

- `backend/app/api/routes/chat.py` — current (pre-agent-loop) implementation
- CLAUDE.md — "Agent Architecture" section, custom loop + native tool use APIs already documented as the standing convention
- ADR-0005 (embedding strategy), ADR-0006 (KB curation), ADR-0007 (observability) — related decisions referenced above
