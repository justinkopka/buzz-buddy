"""Maps asyncpg constraint violations to meaningful HTTP responses.

Without these, a duplicate canonical_name reaches the admin UI as a bare 500.
Postgres already produces a precise message ("Key (canonical_name)=(Weller 12)
already exists."), so the handlers surface that rather than inventing one.
"""

from asyncpg import (
    CheckViolationError,
    ForeignKeyViolationError,
    NotNullViolationError,
    UniqueViolationError,
)
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


def _detail(request: Request, exc: Exception, fallback: str) -> str:
    """Postgres's own message for admin routes, the generic fallback elsewhere.

    The detail echoes row values ("Key (canonical_name)=(Weller 12)"), which is
    exactly what a curator needs and more than any other caller should see.
    """
    if not request.url.path.startswith("/admin/"):
        return fallback
    return getattr(exc, "detail", None) or getattr(exc, "message", None) or fallback


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(UniqueViolationError)
    async def _unique(request: Request, exc: UniqueViolationError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"detail": _detail(request, exc, "That record already exists.")},
        )

    @app.exception_handler(ForeignKeyViolationError)
    async def _foreign_key(
        request: Request, exc: ForeignKeyViolationError
    ) -> JSONResponse:
        # Direction matters. On DELETE the row is still referenced by others
        # (409, a conflict). On INSERT/UPDATE the submitted reference does not
        # exist (422, unprocessable content).
        deleting = request.method == "DELETE"
        return JSONResponse(
            status_code=409 if deleting else 422,
            content={
                "detail": _detail(
                    request,
                    exc,
                    "Still referenced by other records."
                    if deleting
                    else "Referenced record does not exist.",
                )
            },
        )

    @app.exception_handler(CheckViolationError)
    async def _check(request: Request, exc: CheckViolationError) -> JSONResponse:
        # A backstop. The Pydantic validators mirror these constraints and
        # should reject first with a friendlier message; reaching this means
        # the two have drifted apart.
        return JSONResponse(
            status_code=422,
            content={
                "detail": _detail(request, exc, "Value violates a database constraint.")
            },
        )

    @app.exception_handler(NotNullViolationError)
    async def _not_null(request: Request, exc: NotNullViolationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"detail": _detail(request, exc, "A required field was missing.")},
        )
