"""get_details and get_related.

The production copy has no curated similarities yet, so `relationships`
inserts a few for the session and removes exactly the rows it inserted.
"""

import uuid

import pytest
import pytest_asyncio

from app import db, retrieval


# --- get_details -------------------------------------------------------------------


async def test_details_resolve_producer_names(products):
    target = next((p for p in products if p["distiller_id"]), None)
    if target is None:
        pytest.skip("no product has a distiller recorded")
    distiller = await db.fetchrow(
        "SELECT name FROM producers WHERE id = $1", target["distiller_id"]
    )

    details = await retrieval.get_details(target["id"])

    assert details["id"] == target["id"]
    assert details["distiller_name"] == distiller["name"]
    assert "notes" not in details
    assert "search_vector" not in details


async def test_details_unknown_id_is_none():
    assert await retrieval.get_details(uuid.uuid4()) is None


# --- get_related ---------------------------------------------------------------------


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def relationships(database, products):
    """Three rows, chosen to exercise every direction rule:

      (wild_turkey, russells, step_up)       forward step_up / reverse step_down
      (buffalo_trace, wild_turkey, alternative)
      (wild_turkey, buffalo_trace, alternative)   same fact entered both ways
    """
    by_name = {p["canonical_name"]: p["id"] for p in products}
    needed = ["Wild Turkey 101", "Russell's Reserve 13 Year", "Buffalo Trace"]
    if any(n not in by_name for n in needed):
        pytest.skip("pilot bottles for relationship tests are not all present")
    wt, rr, bt = (by_name[n] for n in needed)

    rows = [
        (wt, rr, "step_up"),
        (bt, wt, "alternative"),
        (wt, bt, "alternative"),
    ]
    inserted = []
    for a, b, kind in rows:
        # ON CONFLICT: a curated copy of the same fact may already exist, and
        # it must survive teardown.
        row = await db.fetchrow(
            "INSERT INTO product_similarities (product_a_id, product_b_id, similarity_type, notes) "
            "VALUES ($1, $2, $3, 'test fixture') ON CONFLICT DO NOTHING RETURNING product_a_id",
            a,
            b,
            kind,
            write=True,
        )
        if row is not None:
            inserted.append((a, b, kind))

    yield {"wild_turkey": wt, "russells": rr, "buffalo_trace": bt}

    for a, b, kind in inserted:
        await db.execute(
            "DELETE FROM product_similarities "
            "WHERE product_a_id = $1 AND product_b_id = $2 AND similarity_type = $3",
            a,
            b,
            kind,
        )


def _relations(related: list[dict]) -> dict:
    return {(r["id"], r["relation"]) for r in related}


async def test_forward_step_up(relationships):
    related = await retrieval.get_related(relationships["wild_turkey"])

    assert (relationships["russells"], "step_up") in _relations(related)


async def test_reverse_step_up_reads_as_step_down(relationships):
    related = await retrieval.get_related(relationships["russells"])

    assert (relationships["wild_turkey"], "step_down") in _relations(related)
    assert (relationships["wild_turkey"], "step_up") not in _relations(related)


async def test_alternative_found_from_either_side_once(relationships):
    from_wt = await retrieval.get_related(relationships["wild_turkey"])
    from_bt = await retrieval.get_related(relationships["buffalo_trace"])

    assert [r["relation"] for r in from_wt if r["id"] == relationships["buffalo_trace"]] == [
        "alternative"
    ]
    assert [r["relation"] for r in from_bt if r["id"] == relationships["wild_turkey"]] == [
        "alternative"
    ]


async def test_related_rows_carry_relation_notes_not_product_notes(relationships):
    related = await retrieval.get_related(relationships["wild_turkey"])

    assert related
    for r in related:
        assert "relation_notes" in r
        assert "notes" not in r
        assert "search_vector" not in r


async def test_unrelated_product_has_no_relations(products, relationships):
    involved = set(relationships.values())
    loner = next((p["id"] for p in products if p["id"] not in involved), None)
    if loner is None:
        pytest.skip("every product is part of the fixture relationships")

    related = await retrieval.get_related(loner)

    assert not any(r["id"] in involved and r["relation_notes"] == "test fixture" for r in related)
