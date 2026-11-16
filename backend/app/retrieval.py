"""Read-side retrieval over the knowledge base: the agent's tools call these.

Every ranking parameter lives in this module as a constant.

"""

from decimal import Decimal
from typing import Any
from uuid import UUID

from asyncpg import Record

from app import db, embeddings

# ---------------------------------------------------------------------------
# Ranking constants
# ---------------------------------------------------------------------------

# RRF damper. Lower is a steeper curve: at 20, rank 1 is worth ~1.45x rank 10.
# The published 60 assumes a reranker re-sorts the top 100; here the top eight
# *is* the answer. The constant most likely to be wrong.
RRF_K = 20

# The name arm and prose arm both see canonical_name (prose via search_vector),
# so a name match collects twice and a mention in someone else's prose once.
# That is the whole mechanism separating "Eagle Rare" from "a solid Eagle Rare
# alternative" -- see ADR-0012.
ARM_WEIGHTS = {"semantic": 1.0, "name": 1.0, "prose": 0.7}

# Candidates each arm contributes to fusion. Beyond this a product earns
# nothing from that arm.
ARM_DEPTH = 30

SEARCH_LIMIT = 8

# resolve_bottle stage 2. word_similarity rather than similarity: short input
# like "Pappy" scores near zero against a long canonical name under
# similarity(), but 1.0 under word_similarity(), which matches the input
# against the best-fitting *extent* of the name. pg_trgm's default is 0.6.
FUZZY_THRESHOLD = 0.5

# Candidates within this margin of the best fuzzy score make the result
# ambiguous: "Eagle Rare" against both the 10 and 17 Year scores 1.0 on each,
# and picking one would be a guess.
AMBIGUITY_MARGIN = 0.1

RESOLVE_CANDIDATES = 5

# resolve_bottle stage 3, cosine distance. Realized distances on an all-bourbon
# corpus sit roughly 0.15 (strong) to 0.45 (weak).
SEMANTIC_CEILING = 0.30

_HIDDEN = frozenset({"notes", "search_vector"})


def _public(row: Record) -> dict[str, Any]:
    return {k: v for k, v in dict(row).items() if k not in _HIDDEN}


async def _attach_producers(products: list[dict[str, Any]]) -> None:
    """Resolve producer ids to names on each product, in place, in one query.

    The rows only carry ids. Without the names the model is left to name a
    distillery from memory, which is the hallucination this system exists to
    avoid. Field names match get_details.
    """
    ids = {p[k] for p in products for k in ("distiller_id", "bottler_id") if p[k]}
    producers = {}
    if ids:
        rows = await db.fetch(
            "SELECT id, name, signature_style FROM producers WHERE id = ANY($1)",
            list(ids),
        )
        producers = {row["id"]: row for row in rows}

    for p in products:
        distiller = producers.get(p["distiller_id"])
        bottler = producers.get(p["bottler_id"])
        p["distiller_name"] = distiller["name"] if distiller else None
        p["distiller_style"] = distiller["signature_style"] if distiller else None
        p["bottler_name"] = bottler["name"] if bottler else None


async def _with_producers(rows: list[Record]) -> list[dict[str, Any]]:
    products = [_public(row) for row in rows]
    await _attach_producers(products)
    return products


# ---------------------------------------------------------------------------
# hybrid_search
# ---------------------------------------------------------------------------

