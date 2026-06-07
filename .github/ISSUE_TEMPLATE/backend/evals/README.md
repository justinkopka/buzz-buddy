# BuzzBuddy Eval Framework

## Overview

BuzzBuddy's evaluation framework is the measurement system for AI quality
across the agent's reasoning, retrieval, and tool-use behaviors. Evals
provide the feedback loop that turns prompt and architecture changes from
guesses into measured improvements.

This document captures the design of the eval system. The runner itself
will be built in Sprint 7. Seed test cases drafted in Sprint 0 establish
the format and rigor standard for the broader suite.

## Why Evals Matter to This Project

Modern AI engineering separates hobby projects from production work via
measurement. Without evals, every prompt change is a guess; with them,
changes become testable hypotheses. For BuzzBuddy specifically, evals
serve four purposes:

1. **System quality measurement** — knowing if changes make things
   better or worse
2. **Regression prevention** — catching when a change breaks something
   previously working
3. **Project metrics** — concrete data ("accuracy improved from X% to Y%")
   tracked over the project's lifecycle
4. **Engineering rigor demonstration** — eval design and methodology
   serve as evidence of senior-level AI engineering practice

## Categories

The eval suite is organized into ten categories of agent behavior, each
testing a distinct dimension of quality.

| Category | Description | Programmatic | LLM-Judge | Manual |
|---|---|---|---|---|
| Decision Support | Core "I'm at a store, here are options" flow | High | High | Periodic |
| Bottle Knowledge Accuracy | Does the system get bottle facts right | High | Light | New cases only |
| Hallucination Resistance | Does it admit ignorance or invent facts | High* | High | New cases only |
| Preference Application | Does it actually use stated preferences | High | High | New cases only |
| Collection Awareness | Does it avoid duplicates, consider gaps | High | Medium | New cases only |
| Budget/Constraints | Does it respect explicit user constraints | High | Medium | New cases only |
| Reasoning Quality | Is the explanation clear and well-structured | Light | High | Heaviest |
| Edge Cases | Unknown bottles, ambiguous queries, conflicts | Medium | High | New cases only |
| Tool Use Correctness | Right tools, right order, right parameters | High | None | New cases only |
| Conversational Memory | Use of prior conversation context | Medium | High | New cases only |

*Programmatic for "known unknown" cases (bottles known to not be in KB);
LLM-judge for "KB-resident subtle" cases (faithfulness evaluation).

### On the Constraint Application Pattern

Preference Application, Collection Awareness, and Budget/Constraints
share a structural pattern: *"the user has stated/inferred X about
themselves; did the recommendation honor X, and did the reasoning
explicitly cite X?"* These three categories use a shared grader template
parameterized by constraint type, while remaining distinct categories
for test case organization.

## Grading Methodology

Three types of graders are used across the suite, chosen per category
and per case based on what produces the most reliable signal.

### Programmatic Graders

Deterministic Python checks. Fast, free, perfectly reliable. Used for:

- Checking that a recommendation matches an expected bottle from a set
- Verifying forbidden bottles aren't recommended
- Confirming budget compliance with optional flagging
- Validating tool call sequences and parameters
- Verifying ownership-overlap avoidance
- Detecting confident factual claims about known-unknown entities

Programmatic graders are the first line of defense and the cheapest
to run. Many failure modes can be caught entirely with deterministic
logic — for example, "agent recommended a bottle the user already owns"
is a binary check requiring no judgment.

### LLM-as-Judge Graders

A separate LLM call evaluates the response against a rubric. Used for:

- Checking that reasoning cites expected factors
- Detecting subtle hallucination in otherwise correct responses
- Evaluating reasoning quality and coherence
- Assessing ambiguity handling and clarification behavior
- Judging whether intermediate uncertainty was signaled appropriately

LLM-as-judge is used for evaluations requiring judgment that resists
deterministic checks. Each judge invocation uses a tightly-scoped prompt
focused on a single evaluation dimension to minimize judgment variance.

### Manual Review

Human (developer) inspection of agent outputs. Used minimally and
strategically:

- Calibrating new LLM-as-judge graders when they're first introduced
- Spot-checking outputs when new test cases are added to the suite
- Investigating cases flagged by anomaly detection (see below)
- Periodic deep review of high-priority categories (Decision Support,
  Reasoning Quality)

Manual review is intentionally limited because it doesn't scale.
The system is designed to surface specifically the cases that warrant
human attention, rather than requiring routine review of everything.

## Test Case Structure

Test cases are stored as individual YAML files in
`backend/evals/cases/<category>/<id>.yaml`. Each case captures:

- **Identity**: `id`, `category`, optional `variant`
- **Status**: `active` or `template` (templates are not yet executable
  pending implementation work)
- **Priority**: `p0` through `p3` for selective running
- **Tags**: Cross-cutting labels for filtering
- **Setup**: Simulated user state (collection, preferences, history)
  and optional KB assertions
