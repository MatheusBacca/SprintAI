from typing import Any

import asyncpg


async def get_setting(conn: asyncpg.Connection | asyncpg.Pool, key: str) -> Any | None:
    return await conn.fetchval("SELECT value FROM app_setting WHERE key = $1", key)


async def set_setting(conn: asyncpg.Connection | asyncpg.Pool, key: str, value: Any) -> None:
    await conn.execute(
        """
        INSERT INTO app_setting (key, value, updated_at) VALUES ($1, $2, now())
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
        """,
        key,
        value,
    )
