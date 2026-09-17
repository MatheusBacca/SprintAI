from datetime import datetime
from typing import Any

import asyncpg

Executor = asyncpg.Connection | asyncpg.Pool


async def start_run(conn: Executor, trigger: str) -> int:
    return await conn.fetchval(
        "INSERT INTO sync_run (trigger, status) VALUES ($1, 'running') RETURNING id", trigger
    )


async def finish_run(
    conn: Executor, run_id: int, *, status: str, stats: dict[str, Any], errors: list[dict]
) -> None:
    await conn.execute(
        """
        UPDATE sync_run SET status = $2, stats = $3, errors = $4, finished_at = now()
        WHERE id = $1
        """,
        run_id,
        status,
        stats,
        errors,
    )


async def abandon_running(conn: Executor) -> None:
    """Execuções que ficaram 'running' porque a API foi derrubada no meio."""
    await conn.execute(
        """
        UPDATE sync_run SET status = 'failed', finished_at = now(),
            errors = errors || '[{"stage": "engine", "message": "API reiniciada durante o sync."}]'
        WHERE status = 'running'
        """
    )


async def latest_run(conn: Executor, *, status: str | None = None) -> dict[str, Any] | None:
    if status:
        row = await conn.fetchrow(
            "SELECT * FROM sync_run WHERE status = $1 ORDER BY started_at DESC LIMIT 1", status
        )
    else:
        row = await conn.fetchrow("SELECT * FROM sync_run ORDER BY started_at DESC LIMIT 1")
    return dict(row) if row else None


async def get_state(conn: Executor, resource: str) -> dict[str, Any]:
    row = await conn.fetchrow(
        "SELECT last_success_at, cursor FROM sync_state WHERE resource = $1", resource
    )
    return dict(row) if row else {"last_success_at": None, "cursor": {}}


async def set_state(
    conn: Executor, resource: str, *, cursor: dict[str, Any], success_at: datetime
) -> None:
    await conn.execute(
        """
        INSERT INTO sync_state (resource, last_success_at, cursor) VALUES ($1, $2, $3)
        ON CONFLICT (resource) DO UPDATE SET last_success_at = EXCLUDED.last_success_at,
            cursor = EXCLUDED.cursor
        """,
        resource,
        success_at,
        cursor,
    )
