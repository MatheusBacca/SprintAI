from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends

from database.pool import get_pool
from schemas.notification_schemas import TaskUpdatesOut
from security.credential_store import CredentialStore, get_credential_store
from services import sprint_updates

router = APIRouter(prefix="/notifications", tags=["notifications"])

Pool = Annotated[asyncpg.Pool, Depends(get_pool)]
Store = Annotated[CredentialStore, Depends(get_credential_store)]


@router.get("/updates", response_model=TaskUpdatesOut)
async def task_updates(pool: Pool, store: Store):
    """Tarefas suas das sprints ativas que outra pessoa mexeu nas últimas 48h — o que o
    sino mostra ao lado dos lembretes vencidos. Os lembretes continuam vindo do
    `GET /api/notes/reminders/due`: são domínios diferentes, com ações diferentes."""
    return TaskUpdatesOut(updates=await sprint_updates.for_active_sprints(pool, store))
