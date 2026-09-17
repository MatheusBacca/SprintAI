from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, Query

from database.pool import get_pool
from schemas.search_schemas import SearchOut, SearchPeriod, SearchType
from security.credential_store import CredentialStore, get_credential_store
from services import search_service

router = APIRouter(tags=["search"])

Pool = Annotated[asyncpg.Pool, Depends(get_pool)]
Store = Annotated[CredentialStore, Depends(get_credential_store)]


@router.get("/search", response_model=SearchOut)
async def global_search(
    pool: Pool,
    store: Store,
    q: Annotated[str, Query(max_length=200)],
    search_type: Annotated[list[SearchType] | None, Query(alias="type")] = None,
    period: SearchPeriod = "any",
    limit: Annotated[int, Query(ge=1, le=50, description="itens por tipo")] = 5,
    offset: Annotated[int, Query(ge=0, description="só com um único tipo")] = 0,
):
    """Busca em tarefas, comentários, PRs, contextos e lembretes, agrupada por tipo."""
    return await search_service.search(
        pool,
        store,
        q=q,
        types=search_type,
        period=period,
        limit=limit,
        offset=offset if search_type and len(search_type) == 1 else 0,
    )
