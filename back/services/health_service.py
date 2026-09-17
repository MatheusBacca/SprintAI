from config import get_settings
from database.pool import get_pool
from schemas.health_schemas import DatabaseHealth, HealthResponse

REQUIRED_EXTENSIONS = ("vector", "unaccent", "pg_trgm")


async def check_database() -> DatabaseHealth:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT extname FROM pg_extension WHERE extname = ANY($1::text[])",
                list(REQUIRED_EXTENSIONS),
            )
    except Exception as exc:  # banco fora do ar não derruba o health
        return DatabaseHealth(status="down", detail=type(exc).__name__)
    return DatabaseHealth(status="up", extensions=sorted(r["extname"] for r in rows))


async def get_health() -> HealthResponse:
    settings = get_settings()
    database = await check_database()
    return HealthResponse(
        app=settings.app_name,
        version=settings.app_version,
        status="ok" if database.status == "up" else "degraded",
        database=database,
    )
