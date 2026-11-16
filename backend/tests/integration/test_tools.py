"""execute_tool against the local copy of the knowledge base.

Covers the layer between Claude and retrieval.py: validation, what the model
is allowed to read, and failures coming back as error results instead of
exceptions. Retrieval behavior itself is covered by its own tests.
"""

import json
import uuid

import pytest

from app import tools
from conftest import FAR_VECTOR

INTERNAL_FIELDS = {
    "rrf_score",
    "semantic_rank",
    "semantic_distance",
    "semantic_match",
    "name_rank",
    "prose_rank",
    "match_score",
    "created_at",
    "updated_at",
    "distiller_id",
    "bottler_id",
    "vertical",
    "notes",
    "search_vector",
}


# --- definitions ---------------------------------------------------------------


def test_definitions_are_valid_for_the_api():
    names = [t["name"] for t in tools.TOOL_DEFINITIONS]

    assert names == [
        "search_whiskey",
        "resolve_bottle",
        "get_bottle_details",
        "get_related_bottles",
    ]
    for definition in tools.TOOL_DEFINITIONS:
        assert definition["description"]
        assert definition["input_schema"]["type"] == "object"
        assert definition["input_schema"]["additionalProperties"] is False


def test_search_does_not_expose_limit():
    schema = tools.TOOL_DEFINITIONS[0]["input_schema"]

    assert "limit" not in schema["properties"]
    assert "exclude_product_ids" in schema["properties"]


# --- search_whiskey ------------------------------------------------------------


async def test_search_output_is_json_without_internal_fields(query_vector):
    query_vector(FAR_VECTOR)

    outcome = await tools.execute_tool("search_whiskey", {"query": "wild turkey"})

    assert outcome.is_error is False
    results = json.loads(outcome.content)["results"]
    assert results
    for product in results:
        assert not INTERNAL_FIELDS & product.keys()
        assert product["id"]
        assert None not in product.values()


async def test_search_raw_keeps_ranking_data_for_traces(query_vector):
    query_vector(FAR_VECTOR)

    outcome = await tools.execute_tool("search_whiskey", {"query": "wild turkey"})

    assert "rrf_score" in outcome.raw["results"][0]


async def test_search_applies_price_filter_from_json_numbers(query_vector):
    query_vector(FAR_VECTOR)

    outcome = await tools.execute_tool(
        "search_whiskey", {"query": "bourbon", "max_price": 30}
    )

    for product in outcome.raw["results"]:
        low = product["typical_retail_low_usd"]
        assert (low if low is not None else product["msrp_usd"]) <= 30


async def test_search_excludes_product_ids(products, query_vector):
    query_vector(FAR_VECTOR)
    excluded = products[0]["id"]

    outcome = await tools.execute_tool(
        "search_whiskey", {"query": "bourbon", "exclude_product_ids": [str(excluded)]}
    )

    assert excluded not in {p["id"] for p in outcome.raw["results"]}


async def test_results_carry_producer_names(product_named, query_vector):
    target = product_named("Wild Turkey 101")
    query_vector(FAR_VECTOR)

    outcome = await tools.execute_tool("search_whiskey", {"query": "wild turkey"})

    found = next(
        p for p in json.loads(outcome.content)["results"] if p["id"] == str(target["id"])
    )
    assert found["distiller_name"] == "Wild Turkey Distilling Co."


# --- the other tools -------------------------------------------------------------


async def test_resolve_reports_status_and_producer(product_named):
    product_named("Wild Turkey 101")

    outcome = await tools.execute_tool("resolve_bottle", {"name": "Wild Turkey 101"})

    result = json.loads(outcome.content)
    assert result["status"] == "resolved"
    assert result["matches"][0]["distiller_name"] == "Wild Turkey Distilling Co."
    assert not INTERNAL_FIELDS & result["matches"][0].keys()


async def test_resolve_not_found_is_an_answer_not_an_error(query_vector):
    query_vector(FAR_VECTOR)

    outcome = await tools.execute_tool("resolve_bottle", {"name": "zzqxv qqzz"})

    assert outcome.is_error is False
    # method is None, and nulls are dropped for the model.
    assert json.loads(outcome.content) == {"status": "not_found", "matches": []}


async def test_details_accepts_an_id_from_json(product_named):
    target = product_named("Buffalo Trace")

    outcome = await tools.execute_tool(
        "get_bottle_details", {"product_id": str(target["id"])}
    )

    assert json.loads(outcome.content)["canonical_name"] == "Buffalo Trace"


async def test_details_for_unknown_id_is_an_answer_not_an_error():
    outcome = await tools.execute_tool(
        "get_bottle_details", {"product_id": str(uuid.uuid4())}
    )

    assert outcome.is_error is False
    assert json.loads(outcome.content) == {"status": "not_found"}


async def test_related_returns_a_list(product_named):
    target = product_named("Buffalo Trace")

    outcome = await tools.execute_tool(
        "get_related_bottles", {"product_id": str(target["id"])}
    )

    assert outcome.is_error is False
    assert isinstance(json.loads(outcome.content)["related"], list)


# --- failures come back as results ------------------------------------------------


@pytest.mark.parametrize(
    ("name", "tool_input", "mentions"),
    [
        ("Search_Whiskey", {"query": "x"}, "search_whiskey"),
        ("search_whiskey", {}, "query"),
        ("search_whiskey", {"query": "x", "limit": 50}, "limit"),
        ("search_whiskey", {"query": "x", "max_price": -1}, "max_price"),
        ("search_whiskey", {"query": "x", "categories": ["vodka"]}, "categories"),
        ("search_whiskey", {"query": "   "}, "blank"),
        ("get_bottle_details", {"product_id": "Buffalo Trace"}, "product_id"),
    ],
)
async def test_bad_calls_return_a_correctable_error(name, tool_input, mentions):
    outcome = await tools.execute_tool(name, tool_input)

    assert outcome.is_error is True
    assert mentions in outcome.content


async def test_infrastructure_failure_does_not_leak_detail():
    # no_openai makes the embedding call raise, as an outage would.
    outcome = await tools.execute_tool("search_whiskey", {"query": "bourbon"})

    assert outcome.is_error is True
    assert "OpenAI" not in outcome.content
    assert "search_whiskey failed" in outcome.content
