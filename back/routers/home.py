from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status

from database.pool import get_pool
from schemas.home_schemas import HomeOut, TimelineOut
from security.credential_store import CredentialStore, get_credential_store
from services import home_service, week_service

router = APIRouter(tags=["home"])

Pool = Annotated[asyncpg.Pool, Depends(get_pool)]
Store = Annotated[CredentialStore, Depends(get_credential_store)]
Timezone = Annotated[str | None, Query(max_length=64, description="fuso IANA do navegador")]


@router.get("/home", response_model=HomeOut)
async def get_home(pool: Pool, store: Store, tz: Timezone = None):
    """Painel do dia: progresso das sprints ativas, pendências da semana e lembretes."""
    try:
        return await home_service.get_home(pool, store, timezone=tz)
    except week_service.InvalidTimezone as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.get("/home/timeline", response_model=TimelineOut)
async def get_timeline(
    pool: Pool,
    store: Store,
    tz: Timezone = None,
    include_next: Annotated[bool, Query(description="mostra também a próxima sprint")] = True,
):
    """Faixas das sprints e as minhas tarefas agrupadas por pai, com barra por status."""
    try:
        return await home_service.get_timeline(pool, store, include_next=include_next, timezone=tz)
    except week_service.InvalidTimezone as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
