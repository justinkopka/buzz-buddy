# ADR-0005: Embedding Strategy (Multi-Resolution, pgvector)

**Status:** Accepted
**Date:** 2026-06-04

## Context

Needed an embedding strategy for the knowledge base to support RAG-based bottle retrieval: how many embeddings per bottle, at what granularity, and how vector retrieval combines with keyword-based search.

## Decision

Multi-resolution embeddings — three per bottle (`full_profile`, `tasting_notes`, `community_sentiment`), generated from programmatically-produced natural-language source text rather than serialized structured data, stored in pgvector. Retrieval combines this with BM25 full-text search via Postgres, fused via Reciprocal Rank Fusion, then reranked with a cross-encoder. Sequencing: generate all three embedding types from day one, but ship retrieval logic against `full_profile` only initially, layering in query-intent-based type-selection later.

## Alternatives Considered

- **Option A: Single whole-bottle embedding** — one embedding per bottle covering everything.
- **Option B: Field-level embeddings** — a separate embedding per individual structured field.

## Reasoning

Option A conflates distinct query intents into one representation — "something sweet and not too oaky" and "similar to Henry McKenna BIB" are fundamentally different kinds of questions (flavor-profile matching vs. overall-similarity matching), and blending them into a single embedding loses precision on both. Option B over-fragments: embedding a lone structured field in isolation strips the natural-language context that makes embeddings work well in the first place, for a storage/generation cost multiplier that doesn't buy a corresponding quality improvement.

Multi-resolution (C) addresses this directly — `tasting_notes` embeddings serve flavor-profile queries, `full_profile` serves similarity/overview queries, `community_sentiment` captures reception/reputation separately from either. The cost argument supports doing this without hesitation: multi-resolution adds roughly 1.5–2 days of engineering effort over the project's lifetime, not weeks, and storage is trivial — 1536 floats × 4 bytes ≈ 6KB per embedding, ≈9MB raw for 500 bottles × 3 embeddings, ≈14MB with HNSW index overhead. At this scale, the decision should be made on retrieval quality, not cost.

The sequencing call — generate all three from day one, but only wire retrieval logic against `full_profile` initially — trades a small, front-loaded cost (generation is nearly free at ingestion time) against a much larger deferred one: retrofitting embeddings later would mean a backfill migration across every existing bottle in the KB. Paying the trivial cost up front avoids that entirely.

A non-obvious but important detail: embedding source text must be natural language, not serialized structured data. Embeddings perform markedly worse on `{"proof": 100, "age": 10}` than on "Eagle Rare 10 Year is a 90-proof Kentucky straight bourbon aged ten years…" — the ingestion pipeline needs a step that programmatically generates natural-language descriptions from structured fields specifically to produce good embeddings; embedding the raw record directly would degrade retrieval quality.

On hybrid retrieval: dense vector search alone misses exact-match-sensitive queries (specific bottle names, exact proof numbers) that lexical search handles natively and vector search can dilute. Combining BM25 (via Postgres full-text search — reinforcing ADR-0001's single-database architecture rather than standing up a separate search service) with dense vector search, fused via Reciprocal Rank Fusion, then reranking the fused shortlist with a cross-encoder, is a standard, well-established hybrid RAG pattern that captures both lexical precision and semantic recall without the cost of running an expensive per-pair reranker over the full candidate set.

On the embedding provider: OpenAI's `text-embedding-3-small` (~$0.02/million tokens), consistent with the embeddings-provider choice already established in the project's tech stack.

## Consequences

- **Not yet implemented.** No embedding generation, pgvector schema, or retrieval code exists in the repo (`backend/pyproject.toml` has no `openai`, `pgvector`, `cohere`, or reranking dependencies). This ADR documents intended architecture.
- Reinforces ADR-0001's single-Postgres-database architecture — hybrid retrieval (BM25 + vector) both live in Postgres rather than introducing a separate lexical search service like Elasticsearch/OpenSearch.
- Commits the ingestion pipeline to an extra transformation step: generating natural-language descriptions from structured bottle data before embedding, not embedding raw records directly.
- Generating three embeddings per bottle from day one while only using one (`full_profile`) in retrieval initially means `tasting_notes` and `community_sentiment` sit stored but unused until query-intent-based type-selection is built as a follow-up phase — deliberate, not an oversight.
- **Open question:** cross-encoder reranker choice (Cohere rerank-3 vs. a BGE reranker) isn't finalized — revisit when this is actually implemented.

## References

- CLAUDE.md — tech stack table, OpenAI for embeddings
- ADR-0001 — single-Postgres architecture this decision builds on