- **Query**: The user message being tested
- **Expected**: Required and optional response characteristics
- **Graders**: One or more graders with type, check, and parameters
- **Failure modes to detect**: Documentation of what bugs this case
  is designed to catch

The schema grew naturally as seed cases revealed needs. New fields can
be added as future cases require, with the runner ignoring unknown
fields gracefully.

### Status: Active vs. Template

Some test cases are **templates** rather than executable cases. These
capture the structure and intent of a case before the underlying
system is fully implemented — for example, tool-use cases drafted
before the agent and its tools exist. Templates are excluded from
automated runs but preserved in the repository as documentation of
intended evaluation behavior.

When the dependency is satisfied (e.g., the agent and its tools are
built), the template is concretized into one or more executable cases
that match the actual implementation.

### Joint Grading

Some failure modes cannot be detected by examining the recommendation
in isolation or the reasoning in isolation — they require evaluating
the recommendation *jointly with* the reasoning. The clearest example:

> An agent that recommends a $90 bottle when the user has stated a
> $50 budget is acceptable *if* the reasoning explicitly flags the
> budget violation, and a failure *if* it does so silently.

The framework supports joint grading via grader configurations like
`budget_respected_or_flagged` that consider both the recommendation
and the reasoning trace together. This is intentional and reflects how
good recommendations actually work in practice.

## Runner Architecture Requirements

The eval runner (to be built in Sprint 7) must satisfy several
architectural constraints that emerged during seed case design:

1. **Full trace capture, not just final response.** Graders may need
   access to intermediate signals: retrieved KB chunks, tool calls
   and their arguments, tool results, and reasoning traces. The runner
   captures this via LangSmith integration and exposes it to graders.

2. **Setup-time invariant verification.** Test cases declare assumptions
   about the KB (e.g., "this bottle must not exist," "this bottle must
   exist with these fields"). The runner verifies these before
   executing the case and flags violations as test infrastructure
   failures rather than scoring them as agent failures.

3. **Per-case metadata capture.** Every run records timestamp, git
   commit hash, agent version, prompt template hashes, model used,
   and KB version. This metadata enables cross-run comparison and
   regression tracking without requiring external SaaS coupling.

4. **Pluggable grader system.** Programmatic graders are Python
   functions. LLM-as-judge graders are configurations specifying
   prompt, model, and score dimensions. New grader types can be added
   without touching the runner.

5. **Multiple results destinations.** Results are written to:
   - `docs/metrics/eval-history.md` (human-readable, version-controlled)
   - Structured JSON files per run (programmatic comparison)
   - LangSmith (visualization, trace comparison)

6. **Pytest integration for unified release flow.** The runner can be
   invoked via `pytest backend/evals/` so it integrates with the
   standard release check command alongside deterministic tests.

## Anomaly Detection (Planned)

To minimize routine manual review while preserving quality signal,
the runner will support automated anomaly flagging:

### Statistical Regression Flagging

For each test case, the runner tracks rolling pass rate over recent
runs. When a case's current pass rate drops significantly from its
historical baseline (e.g., a case that's passed 95% of the time
suddenly failing every run), the case is flagged in the run report
for manual investigation. This catches regressions that wouldn't
appear in aggregate metrics but indicate genuine quality drift in
specific scenarios.

### LLM-Assisted Outlier Analysis

Periodically, the eval results history is fed to an LLM with a
prompt to identify suspicious patterns — categories where pass rates
have drifted, latency regressions, judge score drift, etc. This
catches unknown unknowns that statistical methods miss.

Both features are planned for Sprint 7+ as enhancements to the base
eval runner.

## File Layout

    backend/evals/
    ├── cases/                          # Test case YAML files
    │   ├── decision-support/
    │   ├── constraint-application/
    │   ├── hallucination-resistance/
    │   ├── edge-cases/
    │   ├── tool-use/
    │   └── (additional categories as needed)
    ├── graders/                        # Grader implementations (Sprint 7)
    │   ├── programmatic/
    │   └── llm_judge/
    ├── runner.py                       # Main eval runner (Sprint 7)
    └── test_eval_suite.py              # Pytest wrapper (Sprint 7)

    docs/evals/
    ├── README.md                       # This document
    └── (additional design docs as needed)

    docs/metrics/
    └── eval-history.md                 # Run-over-run results summary

## Current State

As of the end of Sprint 0:

- Eval design completed
- Six seed test cases drafted establishing the format and rigor
  standard (DS-001, CA-001/002/003, HR-001/002, EC-001, TU-001)
- Runner and graders to be implemented in Sprint 7
- Seed cases serve as informal sanity checks during Sprints 1-6

## Future Work

- Expand to 30-50 test cases across categories in Sprint 7
- Build runner with all architecture requirements above
- Implement anomaly detection features
- Concretize tool-use template cases once agent and tools are built
  (post-Sprint 4)
- Establish per-release eval thresholds for CI gating