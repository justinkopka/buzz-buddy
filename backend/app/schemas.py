from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------------------------------------------------------------------------
# Any change here needs the matching CHECK updated in a migration, and vice
# versa. `category` is expected to gain values as verticals are added.
# ---------------------------------------------------------------------------

Vertical = Literal["whiskey", "beer", "wine"]

Category = Literal[
    "bourbon",
    "rye",
    "scotch",
    "irish",
    "japanese",
    "canadian",
    "tennessee",
    "american_single_malt",
]

Availability = Literal["widely_available", "regional", "allocated", "discontinued"]

DataQuality = Literal["high", "medium", "low"]

SimilarityType = Literal["step_up", "alternative"]

EmbeddingType = Literal["full_profile", "tasting_notes", "community_sentiment"]


class _WriteBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# producers
# ---------------------------------------------------------------------------


class ProducerWrite(_WriteBase):
    # NOT NULL does not reject the empty string; min_length does.
    name: str = Field(min_length=1)

    # Corporate ownership: Sazerac -> Buffalo Trace. NULL means independent or
    # not yet researched -- a low-stakes ambiguity, unlike Product.bottler_id.
    parent_producer_id: UUID | None = None

    region: str | None = None
    country: str | None = None
    founded_year: int | None = Field(default=None, ge=1000, le=2100)

    # Full prose history, fetched on demand.
    description: str | None = None

    # One line of house style, short enough to inject alongside every product
    # in a retrieval result.
    signature_style: str | None = None


class Producer(ProducerWrite):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# products
# ---------------------------------------------------------------------------


class ProductWrite(_WriteBase):
    # --- Identity ---------------------------------------------------------
    # UNIQUE in the database: duplicate rows degrade resolve_bottle()'s fuzzy
    # matching, so store picks and limited releases need distinct names.
    canonical_name: str = Field(min_length=1)
    brand: str | None = None
    expression: str | None = None
    full_name: str | None = None

    # --- Producer and origin ----------------------------------------------
    #   bottler_id == distiller_id -> not sourced (confirmed)
    #   bottler_id != distiller_id -> sourced
    #   bottler_id is None         -> not yet researched, or contested
    distiller_id: UUID | None = None
    bottler_id: UUID | None = None
    region: str | None = None
    country: str | None = None

    # --- Classification ---------------------------------------------------
    vertical: Vertical
    category: Category
    subcategory: str | None = None

    # --- Spec sheet -------------------------------------------------------
    # `proof` is absent by design: it is GENERATED ALWAYS in Postgres, which
    # rejects direct writes. Accepting it here would let the API take a value
    # the database will refuse.
    abv_pct: Decimal | None = Field(default=None, ge=0, le=100)
    age_years: Decimal | None = Field(default=None, ge=0, le=100)
    age_statement: str | None = None

    # --- Pricing ----------------------------------------------------------
    msrp_usd: Decimal | None = Field(default=None, ge=0)
    typical_retail_low_usd: Decimal | None = Field(default=None, ge=0)
    typical_retail_high_usd: Decimal | None = Field(default=None, ge=0)
    secondary_market_low_usd: Decimal | None = Field(default=None, ge=0)
    secondary_market_high_usd: Decimal | None = Field(default=None, ge=0)
    pricing_notes: str | None = None

    # --- Releases ---------------------------------------------------------
    # Per-batch detail as a JSON array. The shape is a guideline only (see the
    # column comment in the migration); keys are deliberately not validated.
    releases: list[dict[str, Any]] | None = None

    # --- Availability -----------------------------------------------------
    # NULL scarcity_tier means "not yet assessed". Defaulting to 0 would make
    # every unresearched bottle silently claim to be always in stock.
    availability: Availability | None = None
    scarcity_tier: int | None = Field(default=None, ge=0, le=5)

    # --- Descriptive (drives semantic search) -----------------------------
    description: str | None = None
    tasting_notes: str | None = None
    community_sentiment: str | None = None

    # --- Ratings ----------------------------------------------------------
    whiskey_advocate_score: int | None = Field(default=None, ge=0, le=100)
    distiller_score: Decimal | None = Field(default=None, ge=0, le=100)
    # Intentionally schemaless so new sources do not require a migration.
    independent_review_scores: dict[str, Any] | None = None

    # --- Tags -------------------------------------------------------------
    # Open vocabularies, deliberately unconstrained.
    flavor_profile: list[str] = Field(default_factory=list)
    style_tags: list[str] = Field(default_factory=list)

    # --- Metadata ---------------------------------------------------------
    data_quality: DataQuality = "low"
    # Internal curation notes. Never surfaced in user-facing output.
    notes: str | None = None

    @model_validator(mode="after")
    def _check_scarcity_consistency(self) -> "ProductWrite":
        """Mirrors products_scarcity_consistency.

        Loose on purpose: only 'widely_available' constrains the tier.
        Discontinued and regional bottles are free to carry a high one --
        a discontinued cult bottle is genuinely hard to find.
        """
        if (
            self.availability == "widely_available"
            and self.scarcity_tier is not None
            and self.scarcity_tier != 0
        ):
            raise ValueError(
                "scarcity_tier must be 0 when availability is 'widely_available' "
                f"(got {self.scarcity_tier})"
            )
        return self

    @model_validator(mode="after")
    def _check_price_ranges(self) -> "ProductWrite":
        """Low bound must not exceed high bound.

        No database constraint covers this -- it is purely a guard against
        transposing the two while curating.
        """
        for low_field, high_field in (
            ("typical_retail_low_usd", "typical_retail_high_usd"),
            ("secondary_market_low_usd", "secondary_market_high_usd"),
        ):
            low, high = getattr(self, low_field), getattr(self, high_field)
            if low is not None and high is not None and low > high:
                raise ValueError(f"{low_field} ({low}) exceeds {high_field} ({high})")
        return self


