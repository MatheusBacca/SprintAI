"""Tarefas da sprint em que outra pessoa mexeu há pouco.

A mesma regra alimenta dois lugares — a linha "Mexeram nestas" de cada sprint da Home e
as notificações de tarefa do sino —, por isso ela mora aqui e não dentro do `home_service`.

"Mexeram na minha tarefa enquanto eu não estava olhando": só o que **outra pessoa** fez,
nas minhas tarefas. O que eu mesmo faço não é novidade para mim.
"""

from datetime import UTC, datetime, timedelta

import asyncpg

from repositories import activity_repo, progress_repo
from schemas.notification_schemas import TaskUpdateOut
from schemas.progress_schemas import SprintUpdateOut
from security.credential_store import CredentialStore
from services.sprint_service import jira_identity

WINDOW = timedelta(hours=48)
# Teto por sprint: a linha da Home rola, e o painel do sino não é um feed de atividade.
MAX_UPDATES = 12


def browse_url(site_url: str | None) -> str | None:
    return f"{site_url.rstrip('/')}/browse/" if site_url else None


async def by_sprint(
    pool: asyncpg.Pool,
    sprint_ids: list[int],
    *,
    account_id: str | None,
    since: datetime,
    browse: str | None,
) -> dict[int, list[SprintUpdateOut]]:
    """Uma linha por tarefa mexida, agrupada por sprint, da mais recente para a mais antiga."""
    if not sprint_ids:
        return {}
    rows = await activity_repo.recent_by_sprint(
        pool, sprint_ids, since=since, account_id=account_id, only_others=True
    )
    result: dict[int, list[SprintUpdateOut]] = {}
    for row in rows:
        cards = result.setdefault(row["sprint_id"], [])
        if len(cards) >= MAX_UPDATES:
            continue
        points = row["story_points"]
        cards.append(
            SprintUpdateOut(
                key=row["issue_key"],
                summary=row["summary"],
                status=row["status"],
                status_category=row["status_category"],
                story_points=float(points) if points is not None else None,
                url=f"{browse}{row['issue_key']}" if browse else None,
                kind=row["kind"],
                source=row["source"],
                title=row["title"],
                actor_name=row["actor_name"],
                occurred_at=row["occurred_at"],
                event_count=row["event_count"],
            )
        )
    return result


async def for_active_sprints(
    pool: asyncpg.Pool, store: CredentialStore, *, now: datetime | None = None
) -> list[TaskUpdateOut]:
    """O que o sino mostra: as sprints **ativas** do escopo numa lista só, da mexida mais
    recente para a mais antiga. O sino não agrupa por sprint como a Home — é uma caixa de
    novidades, e o nome da sprint vai dentro de cada uma."""
    account_id, site_url = jira_identity(store)
    sprints = await progress_repo.timeline_sprints(pool, include_next=False)
    names = {s["id"]: s["name"] for s in sprints}
    grouped = await by_sprint(
        pool,
        list(names),
        account_id=account_id,
        since=(now or datetime.now(UTC)) - WINDOW,
        browse=browse_url(site_url),
    )
    updates = [
        TaskUpdateOut(**update.model_dump(), sprint_id=sprint_id, sprint_name=names[sprint_id])
        for sprint_id, rows in grouped.items()
        for update in rows
    ]
    return sorted(updates, key=lambda u: u.occurred_at, reverse=True)
