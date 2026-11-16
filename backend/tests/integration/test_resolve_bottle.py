"""resolve_bottle's three stages against the local copy of the knowledge base.

The exact and fuzzy stages must never embed: no_openai fails any test that
reaches OpenAI, so passing those tests proves the cheap paths stay cheap.

Not covered here: ambiguous exact or fuzzy matches. The pilot bottles share
no name fragments, so the case needs two products like "Eagle Rare 10 Year"
and "Eagle Rare 17 Year" in the knowledge base first.
"""

import pytest

from app import retrieval
from conftest import FAR_VECTOR

GIBBERISH = "zzqxv qqzz"


async def test_exact_canonical_name_is_case_insensitive(product_named):
    target = product_named("Buffalo Trace")

    result = await retrieval.resolve_bottle("  bUFFALO tRACE ")

    assert result["status"] == "resolved"
    assert result["method"] == "exact"
    assert [m["id"] for m in result["matches"]] == [target["id"]]


async def test_exact_full_name(product_named):
    target = product_named("Wild Turkey 101")
    if not target["full_name"]:
        pytest.skip("no full_name recorded")

    result = await retrieval.resolve_bottle(target["full_name"].lower())

    assert result["status"] == "resolved"
    assert result["method"] == "exact"
    assert result["matches"][0]["id"] == target["id"]


@pytest.mark.parametrize(
    ("typed", "canonical"),
    [
        ("wild turkey", "Wild Turkey 101"),
        ("russells reserve 13", "Russell's Reserve 13 Year"),
        ("new riff bib", "New Riff Bottled-in-Bond"),
    ],
)
async def test_fuzzy_resolves_partial_and_misspelled_names(product_named, typed, canonical):
    target = product_named(canonical)

    result = await retrieval.resolve_bottle(typed)

    assert result["method"] == "fuzzy"
    assert result["status"] == "resolved"
    assert [m["id"] for m in result["matches"]] == [target["id"]]


async def test_semantic_match_is_never_resolved(product_named, stored_vector, query_vector):
    """A vector match is "something like this", not "this" -- the HR guard."""
    target = product_named("Wild Turkey 101")
    calls = query_vector(await stored_vector(target["id"]))

    result = await retrieval.resolve_bottle(GIBBERISH)

    assert calls == [GIBBERISH]
    assert result["method"] == "semantic"
    assert result["status"] == "ambiguous"
    assert result["matches"][0]["id"] == target["id"]


async def test_nothing_close_is_not_found(query_vector):
    query_vector(FAR_VECTOR)

    result = await retrieval.resolve_bottle(GIBBERISH)

    assert result == {"status": "not_found", "method": None, "matches": []}


async def test_blank_name_is_not_found_without_embedding():
    result = await retrieval.resolve_bottle("   ")

    assert result == {"status": "not_found", "method": None, "matches": []}


async def test_matches_hide_internal_columns(product_named):
    product_named("Buffalo Trace")

    result = await retrieval.resolve_bottle("Buffalo Trace")

    assert "notes" not in result["matches"][0]
    assert "search_vector" not in result["matches"][0]