class Product(ProductWrite):
    model_config = ConfigDict(extra="ignore")

    id: UUID

    # Generated by Postgres as abv_pct * 2. Read-only.
    proof: Decimal | None = None

    created_at: datetime
    updated_at: datetime

    # search_vector is deliberately absent: it is an internal full-text index,
    # and tsvector has no useful JSON representation.


# ---------------------------------------------------------------------------
# product_similarities
# ---------------------------------------------------------------------------


class SimilarityWrite(_WriteBase):
    """Curated market-role knowledge.

    CONVENTION: similarity_type describes what B is, RELATIVE TO A.
        (wild_turkey_101, buffalo_trace, 'step_up')
        reads: "Buffalo Trace is a step up from Wild Turkey 101"

    'step_down' is not a storable value -- it is a step_up row read backwards,
    derived at query time when the match lands on product_b_id. 'alternative'
    is symmetric and is found from either side.
    """

    product_a_id: UUID
    product_b_id: UUID
    similarity_type: SimilarityType
    notes: str | None = None

    @model_validator(mode="after")
    def _check_not_self(self) -> "SimilarityWrite":
        """Mirrors product_similarities_no_self."""
        if self.product_a_id == self.product_b_id:
            raise ValueError("product_a_id and product_b_id must differ")
        return self


class EmbeddingSync(BaseModel):
    """Outcome of an embedding refresh.

    `ok=False` means the product saved but embedding failed -- the row is
    durable either way, and the list view will show it as stale.
    """

    ok: bool
    written: int = 0
    removed: int = 0
    unchanged: int = 0
    error: str | None = None


class EmbeddingStatus(BaseModel):
    """Drives the indicator column. Computed without any API call."""

    current: list[str] = Field(default_factory=list)
    stale: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)


class ProductSaved(BaseModel):
    """Save response: the row, plus what happened to its embeddings."""

    product: "Product"
    embeddings: EmbeddingSync


class Similarity(SimilarityWrite):
    model_config = ConfigDict(extra="ignore")

    # No id field: the primary key is composite
    # (product_a_id, product_b_id, similarity_type).
    # No updated_at: the table does not carry one.
    created_at: datetime
