"""hybrid_search against the local copy of the knowledge base.

Filter tests compute the expected result set in Python from the `products`
fixture, so they hold however the knowledge base grows -- as long as the
eligible set fits inside one page (`limit=50`) and every eligible product has
at least one embedding, which puts it in the semantic arm.
"""

from decimal import Decimal

import pytest

from app import retrieval
from conftest import FAR_VECTOR

# Matches nothing lexically: plainto_tsquery keeps it as one unknown lexeme,
# so only the semantic arm contributes and its behavior is isolated.
NO_LEXICAL_MATCH = "zzqxv"


def _first_known(*values):
    return next((v for v in values if v is not None), None)


# Same fallback order as the eligible CTE: the real end of the shelf range
# first, then MSRP, then the opposite end.
def _price_low(p):
    return _first_known(p["typical_retail_low_usd"], p["msrp_usd"], p["typical_retail_high_usd"])


def _price_high(p):
    return _first_known(p["typical_retail_high_usd"], p["msrp_usd"], p["typical_retail_low_usd"])


# --- semantic arm --------------------------------------------------------------


async def test_own_vector_ranks_first_at_zero_distance(product_named, stored_vector, query_vector):
    target = product_named("Wild Turkey 101")
    calls = query_vector(await stored_vector(target["id"], "tasting_notes"))

    hits = await retrieval.hybrid_search(NO_LEXICAL_MATCH)

    assert calls == [NO_LEXICAL_MATCH]
    top = hits[0]
    assert top["id"] == target["id"]
    assert top["semantic_rank"] == 1
    assert top["semantic_distance"] == pytest.approx(0, abs=1e-6)
    # MIN across types: its tasting_notes vector is the exact match, so it wins.
    assert top["semantic_match"] == "tasting_notes"


async def test_no_lexical_match_leaves_only_semantic_ranks(product_named, stored_vector, query_vector):
    target = product_named("Wild Turkey 101")
    query_vector(await stored_vector(target["id"]))

    hits = await retrieval.hybrid_search(NO_LEXICAL_MATCH)

    assert hits
    assert all(h["name_rank"] is None and h["prose_rank"] is None for h in hits)
    assert all(h["semantic_rank"] is not None for h in hits)


# --- lexical arms ----------------------------------------------------------------


async def test_name_match_outranks_prose_mentions(product_named, query_vector):
    """The ADR-0012 Eagle Rare case, on real data.

    Russell's Reserve is Wild Turkey's premium line, so other bottles' prose
    can mention "Wild Turkey". Only one bottle is *named* it, and that one
    must win. FAR_VECTOR keeps the semantic arm from expressing a preference.
    """
    target = product_named("Wild Turkey 101")
    query_vector(FAR_VECTOR)

    hits = await retrieval.hybrid_search("Wild Turkey")

    assert hits[0]["id"] == target["id"]
    assert hits[0]["name_rank"] == 1
    assert hits[0]["prose_rank"] is not None
    assert [h["id"] for h in hits if h["name_rank"] is not None] == [target["id"]]


# --- fusion and output shape -------------------------------------------------------


async def test_results_sorted_by_score_with_score_matching_ranks(product_named, query_vector):
    query_vector(FAR_VECTOR)

    hits = await retrieval.hybrid_search("Wild Turkey")

    scores = [h["rrf_score"] for h in hits]
    assert scores == sorted(scores, reverse=True)
    for h in hits:
        ranks = {arm: h[f"{arm}_rank"] for arm in retrieval.ARM_WEIGHTS}
        assert h["rrf_score"] == pytest.approx(retrieval.rrf_score(ranks))


async def test_internal_columns_never_returned(query_vector):
    query_vector(FAR_VECTOR)

    hits = await retrieval.hybrid_search("bourbon")

    assert hits
    for h in hits:
        assert "notes" not in h
        assert "search_vector" not in h


async def test_limit_truncates(products, query_vector):
    if len(products) < 3:
        pytest.skip("needs at least three products")
    query_vector(FAR_VECTOR)

    hits = await retrieval.hybrid_search(NO_LEXICAL_MATCH, limit=2)

    assert len(hits) == 2


async def test_blank_query_raises_without_embedding():
    # no_openai would fail the test if embed_query were reached.
    with pytest.raises(ValueError):
        await retrieval.hybrid_search("   ")


# --- hard filters ---------------------------------------------------------------------


FILTER_CASES = [
    pytest.param(
        {"max_price": Decimal("30")},
        lambda p: _price_low(p) is not None and _price_low(p) <= 30,
        id="max_price",
    ),
    pytest.param(
        {"min_price": Decimal("100")},
        lambda p: _price_high(p) is not None and _price_high(p) >= 100,
        id="min_price",
    ),
    pytest.param(
        {"min_proof": Decimal("100")},
        lambda p: p["proof"] is not None and p["proof"] >= 100,
        id="min_proof_excludes_unknown_abv",
    ),
    pytest.param(
        {"max_proof": Decimal("95")},
        lambda p: p["proof"] is not None and p["proof"] <= 95,
        id="max_proof",
    ),
    pytest.param(
        {"categories": ["rye"]},
        lambda p: p["category"] == "rye",
        id="category",
    ),
]


@pytest.mark.parametrize(("filters", "eligible"), FILTER_CASES)
async def test_filter_returns_exactly_the_eligible_set(products, query_vector, filters, eligible):
    query_vector(FAR_VECTOR)

    hits = await retrieval.hybrid_search(NO_LEXICAL_MATCH, limit=50, **filters)

    expected = {p["id"] for p in products if eligible(p) and p["embedding_count"] > 0}
    assert {h["id"] for h in hits} == expected


async def test_empty_category_list_means_no_filter(query_vector):
    query_vector(FAR_VECTOR)

    unfiltered = await retrieval.hybrid_search(NO_LEXICAL_MATCH, limit=50)
    empty = await retrieval.hybrid_search(NO_LEXICAL_MATCH, limit=50, categories=[])

    assert unfiltered
    assert [h["id"] for h in empty] == [h["id"] for h in unfiltered]


async def test_exclude_ids_removes_only_those(products, query_vector):
    query_vector(FAR_VECTOR)
    excluded = products[0]["id"]

    hits = await retrieval.hybrid_search(NO_LEXICAL_MATCH, limit=50, exclude_ids=[excluded])

    expected = {p["id"] for p in products if p["embedding_count"] > 0} - {excluded}
    assert {h["id"] for h in hits} == expected
