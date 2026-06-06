"""Async client + connection-pool management for chronos-mem.

``ChronosClient`` owns a single ``psycopg_pool.AsyncConnectionPool`` and exposes
the tracking verbs (via ``TrackingMixin``). Open it once per process and share it;
the pool multiplexes concurrent agent calls over a bounded set of connections.

    async with ChronosClient(dsn="postgresql://chronos:chronos@localhost/chronos_mem") as db:
        plan = await db.create_plan(agent_id="a1", goal="...")
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from psycopg import AsyncCursor
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from .causality import CausalityMixin
from .interventions import InterventionMixin
from .tracking import TrackingMixin

# Read from the environment when no DSN is passed explicitly.
_DSN_ENV_VAR = "CHRONOS_DSN"


class ChronosClient(TrackingMixin, CausalityMixin, InterventionMixin):
    """A pooled, async entrypoint to a chronos-mem database."""

    def __init__(
        self,
        dsn: str | None = None,
        *,
        min_size: int = 1,
        max_size: int = 10,
        timeout: float = 5.0,
    ) -> None:
        resolved = dsn or os.getenv(_DSN_ENV_VAR)
        if not resolved:
            raise ValueError(
                "No DSN provided. Pass dsn=... or set the "
                f"{_DSN_ENV_VAR} environment variable."
            )
        self._dsn = resolved
        # open=False: defer real connections until open()/__aenter__, so
        # constructing a client never does blocking I/O.
        self._pool: AsyncConnectionPool = AsyncConnectionPool(
            conninfo=resolved,
            min_size=min_size,
            max_size=max_size,
            timeout=timeout,
            kwargs={"row_factory": dict_row},
            open=False,
        )

    # -- lifecycle -----------------------------------------------------------

    async def open(self) -> "ChronosClient":
        """Open the pool and wait until the minimum connections are ready."""
        await self._pool.open(wait=True)
        return self

    async def close(self) -> None:
        """Drain and close every pooled connection. Idempotent."""
        await self._pool.close()

    async def __aenter__(self) -> "ChronosClient":
        return await self.open()

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    # -- low-level query helpers --------------------------------------------

    @asynccontextmanager
    async def _cursor(self) -> AsyncIterator[AsyncCursor[dict[str, Any]]]:
        """Check out one pooled connection and yield a cursor on it.

        A single checkout per logical operation keeps pool pressure low under
        high concurrency; multi-statement reads (e.g. the two causal-trace CTEs)
        share one connection — and one transactional snapshot — instead of
        contending for the pool twice. The connection commits on clean exit.
        """
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                yield cur

    async def _fetchrow(self, query: str, params: Any) -> dict[str, Any]:
        """Execute a single-row-returning statement and return that row as a dict.

        Used by the tracking verbs for ``INSERT ... RETURNING *``.
        """
        async with self._cursor() as cur:
            await cur.execute(query, params)
            row = await cur.fetchone()
        if row is None:
            raise RuntimeError("Expected a returned row but the statement produced none.")
        return row

    async def _fetch(self, query: str, params: Any) -> list[dict[str, Any]]:
        """Execute a read query and return all rows as dicts."""
        async with self._cursor() as cur:
            await cur.execute(query, params)
            return await cur.fetchall()

    async def ping(self) -> bool:
        """Cheap liveness check — returns True if the pool can serve a query."""
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1 AS ok")
                row = await cur.fetchone()
        return bool(row and row.get("ok") == 1)