# Bind parameters:
#   $1 query embedding   $2 query text   $3 ARM_DEPTH
#   $4-$9 hard filters -- NULL (or empty, for $9) disables each one
_HYBRID_SQL = """
WITH q AS (
    -- plainto_tsquery ANDs every term, which filters rather than ranks:
    -- "sweet wheated bourbon" would require all three words in one bottle.
    -- Rewriting & to | ranks by how many terms match instead.
    SELECT replace(plainto_tsquery('english', $2)::text, ' & ', ' | ')::tsquery
        AS query
),
eligible AS (
    -- If provided, apply hard filters before ranking
    SELECT id
    FROM products
    WHERE vertical = 'whiskey'
      AND ($4::text[] IS NULL OR category = ANY($4))
      AND ($5::numeric IS NULL OR COALESCE(typical_retail_low_usd, msrp_usd, typical_retail_high_usd) <= $5)
      AND ($6::numeric IS NULL OR COALESCE(typical_retail_high_usd, msrp_usd, typical_retail_low_usd) >= $6)
      AND ($7::numeric IS NULL OR proof >= $7)
      AND ($8::numeric IS NULL OR proof <= $8)
      AND NOT (id = ANY($9::uuid[]))
),
semantic_arm AS (
    -- Each product is represented by its best-matching vector across all
    -- three embedding types (MIN distance), so no query-intent classifier is
    -- needed. The winning type is kept purely for debuggability.
    SELECT id, embedding_type, distance,
           ROW_NUMBER() OVER (ORDER BY distance) AS rank
    FROM (
        SELECT DISTINCT ON (e.product_id)
               e.product_id AS id,
               e.embedding_type,
               e.embedding <=> $1::vector AS distance
        FROM product_embeddings e
        JOIN eligible el ON el.id = e.product_id
        ORDER BY e.product_id, distance
    ) best
    ORDER BY distance
    LIMIT $3
),
name_arm AS (
    SELECT p.id,
           ROW_NUMBER() OVER (
               ORDER BY ts_rank(to_tsvector('english', p.canonical_name), q.query) DESC
           ) AS rank
    FROM products p
    JOIN eligible el ON el.id = p.id
    CROSS JOIN q
    WHERE to_tsvector('english', p.canonical_name) @@ q.query
    ORDER BY rank
    LIMIT $3
),
prose_arm AS (
    SELECT p.id,
           ROW_NUMBER() OVER (ORDER BY ts_rank(p.search_vector, q.query) DESC) AS rank
    FROM products p
    JOIN eligible el ON el.id = p.id
    CROSS JOIN q
    WHERE p.search_vector @@ q.query
    ORDER BY rank
    LIMIT $3
),
candidates AS (
    SELECT id FROM semantic_arm
    UNION
    SELECT id FROM name_arm
    UNION
    SELECT id FROM prose_arm
)
SELECT p.*,
       s.rank           AS semantic_rank,
       s.distance       AS semantic_distance,
       s.embedding_type AS semantic_match,
       n.rank           AS name_rank,
       pr.rank          AS prose_rank
FROM candidates c
JOIN products p ON p.id = c.id
LEFT JOIN semantic_arm s ON s.id = c.id
LEFT JOIN name_arm n ON n.id = c.id
LEFT JOIN prose_arm pr ON pr.id = c.id
"""


def rrf_score(ranks: dict[str, int | None]) -> float:
    """Weighted Reciprocal Rank Fusion: sum of w_arm / (k + rank_arm).

    Only ordering survives, so cosine distance and ts_rank never need
    reconciling. An arm that did not rank the product (None or absent)
    contributes nothing.

    Pure on purpose: the tuning harness scores configurations with exactly
    this function, so production and tuning cannot disagree about the math.
    """
    return sum(
        weight / (RRF_K + ranks[arm])
        for arm, weight in ARM_WEIGHTS.items()
        if ranks.get(arm) is not None
    )


async def hybrid_search(
    query: str,
    *,
    categories: list[str] | None = None,
    max_price: Decimal | None = None,
    min_price: Decimal | None = None,
    min_proof: Decimal | None = None,
    max_proof: Decimal | None = None,
    exclude_ids: list[UUID] | None = None,
    limit: int = SEARCH_LIMIT,
) -> list[dict[str, Any]]:
    """Three-arm weighted RRF over the eligible set. See ADR-0012.

    Price filters test for overlap with the bottle's typical retail range, so
    "under $50" admits a bottle that is $45-$60 on the shelf -- it is findable
    at that price. A bottle with no price data at all is excluded whenever a
    price filter is set, as is one with no ABV under a proof filter.

    exclude_ids is for bottles the user already owns.

    Raises ValueError on a blank query rather than returning nothing: an empty
    result reads as "no bottles match", which is a different and false claim.
    """
    query = query.strip()
    if not query:
        raise ValueError("query must not be blank")

    vector = await embeddings.embed_query(query)
    rows = await db.fetch(
        _HYBRID_SQL,
        vector,
        query,
        ARM_DEPTH,
        # [] would reach SQL as `category = ANY('{}')` and match nothing;
        # an empty list means "no category filter", same as None.
        categories or None,
        max_price,
        min_price,
        min_proof,
        max_proof,
        exclude_ids or [],
    )

    hits = [_public(row) for row in rows]
    for hit in hits:
        hit["rrf_score"] = rrf_score({arm: hit[f"{arm}_rank"] for arm in ARM_WEIGHTS})

    # canonical_name breaks ties so equal scores always come back in one order.
    hits.sort(key=lambda h: (-h["rrf_score"], h["canonical_name"]))

    top = hits[:limit]
    await _attach_producers(top)
    return top


# ---------------------------------------------------------------------------
# resolve_bottle
# ---------------------------------------------------------------------------


