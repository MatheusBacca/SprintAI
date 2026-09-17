from datetime import UTC, datetime
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status

from database.pool import get_pool
from repositories import bitbucket_repo, jira_repo, sync_repo
from schemas.sync_schemas import ScopeSprintOut, SyncRunOut, SyncStatusOut, SyncTriggerOut
from services.sync.engine import (
    SyncAlreadyRunning,
    SyncEngine,
    get_sync_engine,
    load_scope,
    save_scope,
)
from services.sync.scope import SyncScope

router = APIRouter(prefix="/sync", tags=["sync"])

Pool = Annotated[asyncpg.Pool, Depends(get_pool)]
Engine = Annotated[SyncEngine, Depends(get_sync_engine)]


@router.get("/scope", response_model=SyncScope)
async def get_scope(pool: Pool):
    return await load_scope(pool)


@router.put("/scope", response_model=SyncScope)
async def put_scope(scope: SyncScope, pool: Pool, engine: Engine):
    await save_scope(pool, scope)
    engine.reschedule()
    return scope


@router.get("/sprints", response_model=list[ScopeSprintOut])
async def get_scope_sprints(pool: Pool):
    """Sprints no escopo com a quantidade de tarefas espelhadas em cada uma."""
    return await jira_repo.scope_sprints(pool)


@router.get("/status", response_model=SyncStatusOut)
async def get_status(pool: Pool, engine: Engine):
    last = await sync_repo.latest_run(pool)
    last_success = await sync_repo.latest_run(pool, status="success")
    scope = await load_scope(pool)

    next_in = None
    if scope.enabled and not engine.running and last and last["finished_at"]:
        elapsed = (datetime.now(UTC) - last["finished_at"]).total_seconds()
        next_in = max(0, int(scope.interval_minutes * 60 - elapsed))

    return SyncStatusOut(
        running=engine.running,
        current_stage=engine.current_stage,
        current_run_id=engine.current_run_id,
        last_run=SyncRunOut(**last) if last else None,
        last_success_at=last_success["finished_at"] if last_success else None,
        next_run_in_seconds=next_in,
        counts={**await jira_repo.counts(pool), **await bitbucket_repo.counts(pool)},
    )


@router.post("", response_model=SyncTriggerOut, status_code=status.HTTP_202_ACCEPTED)
async def trigger_sync(engine: Engine):
    try:
        run_id = await engine.trigger("manual")
    except SyncAlreadyRunning as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Já existe uma sincronização em andamento."
        ) from exc
    return SyncTriggerOut(run_id=run_id)
