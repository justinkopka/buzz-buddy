# ADR-0005: Embedding Strategy (Multi-Resolution, pgvector)

**Status:** Accepted
**Date:** 2026-06-04
**Revised:** 2026-08-15 — embedding model changed from `text-embedding-3-small` to `text-embedding-3-large` at `dimensions=1536`
**Revised:** 2026-08-17 — retrieval sequencing superseded by ADR-0012; all three embedding types are queried from the first release

## Context

Needed an embedding strategy for the knowledge base to support RAG-based bottle retrieval: how many embeddings per bottle, at what granularity, and how vector retrieval combines with keyword-based search.

## Decision

Multi-resolution embeddings — three per bottle (`full_profile`, `tasting_notes`, `community_sentiment`), generated from programmatically-produced natural-language source text rather than serialized structured data, stored in pgvector. Retrieval combines this with BM25 full-text search via Postgres, fused via Reciprocal Rank Fusion, then reranked with a cross-encoder. Sequencing (**superseded by ADR-0012**): all three embedding types are generated from day one, which stands. The original plan then shipped retrieval against `full_profile` only, layering in query-intent-based type-selection later; retrieval instead queries all three types from the first release and represents each product by its best-matching vector, which removes the need for the intent classifier entirely.

## Alternatives Considered

- **Option A: Single whole-bottle embedding** — one embedding per bottle covering everything.
- **Option B: Field-level embeddings** — a separate embedding per individual structured field.

## Reasoning

Option A conflates distinct query intents into one representation — "something sweet and not too oaky" and "similar to Henry McKenna BIB" are fundamentally different kinds of questions (flavor-profile matching vs. overall-similarity matching), and blending them into a single embedding loses precision on both. Option B over-fragments: embedding a lone structured field in isolation strips the natural-language context that makes embeddings work well in the first place, for a storage/generation cost multiplier that doesn't buy a corresponding quality improvement.

Multi-resolution (C) addresses this directly — `tasting_notes` embeddings serve flavor-profile queries, `full_profile` serves similarity/overview queries, `community_sentiment` captures reception/reputation separately from either. The cost argument supports doing this without hesitation: multi-resolution adds roughly 1.5–2 days of engineering effort over the project's lifetime, not weeks, and storage is trivial — 1536 floats × 4 bytes ≈ 6KB per embedding, ≈9MB raw for 500 bottles × 3 embeddings, ≈14MB with HNSW index overhead. At this scale, the decision should be made on retrieval quality, not cost.

The sequencing call — generate all three from day one, but only wire retrieval logic against `full_profile` initially — trades a small, front-loaded cost (generation is nearly free at ingestion time) against a much larger deferred one: retrofitting embeddings later would mean a backfill migration across every existing bottle in the KB. Paying the trivial cost up front avoids that entirely.

A non-obvious but important detail: embedding source text must be natural language, not serialized structured data. Embeddings perform markedly worse on `{"proof": 100, "age": 10}` than on "Eagle Rare 10 Year is a 90-proof Kentucky straight bourbon aged ten years…" — the ingestion pipeline needs a step that programmatically generates natural-language descriptions from structured fields specifically to produce good embeddings; embedding the raw record directly would degrade retrieval quality.

On hybrid retrieval: dense vector search alone misses exact-match-sensitive queries (specific bottle names, exact proof numbers) that lexical search handles natively and vector search can dilute. Combining BM25 (via Postgres full-text search — reinforcing ADR-0001's single-database architecture rather than standing up a separate search service) with dense vector search, fused via Reciprocal Rank Fusion, then reranking the fused shortlist with a cross-encoder, is a standard, well-established hybrid RAG pattern that captures both lexical precision and semantic recall without the cost of running an expensive per-pair reranker over the full candidate set.

On the embedding model: OpenAI's `text-embedding-3-large`, requested at `dimensions=1536` rather than its native 3072. This revises the original choice of `text-embedding-3-small`, which was made on cost grounds before the cost was actually quantified.

Both v3 models accept a `dimensions` parameter that shortens the returned vector while preserving its concept-representing properties, so model choice and column width are independent. `vector(1536)` is fixed by the schema; the model producing those 1536 numbers is not, and switching between the two is a re-embedding script with no migration.

That leaves quality against price. OpenAI publishes MTEB averages of 62.3% for `-3-small` and 64.6% for `-3-large` at full width; what they do not publish is a figure for `-3-large` truncated to 1536, so the retained portion of that 2.3-point gap is an inference, not a documented number. (Their stated truncation benchmark — `-3-large` at 256 dimensions outperforming `-3-ada-002` at 1536 — compares against the previous-generation model, not against `-3-small`.) Halving 3072 is a far milder cut than that example, so most of the gap should survive, but the honest position is "probably better by an unmeasured amount."

Price is where the decision resolves. Generation costs $0.02/million tokens for `-3-small` against $0.13/million for `-3-large` — a real 6.5x, applied to a corpus of roughly 1.1M tokens (~1,500 products x 3 embeddings). That is $0.02 versus $0.14 to embed the entire knowledge base, and roughly four cents apart across ten thousand user searches. Storage and query cost are identical, since both produce 1536-wide vectors and nearest-neighbour search is Postgres arithmetic that is indifferent to which model generated them. A 6.5x multiplier on amounts that round to zero is not a tradeoff worth optimizing, so the probable quality gain wins by default.

## Consequences

- **Partially implemented.** The pgvector schema exists (`product_embeddings`, `vector(1536)`, applied to production), and embedding generation is built: `backend/app/embeddings.py` produces all three types from templated source text and syncs them on every product save from the admin routes. Hybrid retrieval is not built — its design is ADR-0012. Reranking is not built and is deferred there with a stated trigger; `backend/pyproject.toml` carries no `cohere` or reranking dependencies.
- The `dimensions` parameter is what keeps the model choice reversible. Requesting a width other than 1536 would break inserts against the existing column, so any future model change must either request 1536 or come with a schema migration and a full re-embed.
- Reinforces ADR-0001's single-Postgres-database architecture — hybrid retrieval (BM25 + vector) both live in Postgres rather than introducing a separate lexical search service like Elasticsearch/OpenSearch.
- Commits the ingestion pipeline to an extra transformation step: generating natural-language descriptions from structured bottle data before embedding, not embedding raw records directly.
- **Superseded by ADR-0012.** This originally read that `tasting_notes` and `community_sentiment` would sit stored but unused until query-intent-based type-selection was built as a follow-up phase. Retrieval instead takes the `MIN` distance across all three types per product, so every vector generated is used from the first query and that follow-up phase is never needed. The decision to generate all three from day one is unchanged — it is precisely what makes this possible without a backfill.
- **Open question:** cross-encoder reranker choice (Cohere rerank-3 vs. a BGE reranker) isn't finalized — revisit when this is actually implemented.

## References

- CLAUDE.md — tech stack table, OpenAI for embeddings
- ADR-0001 — single-Postgres architecture this decision builds on