async def resolve_bottle(name: str) -> dict[str, Any]:
    """Map a name the user typed to a product, cheapest method first.

    Returns {"status", "method", "matches"}, where status is one of:
      resolved   -- exactly one confident match
      ambiguous  -- several plausible matches; the agent should ask
      not_found  -- nothing close; the bottle is not in the knowledge base

    A semantic match is never reported as resolved. A vector says "something
    like this", not "this": asked for a bottle the KB lacks, the nearest vector
    is a different bottle, and treating it as the answer is exactly the
    hallucination the HR eval cases test for.
    """
    name = name.strip()
    if not name:
        return {"status": "not_found", "method": None, "matches": []}

    exact = await db.fetch(
        "SELECT * FROM products WHERE vertical = 'whiskey' "
        "AND (lower(canonical_name) = lower($1) OR lower(full_name) = lower($1)) "
        "ORDER BY canonical_name",
        name,
    )
    if exact:
        return {
            "status": "resolved" if len(exact) == 1 else "ambiguous",
            "method": "exact",
            "matches": await _with_producers(exact),
        }

    fuzzy = await db.fetch(
        "SELECT *, word_similarity($1, canonical_name) AS match_score "
        "FROM products "
        "WHERE vertical = 'whiskey' AND word_similarity($1, canonical_name) >= $2 "
        "ORDER BY match_score DESC, canonical_name LIMIT $3",
        name,
        FUZZY_THRESHOLD,
        RESOLVE_CANDIDATES,
    )
    if fuzzy:
        best = fuzzy[0]["match_score"]
        close = [r for r in fuzzy if best - r["match_score"] <= AMBIGUITY_MARGIN]
        return {
            "status": "resolved" if len(close) == 1 else "ambiguous",
            "method": "fuzzy",
            "matches": await _with_producers(close),
        }

    vector = await embeddings.embed_query(name)
    semantic = await db.fetch(
        "SELECT p.*, best.distance AS match_score "
        "FROM ("
        "    SELECT DISTINCT ON (product_id) product_id, embedding <=> $1::vector AS distance"
        "    FROM product_embeddings ORDER BY product_id, distance"
        ") best "
        "JOIN products p ON p.id = best.product_id "
        "WHERE p.vertical = 'whiskey' AND best.distance <= $2 "
        "ORDER BY best.distance LIMIT $3",
        vector,
        SEMANTIC_CEILING,
        RESOLVE_CANDIDATES,
    )
    if semantic:
        return {
            "status": "ambiguous",
            "method": "semantic",
            "matches": await _with_producers(semantic),
        }

    return {"status": "not_found", "method": None, "matches": []}


# ---------------------------------------------------------------------------
# get_details / get_related
# ---------------------------------------------------------------------------


async def get_details(product_id: UUID) -> dict[str, Any] | None:
    """One full record, with producer names resolved -- the row only has ids."""
    row = await db.fetchrow(
        "SELECT p.*, "
        "       d.name AS distiller_name, d.signature_style AS distiller_style, "
        "       b.name AS bottler_name "
        "FROM products p "
        "LEFT JOIN producers d ON d.id = p.distiller_id "
        "LEFT JOIN producers b ON b.id = p.bottler_id "
        "WHERE p.id = $1 AND p.vertical = 'whiskey'",
        product_id,
    )
    return _public(row) if row else None


# step_down is never stored: it is a step_up row read from the B side, so the
# label is inverted here. alternative is symmetric and found from either side;
# DISTINCT ON drops the duplicate if a curator entered it in both directions.
_RELATED_SQL = """
WITH relations AS (
    SELECT product_b_id AS id, similarity_type AS relation, notes AS relation_notes
    FROM product_similarities
    WHERE product_a_id = $1
    UNION ALL
    SELECT product_a_id,
           CASE similarity_type WHEN 'step_up' THEN 'step_down' ELSE similarity_type END,
           notes
    FROM product_similarities
    WHERE product_b_id = $1
)
SELECT * FROM (
    SELECT DISTINCT ON (p.id, r.relation) p.*, r.relation, r.relation_notes
    FROM relations r
    JOIN products p ON p.id = r.id
    WHERE p.vertical = 'whiskey'
    ORDER BY p.id, r.relation
) related
ORDER BY relation, canonical_name
"""


async def get_related(product_id: UUID) -> list[dict[str, Any]]:
    """Curated market-role neighbors: step_up, step_down, alternative.

    relation_notes is the curator's explanation of the relationship and is
    meant to be surfaced -- unlike products.notes, which _public strips.
    """
    rows = await db.fetch(_RELATED_SQL, product_id)
    return await _with_producers(rows)
