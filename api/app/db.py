"""Acceso a Postgres para la API: un pool pequeno y helpers de consulta."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import SimpleConnectionPool

_pool: SimpleConnectionPool | None = None


def _dsn() -> str:
    return (
        f"host={os.getenv('POSTGRES_HOST', 'postgres')} "
        f"port={os.getenv('POSTGRES_PORT', '5432')} "
        f"dbname={os.getenv('POSTGRES_DB', 'brandpulse')} "
        f"user={os.getenv('POSTGRES_USER', 'marketing')} "
        f"password={os.getenv('POSTGRES_PASSWORD', 'marketing')}"
    )


def init_pool(minconn: int = 1, maxconn: int = 8) -> None:
    global _pool
    if _pool is None:
        _pool = SimpleConnectionPool(minconn, maxconn, dsn=_dsn())


@contextmanager
def cursor() -> Iterator[RealDictCursor]:
    if _pool is None:
        init_pool()
    assert _pool is not None
    conn = _pool.getconn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


def query(sql: str, params: tuple | dict | None = None) -> list[dict[str, Any]]:
    with cursor() as cur:
        cur.execute(sql, params or ())
        return [dict(row) for row in cur.fetchall()]


def query_one(sql: str, params: tuple | dict | None = None) -> dict[str, Any] | None:
    rows = query(sql, params)
    return rows[0] if rows else None
