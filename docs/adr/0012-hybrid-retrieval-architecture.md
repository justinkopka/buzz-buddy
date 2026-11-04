# ADR-0012: Hybrid Retrieval Architecture (Three-Arm Weighted RRF)

**Status:** Accepted
**Date:** 2026-08-17

## Context

ADR-0005 committed to hybrid retrieval — dense vector search combined with
Postgres full-text search, fused via Reciprocal Rank Fusion, then reranked
with a cross-encoder — but stated it as a strategy rather than a design.
Building it surfaced three questions that ADR-0005 does not answer, each with
consequences well beyond the retrieval function itself:

1. **How the two score scales combine.** Cosine distance and `ts_rank`
   are not comparable quantities, and the obvious reconciliation
   (normalize both, take a weighted sum) fails badly at this corpus size.
2. **Where hard constraints apply.** A budget or proof filter can run
   before retrieval or after fusion, and the two produce materially
   different failure modes.
3. **Where the ranking parameters physically live.** Postgres offers a
   native mechanism for field weighting (`setweight` on the generated
   `tsvector`), which places part of the ranking behavior in the schema
   rather than in the repository.

The third question turned out to be the one that matters most, because it
determines whether retrieval quality can be tuned by editing a constant or
requires a migration and a table rewrite.

## Decision

**Three retrieval arms, not two.** The lexical half of the hybrid splits into
two independent arms:

| Arm | Source | Signal |
|---|---|---|
| `semantic` | `product_embeddings`, all three types, `MIN` distance per product | meaning |
| `name` | `to_tsvector('english', canonical_name)`, computed per query | identity |
| `prose` | the existing `search_vector` column, unmodified | topicality |

**Fused with weighted Reciprocal Rank Fusion**, `score(d) = Σ w_arm / (k + rank_arm(d))`.

**Every ranking parameter is a Python module constant** in
`backend/app/retrieval.py` — arm weights, the RRF `k` damper, per-arm
candidate depth, result count, and the resolution thresholds. **No ranking
behavior is stored in the database.** The schema is unchanged by this
decision: no migration, no new columns, no new indexes.

**Hard filters are applied before fusion**, inside a single `eligible` CTE
that both lexical arms and the semantic arm join against.

**The semantic arm queries all three embedding types** and represents each
product by its best-matching vector, superseding ADR-0005's sequencing of
`full_profile` only with query-intent type-selection to follow.

## Alternatives Considered

- **Weighted score normalization** — min-max normalize cosine distance and
  `ts_rank` onto a shared scale, then take a weighted sum.
- **`setweight` on the generated `tsvector` column** — Postgres' native field
  weighting, tagging each lexeme A/B/C/D by source field.
- **Per-field `tsvector` columns** — one generated column and GIN index per
  searchable field, ranked separately and combined with coefficients in
  application code.
- **BM25 in application code** — load the corpus into memory on cold start and
  rank with a real BM25 implementation.
- **Post-filtering** — retrieve on relevance alone, then drop rows that violate
  the user's constraints.
- **Query-intent classification** for embedding-type selection, as ADR-0005
  originally sequenced.

## Reasoning

**Reciprocal Rank Fusion over score normalization.** The two arms produce
numbers that cannot be reconciled, and the small corpus makes normalization
actively unstable rather than merely awkward. Cosine distance is bounded
`[0, 2]`, but on a corpus that is entirely bourbon everything is somewhat
related, so realized distances occupy a narrow band — roughly 0.15 for a
strong match to 0.45 for a weak one. Min-max normalizing that band stretches
twelve-hundredths of real difference across the full unit interval, turning
near-ties into apparent landslides. Worse, the normalization constants are set
by whichever outlier happens to land in the candidate set, so adding one poor
match silently rescores every other row. The arms also return different
cardinalities by construction: the semantic arm always returns exactly the
requested depth, while a lexical arm returns however many rows actually
matched — sometimes three, sometimes sixty. Normalizing a three-row set and a
sixty-row set onto the same scale compares nothing meaningful.

RRF discards magnitudes and keeps only ordering, which is scale-free by
definition. It also produces the right behavior for free: a product appearing
in multiple arms collects from each, so agreement between independent methods
is rewarded without any explicit rule saying so.

