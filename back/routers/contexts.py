from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status

from database.pool import get_pool
from schemas.context_schemas import (
    ContextCountsOut,
    ContextCreate,
    ContextKind,
    ContextListOut,
    ContextOut,
    ContextStatus,
    ContextUpdate,
    IssueContextsOut,
    ResolveIn,
)
from schemas.pr_status_schemas import ISSUE_KEY_PATTERN
from security.credential_store import CredentialStore, get_credential_store
from services import contexts_service

router = APIRouter(tags=["contexts"])

Pool = Annotated[asyncpg.Pool, Depends(get_pool)]
Store = Annotated[CredentialStore, Depends(get_credential_store)]


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, detail="Contexto não encontrado.")


def _conflict(exc: Exception) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))


@router.get("/contexts", response_model=ContextListOut)
async def list_contexts(
    pool: Pool,
    store: Store,
    q: Annotated[str | None, Query(max_length=200)] = None,
    issue_key: Annotated[str | None, Query(pattern=ISSUE_KEY_PATTERN)] = None,
    kind: Annotated[list[ContextKind] | None, Query()] = None,
    context_status: Annotated[ContextStatus | None, Query(alias="status")] = None,
    tag: Annotated[list[str] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return await contexts_service.search(
        pool,
        store,
        q=q,
        issue_key=issue_key,
        kinds=kind,
        status=context_status,
        tags=[t.strip().lower() for t in tag] if tag else None,
        limit=limit,
        offset=offset,
    )


@router.get("/contexts/counts", response_model=ContextCountsOut)
async def context_counts(pool: Pool):
    return await contexts_service.counts(pool)


@router.get("/issues/{issue_key}/contexts", response_model=IssueContextsOut)
async def issue_contexts(
    pool: Pool, store: Store, issue_key: Annotated[str, Path(pattern=ISSUE_KEY_PATTERN)]
):
    return await contexts_service.for_issue(pool, store, issue_key)


@router.post("/contexts", response_model=ContextOut, status_code=status.HTTP_201_CREATED)
async def create_context(pool: Pool, store: Store, payload: ContextCreate):
    return await contexts_service.create(pool, store, payload)


@router.get("/contexts/{context_id}", response_model=ContextOut)
async def get_context(pool: Pool, store: Store, context_id: int):
    try:
        return await contexts_service.get(pool, store, context_id)
    except contexts_service.ContextNotFound as exc:
        raise _not_found() from exc


@router.patch("/contexts/{context_id}", response_model=ContextOut)
async def update_context(pool: Pool, store: Store, context_id: int, payload: ContextUpdate):
    try:
        return await contexts_service.update(pool, store, context_id, payload)
    except contexts_service.ContextNotFound as exc:
        raise _not_found() from exc
    except contexts_service.ContextConflict as exc:
        raise _conflict(exc) from exc


@router.delete("/contexts/{context_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_context(pool: Pool, context_id: int):
    try:
        await contexts_service.delete(pool, context_id)
    except contexts_service.ContextNotFound as exc:
        raise _not_found() from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/contexts/{context_id}/resolve", response_model=ContextOut)
async def resolve_context(pool: Pool, store: Store, context_id: int, payload: ResolveIn):
    try:
        return await contexts_service.resolve(pool, store, context_id, payload)
    except contexts_service.ContextNotFound as exc:
        raise _not_found() from exc
    except contexts_service.ContextConflict as exc:
        raise _conflict(exc) from exc


@router.post("/contexts/{context_id}/reopen", response_model=ContextOut)
async def reopen_context(pool: Pool, store: Store, context_id: int):
    try:
        return await contexts_service.reopen(pool, store, context_id)
    except contexts_service.ContextNotFound as exc:
        raise _not_found() from exc
