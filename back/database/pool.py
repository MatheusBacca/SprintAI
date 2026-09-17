"""Pool asyncpg compartilhado.

A API sobe mesmo com o banco fora do ar (Docker parado é comum numa máquina de dev):
o pool é criado sob demanda e o `/api/health` reporta o estado.
"""

import asyncio
import json

import asyncpg

from config import get_settings
from core.logger import get_logger

logger = get_logger(__name__)

_pool: asyncpg.Pool | None = None
_lock = asyncio.Lock()


class DatabaseUnavailable(Exception):
    """Postgres local fora do ar (container parado, porta errada...)."""


async def init_connection(conn: asyncpg.Connection) -> None:
    for type_name in ("json", "jsonb"):
        await conn.set_type_codec(
            type_name, encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
        )


async def create_pool(dsn: str, *, min_size: int = 1, max_size: int = 10) -> asyncpg.Pool:
    try:
        return await asyncpg.create_pool(
            dsn=dsn, min_size=min_size, max_size=max_size, timeout=5, init=init_connection
        )
    except (TimeoutError, OSError, asyncpg.PostgresError) as exc:
        raise DatabaseUnavailable(
            "Banco local indisponível — suba o Docker (docker compose up -d db)."
        ) from exc


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        async with _lock:
            if _pool is None:
                settings = get_settings()
                _pool = await create_pool(
                    settings.asyncpg_dsn,
                    min_size=settings.db_pool_min,
                    max_size=settings.db_pool_max,
                )
                logger.info("Pool do Postgres criado")
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("Pool do Postgres fechado")