**`k = 20` rather than the published 60.** The constant damps how strongly rank
1 outweighs rank 10. Cormack et al. published 60, tuned against TREC-scale
corpora where a downstream reranker re-sorts the top 100 and a flat curve is
therefore desirable. At `k = 60` rank 1 and rank 10 differ by 13%, which is
close to no preference at all. With roughly 1,500 products, no reranker, and a
result set of eight, the top of the list *is* the answer, so a sharper curve is
the better starting point. This is the single most likely constant to be wrong
and the cheapest to change.

**Splitting the name arm out, rather than weighting fields inside one arm.**
The flat `search_vector` has a concrete failure: searching `Eagle Rare` matches
both "Eagle Rare 10 Year" (once, in `canonical_name`) and any bottle whose
`community_sentiment` says *"often compared to Eagle Rare... a solid Eagle Rare
alternative"* (three times, in prose). `ts_rank` scores by term frequency and,
at its default normalization setting, ignores document length — so the bottle
merely *discussing* Eagle Rare outranks Eagle Rare itself. The blob has
discarded the one fact that mattered: where the term matched. A hit in
`canonical_name` asserts *this is the thing you asked for*; a hit in
`community_sentiment` asserts *this is related to what you asked for*.

`setweight` is Postgres' answer to exactly this, and it works. Running the name
match as its own arm produces the same effect through a different mechanism:
`canonical_name` is deliberately counted twice — once in its own arm, once via
`search_vector` — so a name match collects from two arms while a prose mention
collects from one. Against the case above, with `k = 20`, `w_name = 1.0` and
`w_prose = 0.7`, Eagle Rare scores `1.0/21 + 0.7/22 = 0.079` against the other
bottle's `0.7/21 = 0.033`. The correct row wins by a factor of 2.4.

**Why that mechanism, and not `setweight`.** The two produce comparable
results; they differ entirely in where the tuning knob sits. `setweight` stores
the field-to-bucket assignment inside a generated column, so changing which
bucket a field belongs to requires a migration and a full table rewrite.
Splitting arms puts the equivalent decision in `ARM_WEIGHTS`, a dictionary of
floats.

The principle underneath, which generalizes past this decision: **DDL that
affects performance belongs outside the tuning loop; DDL that affects results
does not.** Dropping an index changes latency and nothing else — every query
returns identical rows. Changing a `setweight` assignment changes which bottle
is recommended. Ranking behavior is product behavior, and product behavior
should be tunable by editing a file and redeploying, not by migrating a
database the admin UI is concurrently writing to. This matters more than usual
here because ADR-0010 commits to measuring retrieval quality with an eval
suite; a parameter sweep across a table rewrite is not a sweep anyone will
actually run.

The remaining alternatives lose on cost rather than principle. Per-field
`tsvector` columns move all coefficients into code but require N generated
columns and N GIN indexes, paying storage and write amplification on every
product save to solve a problem three arms already solve. In-memory BM25 is
genuinely attractive — it would supply the IDF term `ts_rank` lacks — but it
puts a second copy of the corpus in the Lambda that goes stale the moment a
curator saves a product, and discards an index Postgres maintains for free.

**Pre-filtering, and why it is free here.** Post-filtering has a specific
failure: a query for a wheated bourbon under $50 whose twenty best flavor
matches are all $200 allocated bottles returns *nothing*, silently, while the
knowledge base is full of qualifying options. Pre-filtering searches only the
eligible set and always returns the best eligible candidates.

Pre-filtering is normally avoided because it fights an approximate-nearest-
neighbor index — the index navigates by vector similarity alone, knows nothing
of the price filter, and can exhaust its search budget on ineligible rows. That
cost does not exist yet: the initial migration deliberately ships without an
HNSW index, on the grounds that exact search over a few thousand vectors
returns in single-digit milliseconds with perfect recall. Writing the query
pre-filtered now means the interaction is already handled if an index is added
later.

**Querying all three embedding types.** ADR-0005 sequenced retrieval against
`full_profile` alone, with query-intent-based type selection as a follow-up
phase. That phase requires building a classifier that decides whether a query
is about flavor, overall similarity, or reputation — and then living with its
mistakes. The query *"an underrated value pick that's also really sweet"*
is both a reputation question and a flavor question; a classifier must discard
half of it. Taking `MIN` distance across a product's vectors requires no
classification: whichever vector matches best represents the product, and both
halves of that query find their natural target. `MIN` rather than `SUM` also
bounds the effect of having more vectors — additional types can only help via
the single best one.

