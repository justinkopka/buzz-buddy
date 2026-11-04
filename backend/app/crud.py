"""Database operations for the knowledge base.

Plain async functions rather than route handlers, so they can be called
outside an HTTP request -- the embedding pipeline writes products without a
client on the other end.

Column lists are derived from the Pydantic models at import time. That is
safe from injection because the names come from the class definition, never
from request data: `extra="forbid"` has already rejected any field not
declared on the model. Values always travel as $1-style bind parameters.

SELECT * is used throughout. The read models carry extra="ignore", so
database-generated columns the API does not expose (products.search_vector)
are dropped on the way through rather than needing an explicit column list
that would drift as the schema grows.
"""

from typing import Any
from uuid import UUID

from app import db
from app.schemas import (
    Producer,
    ProducerWrite,
    Product,
    ProductWrite,
    Similarity,
    SimilarityWrite,
)

_PRODUCER_COLS = list(ProducerWrite.model_fields)
_PRODUCT_COLS = list(ProductWrite.model_fields)
_SIMILARITY_COLS = list(SimilarityWrite.model_fields)


def _values(data: Any, columns: list[str]) -> list:
    return [getattr(data, col) for col in columns]


def _insert_sql(table: str, columns: list[str]) -> str:
    names = ", ".join(columns)
    placeholders = ", ".join(f"${i}" for i in range(1, len(columns) + 1))
    return f"INSERT INTO {table} ({names}) VALUES ({placeholders}) RETURNING *"


def _update_sql(table: str, columns: list[str]) -> str:
    assignments = ", ".join(f"{col} = ${i}" for i, col in enumerate(columns, start=1))
    return f"UPDATE {table} SET {assignments} WHERE id = ${len(columns) + 1} RETURNING *"


# ---------------------------------------------------------------------------
# producers
# ---------------------------------------------------------------------------


async def list_producers(limit: int = 50, offset: int = 0) -> list[Producer]:
    rows = await db.fetch(
        "SELECT * FROM producers ORDER BY name LIMIT $1 OFFSET $2",
        limit,
        offset,
    )
    return [Producer(**dict(row)) for row in rows]


async def count_producers() -> int:
    row = await db.fetchrow("SELECT count(*) AS n FROM producers")
    return row["n"]


async def get_producer(producer_id: UUID) -> Producer | None:
    row = await db.fetchrow("SELECT * FROM producers WHERE id = $1", producer_id)
    return Producer(**dict(row)) if row else None


async def create_producer(data: ProducerWrite) -> Producer:
    row = await db.fetchrow(
        _insert_sql("producers", _PRODUCER_COLS),
        *_values(data, _PRODUCER_COLS),
        write=True,
    )
    return Producer(**dict(row))


async def update_producer(producer_id: UUID, data: ProducerWrite) -> Producer | None:
    row = await db.fetchrow(
        _update_sql("producers", _PRODUCER_COLS),
        *_values(data, _PRODUCER_COLS),
        producer_id,
        write=True,
    )
    return Producer(**dict(row)) if row else None


async def delete_producer(producer_id: UUID) -> bool:
    """Returns False when no row matched, so the route can 404.

    A producer still referenced by products raises ForeignKeyViolationError,
    which the error handlers turn into a 409 rather than a 500.
    """
    status = await db.execute("DELETE FROM producers WHERE id = $1", producer_id)
    return status != "DELETE 0"


# ---------------------------------------------------------------------------
# products
# ---------------------------------------------------------------------------


async def list_products(
    limit: int = 50,
    offset: int = 0,
    search: str | None = None,
    vertical: str | None = None,
    category: str | None = None,
) -> list[Product]:
    """Filtered listing for the curation UI.

    Only placeholder *numbers* are interpolated into the SQL; every value is
    bound. `search` is a substring match on canonical_name, which is what the
    curator actually types when hunting for a bottle they may have entered
    already.
    """
    conditions: list[str] = []
    params: list[Any] = []

    if search:
        params.append(f"%{search}%")
        conditions.append(f"canonical_name ILIKE ${len(params)}")
    if vertical:
        params.append(vertical)
        conditions.append(f"vertical = ${len(params)}")
    if category:
        params.append(category)
        conditions.append(f"category = ${len(params)}")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.extend([limit, offset])

    rows = await db.fetch(
        f"SELECT * FROM products {where} ORDER BY canonical_name "
        f"LIMIT ${len(params) - 1} OFFSET ${len(params)}",
        *params,
    )
    return [Product(**dict(row)) for row in rows]


async def count_products() -> int:
    row = await db.fetchrow("SELECT count(*) AS n FROM products")
    return row["n"]


async def get_product(product_id: UUID) -> Product | None:
    row = await db.fetchrow("SELECT * FROM products WHERE id = $1", product_id)
    return Product(**dict(row)) if row else None


async def create_product(data: ProductWrite) -> Product:
    row = await db.fetchrow(
        _insert_sql("products", _PRODUCT_COLS),
        *_values(data, _PRODUCT_COLS),
        write=True,
    )
    return Product(**dict(row))


async def update_product(product_id: UUID, data: ProductWrite) -> Product | None:
    row = await db.fetchrow(
        _update_sql("products", _PRODUCT_COLS),
        *_values(data, _PRODUCT_COLS),
        product_id,
        write=True,
    )
    return Product(**dict(row)) if row else None


async def delete_product(product_id: UUID) -> bool:
    """Cascades to product_embeddings and product_similarities."""
    status = await db.execute("DELETE FROM products WHERE id = $1", product_id)
    return status != "DELETE 0"


# ---------------------------------------------------------------------------
# product_similarities
# ---------------------------------------------------------------------------


async def list_similarities(
    product_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Similarity]:
    """Raw stored rows, in the direction they were entered.

    Filtering by product matches BOTH sides deliberately: a step_up row stored
    as (A, B) is also the fact that A is a step down from B, so a query for B
    that only looked at product_a_id would miss it. Inverting the label for the
    reverse direction is retrieval's job, not CRUD's -- see the convention on
    SimilarityWrite.
    """
    if product_id is None:
        rows = await db.fetch(
            "SELECT * FROM product_similarities ORDER BY created_at DESC "
            "LIMIT $1 OFFSET $2",
            limit,
            offset,
        )
    else:
        rows = await db.fetch(
            "SELECT * FROM product_similarities "
            "WHERE product_a_id = $1 OR product_b_id = $1 "
            "ORDER BY created_at DESC LIMIT $2 OFFSET $3",
            product_id,
            limit,
            offset,
        )
    return [Similarity(**dict(row)) for row in rows]


async def create_similarity(data: SimilarityWrite) -> Similarity:
    row = await db.fetchrow(
        _insert_sql("product_similarities", _SIMILARITY_COLS),
        *_values(data, _SIMILARITY_COLS),
        write=True,
    )
    return Similarity(**dict(row))


async def delete_similarity(
    product_a_id: UUID, product_b_id: UUID, similarity_type: str
) -> bool:
    """All three parts are required: they are the composite primary key.

    There is no update operation -- the only mutable field is `notes`, and a
    relationship that turns out to be wrong is deleted and re-entered rather
    than edited into a different fact.
    """
    status = await db.execute(
        "DELETE FROM product_similarities "
        "WHERE product_a_id = $1 AND product_b_id = $2 AND similarity_type = $3",
        product_a_id,
        product_b_id,
        similarity_type,
    )
    return status != "DELETE 0"
