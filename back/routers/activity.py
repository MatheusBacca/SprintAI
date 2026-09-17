from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status

from database.pool import get_pool
from schemas.activity_schemas import ActivityFeedOut, ActivitySource
from security.credential_store import CredentialStore, get_credential_store
from services.activity import feed

router = APIRouter(tags=["activity"])

Pool = Annotated[asyncpg.Pool, Depends(get_pool)]
Store = Annotated[CredentialStore, Depends(get_credential_store)]


@router.get("/activity", response_model=ActivityFeedOut)
async def list_activity(
    pool: Pool,
    store: Store,
    cursor: Annotated[str | None, Query(max_length=128, description="da resposta anterior")] = None,
    limit: Annotated[int, Query(ge=1, le=feed.MAX_LIMIT)] = 30,
    source: ActivitySource | None = None,
    only_others: Annotated[bool, Query(description="esconde o que fui eu que fiz")] = False,
):
    """Feed de atividade do espelho (Jira e Bitbucket), do mais novo para o mais antigo."""
    try:
        return await feed.list_events(
            pool, store, cursor=cursor, limit=limit, source=source, only_others=only_others
        )
    except feed.InvalidCursor as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
