"""Feed da Home: eventos do espelho, do mais novo para o mais antigo.

A paginação é por cursor `(occurred_at, id)` e não por offset: o sync insere eventos
o tempo todo, e offset faria a página 2 repetir ou pular linhas.
"""

import base64
import binascii
from datetime import datetime

import asyncpg

from repositories import activity_repo
from schemas.activity_schemas import ActivityEventOut, ActivityFeedOut
from security.credential_store import CredentialStore
from services.sprint_service import jira_identity

MAX_LIMIT = 100


class InvalidCursor(ValueError):
    pass


def encode_cursor(occurred_at: datetime, event_id: int) -> str:
    raw = f"{occurred_at.isoformat()}|{event_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, int]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        occurred_at, event_id = base64.urlsafe_b64decode(padded).decode().rsplit("|", 1)
        return datetime.fromisoformat(occurred_at), int(event_id)
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise InvalidCursor("Cursor inválido.") from exc


async def list_events(
    pool: asyncpg.Pool,
    store: CredentialStore,
    *,
    cursor: str | None = None,
    limit: int = 30,
    source: str | None = None,
    only_others: bool = False,
) -> ActivityFeedOut:
    limit = max(1, min(limit, MAX_LIMIT))
    before = decode_cursor(cursor) if cursor else None
    # Uma linha a mais só para saber se existe próxima página.
    rows = await activity_repo.feed(
        pool, before=before, limit=limit + 1, source=source, only_others=only_others
    )
    has_more = len(rows) > limit
    rows = rows[:limit]

    _, site_url = jira_identity(store)
    browse = f"{site_url.rstrip('/')}/browse/" if site_url else None

    events = [
        ActivityEventOut(
            id=row["id"],
            source=row["source"],
            kind=row["kind"],
            issue_key=row["issue_key"],
            issue_summary=row["issue_summary"],
            issue_status=row["issue_status"],
            issue_url=f"{browse}{row['issue_key']}" if browse and row["issue_key"] else None,
            repo_slug=row["repo_slug"],
            pr_id=row["pr_id"],
            pr_url=(row["detail"] or {}).get("url"),
            actor_name=row["actor_name"],
            actor_is_me=row["actor_is_me"],
            occurred_at=row["occurred_at"],
            title=row["title"],
            detail=row["detail"] or {},
        )
        for row in rows
    ]
    next_cursor = (
        encode_cursor(rows[-1]["occurred_at"], rows[-1]["id"]) if has_more and rows else None
    )
    return ActivityFeedOut(events=events, next_cursor=next_cursor)