## Consequences

- **Not yet implemented.** No retrieval code exists in the repo as of this ADR;
  `backend/app/api/routes/chat.py` is still a direct passthrough to Claude with
  no tools and no retrieval.
- **Supersedes ADR-0005's retrieval sequencing.** That ADR states retrieval
  ships against `full_profile` only, with type-selection layered in later, and
  lists the other two embedding types as deliberately unused. Both statements
  are now wrong; ADR-0005 needs a `Revised:` line pointing here.
- **No schema change.** `search_vector`, `product_embeddings`, every index and
  constraint are untouched. The flat, unweighted `search_vector` is now a
  deliberate choice rather than an unexamined default — it is the prose arm,
  and the weighting that would have been applied to it lives in `ARM_WEIGHTS`.
- **Retrieval quality is coupled to curation completeness, invisibly.**
  `build_source_texts` omits an embedding type when its defining field is
  empty, so a thinly-curated product may carry only `full_profile` while a
  well-curated one carries three vectors. On a flavor query the well-curated
  product has a purpose-built `tasting_notes` vector; the thin one competes
  with a general-purpose one and loses. This is defensible — less is genuinely
  known about it, and its `data_quality` is probably `low` — but the penalty is
  a side effect of vector count rather than an explicit judgment, and it will
  not be obvious when it happens.
- **The semantic arm returns the winning `embedding_type`** alongside the
  distance, purely for debuggability. Without it, a wrong-looking result gives
  no indication of which resolution produced the match.
- **`ts_rank` still has no IDF.** Splitting arms addresses *where* a term
  matched, not *how rare* the term is, so a common word repeated in a long
  document can still outscore a rare exact match within a single arm. The name
  arm limits the blast radius; it does not fix the underlying gap. In-memory
  BM25 remains the real fix if this becomes the binding constraint.
- **The fused query is genuinely harder to read** than a single ranked
  `SELECT` — six CTEs, thirteen bind parameters. The tradeoff is accepted
  because the complexity is confined to one string in one module, while the
  behavior it produces is tunable from a dictionary of floats.
- **An expression index on `to_tsvector('english', canonical_name)` is
  available** if the name arm's per-query sequential scan ever costs real time.
  It is pure performance DDL by the principle above — adding or dropping it can
  never change a returned row — so it stays outside the tuning loop.
- **Every constant is currently an educated guess.** `RRF_K`, `ARM_WEIGHTS`,
  `SEMANTIC_CEILING`, and `FUZZY_THRESHOLD` are unvalidated until the eval
  runner of ADR-0010 exists. Placing them in one module is what makes
  validating them cheap later; it does not make them correct now.
- **Open question: the cross-encoder reranker.** ADR-0005 specifies reranking
  the fused shortlist and defers the Cohere-versus-BGE choice to implementation
  time. This pipeline ships without a rerank stage, and the choice is still
  unresolved. The deferral rests on three points: a BGE-class cross-encoder
  needs PyTorch and several gigabytes of memory against a 512 MB
  container-image Lambda; Cohere's API adds a sixth external dependency, a
  sixth secret, and a new in-request failure mode; and Claude — which already
  reads every returned result — is a stronger cross-encoder than either. A
  reranker earns its cost when candidates must be *discarded* before the model
  sees them, which is a token-budget problem this system does not yet have at
  eight results. Revisit when either (a) the eligible set surviving hard
  filters routinely exceeds ~50 products, or (b) tuning `ARM_WEIGHTS` and
  `RRF_K` plateaus while eval precision on the returned set remains below
  target. Until one of those holds, `SEARCH_LIMIT` is the cheaper lever —
  retrieving twelve and letting Claude discriminate beats retrieving eight and
  paying a network hop to reorder them.

## References

- ADR-0005 — embedding strategy; establishes hybrid retrieval and the
  three embedding types, and is partially superseded here
- ADR-0004 — custom agent loop; the consumer of these retrieval functions
- ADR-0010 — eval framework execution; the mechanism intended to validate
  every constant this decision introduces
- ADR-0011 — single-table schema; source of the tool-boundary `vertical`
  filter the `eligible` CTE hardcodes
- `docs/schema.md` — "Cross-vertical isolation" and "Similarity direction"
- `supabase/migrations/20260813010800_initial_schema.sql` — the
  `search_vector` definition and the note that `ts_rank` is not BM25
