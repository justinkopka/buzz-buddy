import json
import os

import asyncpg
from pgvector.asyncpg import register_vector

_pool: asyncpg.Pool | None = None

async def _init_connection(conn: asyncpg.Connection) -> None:
    await conn.execute("SET search_path TO public, extensions")
    await register_vector(conn, schema="extensions")
    # asyncpg passes jsonb through as raw text in both directions: reads return
    # a str, and writes reject anything that is not already a str.
    await conn.set_type_codec(
        "jsonb", schema="pg_catalog", encoder=json.dumps, decoder=json.loads
    )


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=os.environ["DATABASE_URL"],
            min_size=1,
            max_size=2,
            init=_init_connection,
            statement_cache_size=0,
        )
    return _pool


_RETRYABLE = (
    asyncpg.PostgresConnectionError,
    asyncpg.IdleSessionTimeoutError,
    asyncpg.AdminShutdownError,
    asyncpg.InterfaceError,
    ConnectionError,
)


async def _read(method: str, sql: str, *args):
    """Reads are retried once on a dropped connection -- re-running is harmless."""
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            return await getattr(conn, method)(sql, *args)
    except _RETRYABLE:
        async with pool.acquire() as conn:
            return await getattr(conn, method)(sql, *args)


async def _write(method: str, sql: str, *args):
    """Writes are sent exactly once.

    A connection that drops after the server commits looks identical to one
    that drops before, so retrying the statement can repeat a write that
    already happened -- a duplicate producer, or a 409 for a save that worked.
    Instead the connection is checked with a round trip first: a stale pooled
    connection (the common case after Lambda sits idle) fails there and is
    replaced, and only a just-verified connection gets the write.
    """
    pool = await get_pool()
    for attempt in (1, 2):
        async with pool.acquire() as conn:
            try:
                await conn.execute("SELECT 1")
            except _RETRYABLE:
                if attempt == 2:
                    raise
                continue
            return await getattr(conn, method)(sql, *args)


async def fetch(sql: str, *args) -> list[asyncpg.Record]:
    return await _read("fetch", sql, *args)


async def fetchrow(sql: str, *args, write: bool = False) -> asyncpg.Record | None:
    """Pass write=True for INSERT/UPDATE ... RETURNING."""
    if write:
        return await _write("fetchrow", sql, *args)
    return await _read("fetchrow", sql, *args)


async def execute(sql: str, *args) -> str:
    """Always treated as a write -- every caller uses it for DML."""
    return await _write("execute", sql, *args)
