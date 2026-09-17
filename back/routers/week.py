from datetime import date
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status

from database.pool import get_pool
from schemas.week_schemas import WeekOut
from security.credential_store import CredentialStore, get_credential_store
from services import week_service

router = APIRouter(tags=["week"])

Pool = Annotated[asyncpg.Pool, Depends(get_pool)]
Store = Annotated[CredentialStore, Depends(get_credential_store)]


@router.get("/week", response_model=WeekOut)
async def get_week(
    pool: Pool,
    store: Store,
    day: Annotated[date | None, Query(description="qualquer dia da semana; padrão: hoje")] = None,
    tz: Annotated[str | None, Query(max_length=64, description="fuso IANA do navegador")] = None,
):
    """Semana (segunda a domingo): minhas sem sprint, prazos, "Analisar e fatiar" e lembretes."""
    try:
        return await week_service.get_week(pool, store, day=day, timezone=tz)
    except week_service.InvalidTimezone as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
