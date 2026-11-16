"""The agent's tools: what Claude can call, and how the calls are executed.

A thin layer over retrieval.py that owns everything specific to talking to the
model -- schemas, input validation, serialization, and deciding which fields
the model sees. retrieval.py stays usable without any of it.

execute_tool never raises for a bad call. Every failure comes back as an error
result, because Claude can usually read one and correct itself, whereas an
exception would end the whole request.

Tool definitions leave `eager_input_streaming` off on purpose. It exists for
large tool inputs, these are a few short fields, and turning it on would give
up the API's own validation of them.
"""

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app import retrieval
from app.schemas import Category

logger = logging.getLogger(__name__)

# Removed from what the model reads. They stay in ToolOutcome.raw, so traces
# and evals can still see why a bottle ranked where it did.
_NOT_FOR_MODEL = frozenset(
    {
        # Ranking internals: the model judges relevance by reading the bottle.
        "rrf_score",
        "semantic_rank",
        "semantic_distance",
        "semantic_match",
        "name_rank",
        "prose_rank",
        "match_score",
        # Bookkeeping. Producer ids are replaced by the resolved names.
        "created_at",
        "updated_at",
        "distiller_id",
        "bottler_id",
        "vertical",
    }
)


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


class _ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchWhiskeyInput(_ToolInput):
    query: str = Field(
        min_length=1,
        description=(
            "What the user is looking for, in natural language: flavors, style, "
            "occasion, or similar. Do not repeat the numeric filters here."
        ),
    )
    categories: list[Category] | None = Field(
        default=None, description="Only return these whiskey categories."
    )
    min_price: float | None = Field(
        default=None, ge=0, description="Lowest price in USD the user wants."
    )
    max_price: float | None = Field(
        default=None, ge=0, description="The user's budget in USD."
    )
    min_proof: float | None = Field(default=None, ge=0, description="Lowest proof.")
    max_proof: float | None = Field(default=None, ge=0, description="Highest proof.")
    exclude_product_ids: list[UUID] | None = Field(
        default=None,
        description=(
            "Product ids to leave out. Use only when the user wants something new "
            "and has named bottles they already own. Get ids by resolving the "
            "bottles they named with resolve_bottle."
        ),
    )


class ResolveBottleInput(_ToolInput):
    name: str = Field(min_length=1, description="The bottle name as the user wrote it.")


class ProductIdInput(_ToolInput):
    product_id: UUID = Field(
        description="A product id from a search_whiskey or resolve_bottle result."
    )


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _decimal(value: float | None) -> Decimal | None:
    # Through str, so 49.99 stays 49.99 rather than the float's binary expansion.
    return None if value is None else Decimal(str(value))


async def _search_whiskey(args: SearchWhiskeyInput) -> dict[str, Any]:
    results = await retrieval.hybrid_search(
        args.query,
        categories=args.categories,
        min_price=_decimal(args.min_price),
        max_price=_decimal(args.max_price),
        min_proof=_decimal(args.min_proof),
        max_proof=_decimal(args.max_proof),
        exclude_ids=args.exclude_product_ids,
    )
    return {"results": results}


async def _resolve_bottle(args: ResolveBottleInput) -> dict[str, Any]:
    return await retrieval.resolve_bottle(args.name)


async def _get_bottle_details(args: ProductIdInput) -> dict[str, Any]:
    product = await retrieval.get_details(args.product_id)
    # Not an error: "that bottle is not in the knowledge base" is a real answer.
    return {"status": "not_found"} if product is None else product


async def _get_related_bottles(args: ProductIdInput) -> dict[str, Any]:
    return {"related": await retrieval.get_related(args.product_id)}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Tool:
    description: str
    input_model: type[_ToolInput]
    handler: Callable[[Any], Awaitable[dict[str, Any]]]


_TOOLS: dict[str, _Tool] = {
    "search_whiskey": _Tool(
        description=(
            "Search the knowledge base for whiskey of any category, including "
            "bourbon, rye, and scotch, matching a description, within optional "
            "price, proof, and category limits. Use this to find bottles to "
            "recommend."
        ),
        input_model=SearchWhiskeyInput,
        handler=_search_whiskey,
    ),
    "resolve_bottle": _Tool(
        description=(
            "Look up a specific bottle the user named. Returns a status: 'resolved' "
            "means one confident match, 'ambiguous' means several plausible matches "
            "that may not be the bottle named, and 'not_found' means the bottle is "
            "not in the knowledge base. When 'ambiguous', ask which one they mean, "
            "or cover the likely candidates if the difference matters. A match "
            "found by meaning rather than by name (method: semantic) may not be "
            "the bottle named; treat it as a related bottle, not the same one."
        ),
        input_model=ResolveBottleInput,
        handler=_resolve_bottle,
    ),
    "get_bottle_details": _Tool(
        description="Get the full record for one bottle by product id.",
        input_model=ProductIdInput,
        handler=_get_bottle_details,
    ),
    "get_related_bottles": _Tool(
        description=(
            "Get curated relationships for one bottle by product id: step_up, "
            "step_down, and alternative. relation_notes explains each one."
        ),
        input_model=ProductIdInput,
        handler=_get_related_bottles,
    ),
}

# Built once, in a fixed order: this list is part of the prompt cache prefix,
# and it must not change between the turns of a request.
TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": name,
        "description": tool.description,
        "input_schema": tool.input_model.model_json_schema(),
    }
    for name, tool in _TOOLS.items()
]


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolOutcome:
    """content is what the model reads; raw is the full result, for traces."""

    content: str
    is_error: bool = False
    raw: Any = None


def _for_model(value: Any) -> Any:
    """Drop internal fields and nulls: an absent field reads as "not known"."""
    if isinstance(value, dict):
        return {
            k: _for_model(v)
            for k, v in value.items()
            if k not in _NOT_FOR_MODEL and v is not None
        }
    if isinstance(value, list):
        return [_for_model(v) for v in value]
    return value


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


def _error(message: str) -> ToolOutcome:
    return ToolOutcome(content=message, is_error=True)


async def execute_tool(name: str, tool_input: Any) -> ToolOutcome:
    tool = _TOOLS.get(name)
    if tool is None:
        return _error(f"Unknown tool {name!r}. Valid tools: {', '.join(_TOOLS)}.")

    try:
        args = tool.input_model.model_validate(tool_input)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in e['loc']) or 'input'}: {e['msg']}"
            for e in exc.errors()
        )
        return _error(f"Invalid input for {name}: {problems}")

    try:
        raw = await tool.handler(args)
    except ValueError as exc:
        # retrieval's own contract errors, written to be read.
        return _error(str(exc))
    except Exception:  # noqa: BLE001 - deliberate: a failed tool must not end the turn
        # The detail stays in the logs: driver and network errors can carry
        # connection strings, and the model may repeat what it reads.
        logger.exception("Tool %s failed", name)
        return _error(f"{name} failed. The knowledge base could not be reached.")

    return ToolOutcome(
        content=json.dumps(_for_model(raw), default=_json_default, ensure_ascii=False),
        raw=raw,
    )
