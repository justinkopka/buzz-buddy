# ADR-0002: Backend Stack (Python + FastAPI on Lambda)

**Status:** Accepted
**Date:** 2026-06-04

## Context

Needed a backend language, web framework, and compute platform for the API layer serving the agent. The choice needed to hold up both as a technically sound foundation and as a credible demonstration of AI engineering practice, given the project's dual purpose.

## Decision

Python, using FastAPI, deployed on AWS Lambda.

## Alternatives Considered

- **Node.js** — technically fine, but misaligned with the AI engineering ecosystem specifically.
- **Go** — language itself is fine, but the AI/ML library ecosystem isn't there.
- **Rust** — rejected outright; wrong tool for this kind of application-layer, library-heavy work.
- **Java** — my most professionally familiar language, but not a fit for the AI/ML ecosystem this project draws on.

## Reasoning

Python is the de facto language of AI engineering — virtually every relevant library (LLM SDKs, RAG tooling, embedding/eval frameworks) is Python-first, and job postings in the space assume Python fluency by default. Writing this project in Node would add unnecessary friction for anyone evaluating the work — an extra inferential leap ("can they actually do Python?") that a Python-first codebase avoids entirely. Go and Rust were considered and rejected quickly: Go's AI/ML ecosystem is too thin, and Rust is the wrong level of abstraction for this kind of application code. Java got a longer look than the others — it's my most familiar language professionally — but the same ecosystem argument applies: the AI engineering tooling world simply isn't built around Java, and personal comfort didn't outweigh that.

FastAPI won within Python on concrete technical merits: native async support, Pydantic-based request/response typing, and automatic OpenAPI spec generation — all of which reduce boilerplate and produce a more pleasant development experience than the alternatives.

Lambda won on cost: near-zero infrastructure spend until the app has real traffic, which matters for a project with no revenue yet. The known trade-off, flagged at decision time: Lambda's 15-minute execution ceiling could become a problem for long-running work like bulk embedding generation — the plan is to run that kind of workload locally or in a one-off container rather than inside the request-serving Lambda. (How the Lambda is actually invoked over the network — Function URL vs. API Gateway — is its own decision; see ADR-0009.)

## Consequences

- Lambda's 15-minute execution ceiling forecloses running long-running batch jobs (e.g., bulk embedding generation for the knowledge base) directly on this compute path — those need to run locally or as a separate one-off container job instead.
- **Implementation drift from the original decision:** the backend is packaged as a container image (via ECR — see `backend/Dockerfile`) rather than a traditional zip-based Lambda deployment, which wasn't an explicit Sprint 0 decision but emerged during actual implementation. This affects cold-start latency (larger images cold-start slower than small zips), requires a Docker-based build/push pipeline (see `infrastructure/`) instead of a simple zip upload, and is subject to the 10GB container image size ceiling rather than zip's 250MB unzipped limit — not a real constraint at current dependency footprint, but worth knowing the ceiling changed.
- FastAPI's automatic OpenAPI generation gives free interactive API docs (`/docs`), though in practice this surfaced its own quirks when testing bearer-token auth through the browser UI — a testing-tool limitation, not a framework or architecture flaw.

## References

- `backend/pyproject.toml` — fastapi, uvicorn, mangum, pydantic-backed dependencies
- `backend/Dockerfile` — container image packaging (the drift noted above)
- `backend/app/api/routes/chat.py` — async handlers, Pydantic request/response models in practice
