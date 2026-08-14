# ADR-0001: Database and Auth (Supabase, Postgres + pgvector)

**Status:** Accepted
**Date:** 2026-06-04

## Context

BuzzBuddy needs both relational data (users, conversations, bottles, collections, preferences) and vector embeddings for RAG-based bottle recommendations. The dominant query pattern in the product is inherently hybrid — semantic similarity search combined with relational filters (ownership, budget, preference weighting) as a single logical operation, not two independent lookups stitched together.

## Decision

Use a single Postgres database (via Supabase) with the pgvector extension for both relational data and vector embeddings, and adopt Supabase Auth for authentication rather than a standalone auth provider.

## Alternatives Considered

- **Architecture B: Postgres + dedicated vector DB** (e.g., Pinecone, Weaviate) — relational data in Postgres, embeddings in a purpose-built vector store.
- **Architecture C: DynamoDB + dedicated vector DB** — fully NoSQL relational layer paired with a separate vector store.
- **Postgres hosting:** RDS, Aurora Serverless v2, Neon, alongside Supabase.
- **Auth:** Clerk (best standalone DX, free to 10k MAU), AWS Cognito (cheaper at scale, more AWS-native, more setup friction).

## Reasoning

The decisive argument is architectural, not operational: the core query — "find bottles semantically similar to X, excluding ones the user owns, under budget Y, weighted by preference" — is one SQL query when embeddings live next to relational data (Architecture A). In B or C, the same query becomes query-the-vector-store, query-the-relational-store, join in application code, re-rank — more code, more latency, more failure surface, and this is the main path, not an edge case.

pgvector is production-ready (HNSW indexing) and handles far more scale than this project needs — v1's KB is roughly 1,500 vectors (3 per bottle × ~500 bottles), nowhere near where pgvector's ceiling would matter.

Operational simplicity mattered as a hard solo-developer constraint: every extra service is another account, dashboard, failure mode, and cost line to own. Choosing pgvector over a dedicated vector DB is also the more interesting engineering story — it demonstrates judgment about when *not* to add infrastructure, rather than reflexively reaching for a trendy vector store.

On hosting: Supabase won over RDS/Aurora Serverless v2/Neon on setup time (~30 minutes vs. several hours to hand-roll RDS + pooling + auth), built-in PgBouncer connection pooling (directly defuses the classic Lambda-exhausts-Postgres-connections failure mode), bundled auth removing a separate integration entirely, and a free tier (500MB, 50k MAU) that covers v1's entire expected lifetime.

Bundling auth with Supabase rather than Clerk or Cognito eliminated a whole separate integration — one fewer account, one fewer credential/webhook setup, one fewer service boundary between "who is this user" and "what data can they see."

## Consequences

- The stack now spans multiple managed services (AWS, Supabase, Vercel) rather than a single vendor — more moving parts to operate day-to-day than an all-AWS approach would have, offset by each individual piece being faster to set up and simpler to maintain on its own.
- Accepted, documented risk: if the vector workload ever grows well beyond pgvector's comfort zone (considered unlikely at this project's scale), a migration to a dedicated vector store would be required.
- Commits the project to Postgres row-level security as the primary data-isolation mechanism, not application-code-only access control — needs to be in place as soon as real user-data tables exist. **Not yet applicable** — no DB schema exists in the repo as of this ADR.
- Ties authentication tightly to Supabase specifically; switching auth providers later means also touching the database relationship, not just swapping a standalone service.

## References

- `backend/app/auth.py` — Supabase JWT (JWKS) validation; confirms this decision as implemented
- `.env.example` — `SUPABASE_URL`, `SUPABASE_SECRET_KEY`
