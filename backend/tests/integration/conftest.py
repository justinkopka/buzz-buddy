"""Integration fixtures: a real Postgres, no real OpenAI.

The database is the local Supabase stack, loaded with a copy of production
data (`npx supabase db reset` after dumping to supabase/seed.sql). Tests read
whatever bottles are there, so assertions are written against behavior and
predicates rather than exact result lists -- curating a new bottle should not
break them.

Two guards run before anything else:
  - DATABASE_URL is overwritten with a localhost URL. backend/.env points at
    the hosted project, and nothing here may ever run against it.
  - Every path to OpenAI is replaced with a function that fails the test.
    Tests that need a query vector supply one with `query_vector`, usually a
    vector already stored in product_embeddings.
"""

import os
from urllib.parse import urlparse

import pytest
import pytest_asyncio

LOCAL_DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:55322/postgres"

_url = os.environ.get("TEST_DATABASE_URL", LOCAL_DATABASE_URL)
if urlparse(_url).hostname not in {"localhost", "127.0.0.1", "::1"}:
    pytest.exit(
        f"TEST_DATABASE_URL must point at localhost, got {urlparse(_url).hostname!r}. "
        "Integration tests write fixture rows and must never touch production.",
        returncode=2,
    )
# Set before app.db is imported anywhere: get_pool() reads it lazily, but a
# DATABASE_URL already exported in the shell must never win.
os.environ["DATABASE_URL"] = _url

from app import db, embeddings  # noqa: E402

EMBEDDING_DIMENSIONS = embeddings.EMBEDDING_DIMENSIONS

# A unit vector along one axis. Real embeddings spread their weight across all
# 1536 dimensions, so this sits at cosine distance ~1.0 from every product --
# far past SEMANTIC_CEILING, and gives the semantic arm no real preference.
FAR_VECTOR = [1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 1)


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def database():
    """Fails fast with instructions if the local stack is not running.

    Session-scoped on a session event loop because db._pool is a module
    global: a pool created on one test's loop cannot be used from another's.
    """
    try:
        await db.fetch("SELECT 1")
    except (OSError, ConnectionError) as exc:
        pytest.skip(f"local Supabase is not reachable ({exc}); run `npx supabase start`")
    yield
    if db._pool is not None:
        await db._pool.close()
        db._pool = None


@pytest.fixture(autouse=True)
def no_openai(monkeypatch):
    """Tests are free and deterministic: any attempt to embed fails loudly."""

    async def refuse(*args, **kwargs):
        raise AssertionError("test attempted an OpenAI embedding call")

    monkeypatch.setattr(embeddings, "_embed", refuse)
    monkeypatch.setattr(embeddings, "embed_query", refuse)


@pytest.fixture
def query_vector(monkeypatch):
    """Make embed_query return a chosen vector, and record what it was asked.

    Usage: calls = query_vector(vector); ...; assert calls == ["text"]
    """

    def install(vector) -> list[str]:
        calls: list[str] = []

        async def fake(text: str):
            calls.append(text)
            return vector

        monkeypatch.setattr(embeddings, "embed_query", fake)
        return calls

    return install


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def products(database) -> list[dict]:
    """Every whiskey product in the local copy, including fields retrieval hides.

    Expected results are computed from this in Python, independently of the
    SQL under test.
    """
    rows = await db.fetch(
        "SELECT p.*, "
        "  (SELECT count(*) FROM product_embeddings e WHERE e.product_id = p.id) "
        "  AS embedding_count "
        "FROM products p WHERE vertical = 'whiskey' ORDER BY canonical_name"
    )
    found = [dict(r) for r in rows]
    if not found:
        pytest.skip("local database has no products; dump and `npx supabase db reset`")
    return found


@pytest.fixture
def product_named(products):
    """Look up a pilot bottle by canonical_name, skipping if it was renamed."""

    def lookup(name: str) -> dict:
        for p in products:
            if p["canonical_name"] == name:
                return p
        pytest.skip(f"{name!r} is not in the local knowledge base")

    return lookup


@pytest.fixture
def stored_vector():
    """Fetch a vector already in product_embeddings, to use as a query vector.

    Querying with a product's own vector is the deterministic stand-in for a
    real embedding: that product must come back at distance ~0.
    """

    async def fetch(product_id, embedding_type: str = "full_profile"):
        row = await db.fetchrow(
            "SELECT embedding FROM product_embeddings "
            "WHERE product_id = $1 AND embedding_type = $2",
            product_id,
            embedding_type,
        )
        if row is None:
            pytest.skip(f"product {product_id} has no {embedding_type} embedding")
        return row["embedding"]

    return fetch
