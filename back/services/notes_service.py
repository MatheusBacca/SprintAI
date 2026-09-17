from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg

from realtime import bus
from repositories import notes_repo
from schemas.note_schemas import (
    LinkedIssueOut,
    NoteCreate,
    NoteListOut,
    NoteOut,
    NoteUpdate,
    TagCountOut,
)
from security.credential_store import CredentialStore
from services.sprint_service import jira_identity


class NoteNotFound(Exception):
    pass


async def hydrate(
    pool: asyncpg.Pool, store: CredentialStore, rows: list[dict[str, Any]]
) -> list[NoteOut]:
    _, site_url = jira_identity(store)
    issues = await notes_repo.linked_issues(pool, [r["id"] for r in rows]) if rows else {}
    browse = f"{site_url.rstrip('/')}/browse/" if site_url else None
    return [
        NoteOut(
            **row,
            issues=[
                LinkedIssueOut(**i, url=f"{browse}{i['key']}" if browse else None)
                for i in issues.get(row["id"], [])
            ],
        )
        for row in rows
    ]


async def get(pool: asyncpg.Pool, store: CredentialStore, note_id: int) -> NoteOut:
    row = await notes_repo.get(pool, note_id)
    if row is None:
        raise NoteNotFound(note_id)
    return (await hydrate(pool, store, [row]))[0]


async def create(pool: asyncpg.Pool, store: CredentialStore, payload: NoteCreate) -> NoteOut:
    async with pool.acquire() as conn, conn.transaction():
        note_id = await notes_repo.create(conn, payload.model_dump())
        await notes_repo.replace_issue_keys(conn, note_id, payload.issue_keys)
    bus.publish(bus.NOTE_CHANGED, {"id": note_id, "action": "created"})
    return await get(pool, store, note_id)


async def update(
    pool: asyncpg.Pool, store: CredentialStore, note_id: int, payload: NoteUpdate
) -> NoteOut:
    changes = payload.model_dump(exclude_unset=True)
    issue_keys = changes.pop("issue_keys", None)
    try:
        async with pool.acquire() as conn, conn.transaction():
            if not await notes_repo.update(conn, note_id, changes):
                raise NoteNotFound(note_id)
            if issue_keys is not None:
                await notes_repo.replace_issue_keys(conn, note_id, issue_keys)
    except asyncpg.CheckViolationError as exc:
        # CHECK (title <> '' OR body <> ''): a edição deixaria o lembrete vazio.
        raise ValueError("Escreva um título ou um texto para o lembrete.") from exc
    bus.publish(bus.NOTE_CHANGED, {"id": note_id, "action": "updated"})
    return await get(pool, store, note_id)


async def delete(pool: asyncpg.Pool, note_id: int) -> None:
    if not await notes_repo.delete(pool, note_id):
        raise NoteNotFound(note_id)
    bus.publish(bus.NOTE_CHANGED, {"id": note_id, "action": "deleted"})


async def search(pool: asyncpg.Pool, store: CredentialStore, **filters: Any) -> NoteListOut:
    rows, total = await notes_repo.search(pool, **filters)
    return NoteListOut(items=await hydrate(pool, store, rows), total=total)


async def tags(pool: asyncpg.Pool) -> list[TagCountOut]:
    return [TagCountOut(**r) for r in await notes_repo.tag_counts(pool)]


async def due(pool: asyncpg.Pool, store: CredentialStore) -> list[NoteOut]:
    return await hydrate(pool, store, await notes_repo.due_reminders(pool))


async def acknowledge(pool: asyncpg.Pool, store: CredentialStore, note_id: int) -> NoteOut:
    if not await notes_repo.acknowledge(pool, note_id):
        raise NoteNotFound(note_id)
    bus.publish(bus.NOTE_CHANGED, {"id": note_id, "action": "acknowledged"})
    return await get(pool, store, note_id)


async def snooze(pool: asyncpg.Pool, store: CredentialStore, note_id: int, minutes: int) -> NoteOut:
    until = datetime.now(UTC) + timedelta(minutes=minutes)
    if not await notes_repo.snooze(pool, note_id, until):
        raise NoteNotFound(note_id)
    bus.publish(bus.NOTE_CHANGED, {"id": note_id, "action": "snoozed"})
    return await get(pool, store, note_id)
