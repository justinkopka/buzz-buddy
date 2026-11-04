import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app import crud, embeddings
from app.auth import require_role
from app.schemas import (
    Category,
    EmbeddingStatus,
    EmbeddingSync,
    Producer,
    ProducerWrite,
    Product,
    ProductSaved,
    ProductWrite,
    Similarity,
    SimilarityType,
    SimilarityWrite,
    Vertical,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_role("admin"))],
)


# ---------------------------------------------------------------------------
# producers
# ---------------------------------------------------------------------------


@router.get("/producers", response_model=list[Producer])
async def list_producers(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return await crud.list_producers(limit=limit, offset=offset)


@router.get("/producers/{producer_id}", response_model=Producer)
async def get_producer(producer_id: UUID):
    producer = await crud.get_producer(producer_id)
    if producer is None:
        raise HTTPException(status_code=404, detail="Producer not found")
    return producer


@router.post("/producers", response_model=Producer, status_code=201)
async def create_producer(data: ProducerWrite):
    return await crud.create_producer(data)


@router.put("/producers/{producer_id}", response_model=Producer)
async def update_producer(producer_id: UUID, data: ProducerWrite):
    """Full replace, not a patch.

    The admin form loads every field and submits every field, so an omitted
    value means "clear this", not "leave it alone".
    """
    producer = await crud.update_producer(producer_id, data)
    if producer is None:
        raise HTTPException(status_code=404, detail="Producer not found")
    return producer


@router.delete("/producers/{producer_id}", status_code=204)
async def delete_producer(producer_id: UUID):
    if not await crud.delete_producer(producer_id):
        raise HTTPException(status_code=404, detail="Producer not found")
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# products
# ---------------------------------------------------------------------------


@router.get("/products", response_model=list[Product])
async def list_products(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    search: str | None = Query(None, description="Substring match on canonical_name"),
    vertical: Vertical | None = None,
    category: Category | None = None,
):
    return await crud.list_products(
        limit=limit,
        offset=offset,
        search=search,
        vertical=vertical,
        category=category,
    )


@router.get("/products/{product_id}", response_model=Product)
async def get_product(product_id: UUID):
    product = await crud.get_product(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


async def _sync(product_id: UUID, force: bool = False) -> EmbeddingSync:
    """Refresh embeddings without ever failing the request.

    The product row is already committed by the time this runs. Letting an
    OpenAI outage turn a successful save into a 500 would tell the curator
    their work was lost when it was not. The failure is reported instead, and
    the list view shows the product as stale until a later sync fixes it.
    """
    try:
        return EmbeddingSync(ok=True, **await embeddings.sync_embeddings(product_id, force))
    except Exception:  # noqa: BLE001 - deliberate: the save must stand
        # The traceback goes to CloudWatch, not the client: OpenAI and asyncpg
        # messages can carry internal detail the browser has no use for.
        logger.exception("Embedding sync failed for product %s", product_id)
        return EmbeddingSync(
            ok=False, error="Embedding generation failed; the product was saved."
        )


@router.post("/products", response_model=ProductSaved, status_code=201)
async def create_product(data: ProductWrite):
    product = await crud.create_product(data)
    return ProductSaved(product=product, embeddings=await _sync(product.id))


@router.put("/products/{product_id}", response_model=ProductSaved)
async def update_product(product_id: UUID, data: ProductWrite):
    """Full replace -- see the note on update_producer."""
    product = await crud.update_product(product_id, data)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return ProductSaved(product=product, embeddings=await _sync(product.id))


@router.get("/products/{product_id}/embeddings", response_model=EmbeddingStatus)
async def get_embedding_status(product_id: UUID):
    if await crud.get_product(product_id) is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return EmbeddingStatus(**await embeddings.embedding_status(product_id))


@router.post("/products/{product_id}/embeddings", response_model=EmbeddingSync)
async def regenerate_embeddings(product_id: UUID, force: bool = Query(False)):
    """Manual refresh. force=True re-embeds even when the source text matches."""
    if await crud.get_product(product_id) is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return await _sync(product_id, force=force)


@router.delete("/products/{product_id}", status_code=204)
async def delete_product(product_id: UUID):
    """Cascades to this product's embeddings and similarity rows."""
    if not await crud.delete_product(product_id):
        raise HTTPException(status_code=404, detail="Product not found")
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# product_similarities
# ---------------------------------------------------------------------------


@router.get("/similarities", response_model=list[Similarity])
async def list_similarities(
    product_id: UUID | None = Query(None, description="Matches either side"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return await crud.list_similarities(
        product_id=product_id, limit=limit, offset=offset
    )


@router.post("/similarities", response_model=Similarity, status_code=201)
async def create_similarity(data: SimilarityWrite):
    return await crud.create_similarity(data)


@router.delete("/similarities", status_code=204)
async def delete_similarity(
    product_a_id: UUID,
    product_b_id: UUID,
    similarity_type: SimilarityType,
):
    """Identified by the full composite key, so all three are query params.

    There is no PUT: the only mutable field is `notes`, and a relationship
    that turns out to be wrong gets deleted and re-entered.
    """
    if not await crud.delete_similarity(product_a_id, product_b_id, similarity_type):
        raise HTTPException(status_code=404, detail="Relationship not found")
    return Response(status_code=204)
