# ADR-0011: Single-Table Multi-Vertical Product Schema

**Status:** Accepted
**Date:** 2026-08-11

## Context

ADR-0001 settled the platform (Supabase Postgres with pgvector) but not the schema itself. Designing the concrete tables surfaced a structural question the platform decision didn't answer: the roadmap expands from whiskey to craft beer and wine as separate verticals, and how that expansion is modeled determines the shape of every table that references a product.

## Decision

**One `products` table** for all verticals, discriminated by a first-class `category` column, with vertical-specific attributes as nullable columns (`proof`, `age_years`, `age_statement` today; IBU, vintage, varietal later).

**One `producers` table** for distilleries, breweries, and wineries, referenced twice from `products`:

```sql
distiller_id UUID REFERENCES producers(id),  -- where it was distilled
bottler_id   UUID REFERENCES producers(id)   -- who bottles and sells it
```

**`product_similarities`** stores relationships in one direction only, with the convention that `similarity_type` describes **what B is, relative to A**. Stored types are `step_up` and `alternative`; `step_down` is derived at query time by reading a `step_up` row backwards.

## Alternatives Considered

- **Separate tables per vertical** (`whiskeys`, `beers`, `wines`), with three sub-options for how dependent tables reference them: a polymorphic `(product_type, product_id)` pair; three parallel embedding/similarity tables; or exclusive-arc nullable FK columns.
- **Separate `distilleries` / `breweries` / `wineries` tables**, mirroring the per-vertical product split.
- **Retaining `similar_profile`** as a third similarity type alongside `step_up` and `alternative`.

## Reasoning

**Field overlap made the per-vertical split weak on its own terms.** Sorting the schema by which verticals each column applies to, roughly 90% is shared — naming, producer, region, category, flavor tags, all six pricing columns, availability, the three descriptive text fields, ratings, quality metadata, and `abv_pct`. Only `proof`, `age_years`, `age_statement`, and `whiskey_advocate_score` are whiskey-specific, with a comparable handful expected per future vertical. Splitting the table would triplicate the shared 90% to isolate the specific 10%.

**The decisive argument is what hangs off the product table.** `product_embeddings`, `product_similarities`, and eventually `user_collections` each need a foreign key to a product. With three product tables, every one of those inherits the same problem, and none of the three solutions is good:

- A polymorphic `(product_type, product_id)` reference is the worst option, because **Postgres cannot express a foreign key that targets different tables depending on a discriminator column.** Referential integrity would be lost entirely — orphaned embeddings after a delete, with no database-level protection.
- Three parallel embedding tables preserve integrity but triplicate the DDL, require three vector indexes to build and tune, and turn any embedding-model change into three migrations instead of one.
- Exclusive-arc nullable FK columns preserve integrity honestly, but require a nullable column per vertical, a `num_nonnulls` check, and multiple `LEFT JOIN`s plus `COALESCE` on every query.

One table solves this once, permanently, at the cost of a few nullable columns.

**Producer consolidation follows the same logic more strongly.** A breweries table and a wineries table would want exactly the fields `distilleries` already has — name, parent company, region, founded year, description, signature style. That's near-total overlap with no vertical-specific columns to justify the split. Some companies also genuinely span verticals (Constellation Brands owns wine, beer, and spirits), so a per-vertical producer table would model them incorrectly.

Consolidating also improves the sourced-whiskey model. A large share of American whiskey is distilled by one company and bottled by another; capturing that lets the agent identify when two differently-priced bottles are substantially the same liquid. With a single `producers` table, both roles are FKs into it — MGP and the non-distiller producer bottling its whiskey are both simply producers. Sourced detection becomes `bottler_id <> distiller_id` rather than a string comparison, and `bottler_id IS NULL` cleanly means "not yet researched," distinct from "distilled and bottled by the same company."

**On similarity directionality:** `step_up` and `step_down` are inverses, so storing both means storing every fact twice with no guarantee they stay consistent. Storing one direction and deriving the other at query time makes that class of inconsistency structurally impossible. The query reads both columns and inverts the label when it matches on `product_b_id`, so `step_down` still exists in the tool's output — it just never exists as data.

`similar_profile` was dropped because it duplicates what the embeddings already do. ADR-0006 justified this table on the grounds that it captures cultural knowledge about market role that embeddings cannot discover, precisely because such bottles often aren't flavor-similar. `similar_profile` is the one relation type a vector search over `tasting_notes` embeddings *would* find on its own, which makes it the one type that violates the table's own rationale — while consuming a hand-curation budget targeted at only 50–100 total relationships.

**On cross-vertical isolation:** the concern that a wine query might retrieve whiskey results is real at the embedding level — tasting vocabulary genuinely overlaps between barrel-aged wine and bourbon, so cosine distance alone will not separate the verticals. But separate tables are not actually safer here. Their isolation is exactly equivalent to a `WHERE category = ...` clause; they simply make the filter implicit and permanent rather than explicit and optional. The single table with a hard filter provides identical isolation while preserving the ability to query across categories deliberately. The filter should be enforced at the **tool boundary** — separate tools per vertical, each hardcoding its own category filter — rather than exposed as a parameter the model could omit.

## Consequences

- **Not yet implemented.** No migrations, tables, or schema exist in the repo as of this ADR.
- Vertical-specific columns are nullable and will accumulate as verticals are added — a few unused columns per row, accepted as the cost of a single FK target for every dependent table.
- **Table names in ADR-0006 are superseded.** That ADR references `bottle_similarities`; this decision renames it to `product_similarities`, along with `bottles` → `products`, `distilleries` → `producers`, and `bottle_embeddings` → `product_embeddings`. ADR-0006's reasoning is unaffected; only the names changed.
- ADR-0006's `producer` TEXT field is replaced by `bottler_id` as a foreign key. This requires creating producer rows for non-distiller producers rather than typing a name — the same effort with autocomplete in the admin UI, and it enables producer-level queries like "everything from Sazerac-owned distilleries" if `parent_producer_id` is added as a self-reference.
- Cross-vertical contamination is prevented by a filter, not by table structure. That makes correct tool design load-bearing: if a tool omits its category filter, nothing else stops whiskey from appearing in wine results. Per-category eval breakdowns (already called for in ADR-0006) are the backstop that would catch it.
- Field-level decisions — CHECK constraint vocabularies, `TIMESTAMPTZ`, the generated `tsvector` column, index definitions, and the `scarcity_tier` rubric — are deliberately **not** recorded here. They live as comments in the migration SQL, next to what they describe, so they cannot drift from the schema.
- Human-readable schema reference lives in `docs/schema.md` — an ER diagram plus per-table narrative, linking here and to related ADRs for reasoning. Migrations remain authoritative for exact DDL; the doc covers structure and purpose, which change far less often.

## References

- ADR-0001 — Supabase Postgres with pgvector, the platform this schema is built on
- ADR-0005 — multi-resolution embedding strategy; `product_embeddings` is its physical structure
- ADR-0006 — knowledge base curation; source of the similarities-table rationale and most field-level decisions
