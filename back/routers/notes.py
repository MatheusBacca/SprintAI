from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from database.pool import get_pool
from schemas.note_schemas import (
    ISSUE_KEY_PATTERN,
    DueFilter,
    NoteCreate,
    NoteListOut,
    NoteOut,
    NoteUpdate,
    SnoozeIn,
    TagCountOut,
)
from security.credential_store import CredentialStore, get_credential_store
from services import notes_service

router = APIRouter(prefix="/notes", tags=["notes"])

Pool = Annotated[asyncpg.Pool, Depends(get_pool)]
Store = Annotated[CredentialStore, Depends(get_credential_store)]


def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, detail="Lembrete não encontrado.")


@router.get("", response_model=NoteListOut)
async def list_notes(
    pool: Pool,
    store: Store,
    q: Annotated[str | None, Query(max_length=200)] = None,
    tag: Annotated[list[str] | None, Query()] = None,
    issue_key: Annotated[str | None, Query(pattern=ISSUE_KEY_PATTERN)] = None,
    pinned: bool | None = None,
    archived: Annotated[bool | None, Query(description="omitido = só ativos")] = False,
    include_archived: bool = False,
    due: DueFilter = "any",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return await notes_service.search(
        pool,
        store,
        q=q,
        tags=[t.strip().lower() for t in tag] if tag else None,
        issue_key=issue_key,
        pinned=pinned,
        archived=None if include_archived else archived,
        due=due,
        limit=limit,
        offset=offset,
    )


@router.get("/tags", response_model=list[TagCountOut])
async def list_tags(pool: Pool):
    return await notes_service.tags(pool)


@router.get("/reminders/due", response_model=list[NoteOut])
async def due_reminders(pool: Pool, store: Store):
    """Lembretes cujo horário chegou e ainda não foram vistos (notificação do front)."""
    return await notes_service.due(pool, store)


@router.post("", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
async def create_note(pool: Pool, store: Store, payload: NoteCreate):
    return await notes_service.create(pool, store, payload)


@router.get("/{note_id}", response_model=NoteOut)
async def get_note(pool: Pool, store: Store, note_id: int):
    try:
        return await notes_service.get(pool, store, note_id)
    except notes_service.NoteNotFound as exc:
        raise _not_found(exc) from exc


@router.patch("/{note_id}", response_model=NoteOut)
async def update_note(pool: Pool, store: Store, note_id: int, payload: NoteUpdate):
    try:
        return await notes_service.update(pool, store, note_id, payload)
    except notes_service.NoteNotFound as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(pool: Pool, note_id: int):
    try:
        await notes_service.delete(pool, note_id)
    except notes_service.NoteNotFound as exc:
        raise _not_found(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{note_id}/reminder/ack", response_model=NoteOut)
async def acknowledge_reminder(pool: Pool, store: Store, note_id: int):
    try:
        return await notes_service.acknowledge(pool, store, note_id)
    except notes_service.NoteNotFound as exc:
        raise _not_found(exc) from exc


@router.post("/{note_id}/reminder/snooze", response_model=NoteOut)
async def snooze_reminder(pool: Pool, store: Store, note_id: int, body: SnoozeIn):
    try:
        return await notes_service.snooze(pool, store, note_id, body.minutes)
    except notes_service.NoteNotFound as exc:
        raise _not_found(exc) from exc
