from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status

from database.pool import get_pool
from schemas.sprint_schemas import SprintSummaryOut, SprintTreeOut
from security.credential_store import CredentialStore, get_credential_store
from services import sprint_service

router = APIRouter(prefix="/sprints", tags=["sprints"])

Pool = Annotated[asyncpg.Pool, Depends(get_pool)]
Store = Annotated[CredentialStore, Depends(get_credential_store)]


@router.get("", response_model=list[SprintSummaryOut])
async def list_sprints(pool: Pool, store: Store):
    """Sprints do escopo espelhado: ativas, futuras e fechadas, com contagens."""
    return await sprint_service.list_sprints(pool, store)


@router.get("/{sprint_id}/tree", response_model=SprintTreeOut)
async def sprint_tree(pool: Pool, store: Store, sprint_id: int, only_mine: bool = False):
    try:
        return await sprint_service.sprint_tree(pool, store, sprint_id, only_mine=only_mine)
    except sprint_service.SprintNotFound as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Sprint não encontrada no espelho local."
        ) from exc
