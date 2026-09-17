"""Bolinha de "teve atualização" nos cards do canvas da sprint.

Compara a foto que o dev viu por último (`issue_seen`) com o que o card mostra agora.
Só entram os campos que aparecem no card — status do Jira, etapa de PR, Story Points
e responsável —: mudança que o card não mostra acenderia uma bolinha que o dev não
consegue explicar olhando para ele.
"""

from typing import Any

import asyncpg

from repositories import issue_repo, seen_repo
from services import pr_status_service

FIELDS = ("status", "pr", "story_points", "assignee")


def snapshot(
    *,
    status: str | None,
    story_points: float | None,
    assignee_name: str | None,
    pr_status: str | None = None,
    with_pr: bool = True,
) -> dict[str, Any]:
    """Foto de um card. `with_pr=False` para card fora da sprint, que não calcula PR."""
    shot: dict[str, Any] = {
        "status": status,
        "story_points": float(story_points) if story_points is not None else None,
        "assignee": assignee_name,
    }
    if with_pr:
        shot["pr"] = pr_status
    return shot


def changed_fields(seen: dict[str, Any], current: dict[str, Any]) -> list[str]:
    """Campos que mudaram. Só compara o que as duas fotos têm — um card que entrou na
    sprint passa a ter PR, e isso não é atualização."""
    return [f for f in FIELDS if f in seen and f in current and seen[f] != current[f]]


async def unseen_changes(
    pool: asyncpg.Pool, current_by_key: dict[str, dict[str, Any]]
) -> dict[str, list[str]]:
    """O que mudou em cada card desde a última visita. Card sem foto ganha a primeira
    agora, apagado: sem isso a primeira abertura do canvas acenderia todos."""
    seen = await seen_repo.snapshots(pool, current_by_key)
    await seen_repo.insert_missing(
        pool, {k: shot for k, shot in current_by_key.items() if k not in seen}
    )
    return {k: changed_fields(seen[k], shot) for k, shot in current_by_key.items() if k in seen}


async def mark_seen(pool: asyncpg.Pool, issue_key: str) -> bool:
    """Refaz a foto com o estado atual do espelho. `False` se a tarefa não está nele."""
    row = await issue_repo.issue(pool, issue_key)
    if row is None:
        return False
    summaries = await pr_status_service.summaries(pool, [issue_key])
    await seen_repo.upsert(
        pool,
        issue_key,
        snapshot(
            status=row["status"],
            story_points=row["story_points"],
            assignee_name=row["assignee_name"],
            pr_status=summaries[issue_key].status,
        ),
    )
    return True
