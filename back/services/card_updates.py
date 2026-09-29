"""Bolinha de "teve atualização" nos cards do canvas da sprint.

Compara a foto que o dev viu por último (`issue_seen`) com o que o card mostra agora.
Só entram os campos que aparecem no card — status do Jira, etapa de PR, aprovações do
PR, Story Points e responsável —: mudança que o card não mostra acenderia uma bolinha
que o dev não consegue explicar olhando para ele.
"""

from typing import Any

import asyncpg

from repositories import issue_repo, seen_repo
from services import pr_status_service
from services.pr_status import ReviewProgress

FIELDS = ("status", "pr", "pr_review", "story_points", "assignee")


def review_shot(review: ReviewProgress | None) -> dict[str, int] | None:
    """O "N/X" do badge e o amarelo da barra. As aprovações que a regra pede
    ficam de fora: são da configuração, não do PR, e trocar a regra não é atualização."""
    if review is None:
        return None
    return {
        "approvals": review.approvals,
        "reviewers": review.reviewers,
        "changes_requested": review.changes_requested,
    }


def snapshot(
    *,
    status: str | None,
    story_points: float | None,
    assignee_name: str | None,
    pr_status: str | None = None,
    pr_review: ReviewProgress | None = None,
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
        shot["pr_review"] = review_shot(pr_review)
    return shot


def changed_fields(seen: dict[str, Any], current: dict[str, Any]) -> list[str]:
    """Campos que mudaram. Só compara o que as duas fotos têm — um card que entrou na
    sprint passa a ter PR, e a foto de antes das aprovações no badge não tem
    `pr_review`: nenhum dos dois é atualização."""
    changed = [f for f in FIELDS if f in seen and f in current and seen[f] != current[f]]
    # A etapa nova já conta a review que mudou junto — o merge leva a barra embora.
    if "pr" in changed and "pr_review" in changed:
        changed.remove("pr_review")
    return changed


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


async def acknowledge_own_change(
    pool: asyncpg.Pool, issue_key: str, changes: dict[str, Any]
) -> None:
    """O dev mexeu no card pelo próprio SprintAI: a mudança dele não acende a bolinha.

    Só o campo mexido entra na foto — refazê-la inteira (`mark_seen`) engoliria a mudança
    de outra pessoa que o dev ainda não viu, como um responsável trocado.
    """
    fields = {k: v for k, v in changes.items() if k in FIELDS}
    if fields.get("story_points") is not None:
        fields["story_points"] = float(fields["story_points"])
    if fields:
        await seen_repo.merge_existing(pool, issue_key, fields)


async def mark_seen(pool: asyncpg.Pool, issue_key: str) -> bool:
    """Refaz a foto com o estado atual do espelho. `False` se a tarefa não está nele."""
    row = await issue_repo.issue(pool, issue_key)
    if row is None:
        return False
    summary = (await pr_status_service.summaries(pool, [issue_key]))[issue_key]
    await seen_repo.upsert(
        pool,
        issue_key,
        snapshot(
            status=row["status"],
            story_points=row["story_points"],
            assignee_name=row["assignee_name"],
            pr_status=summary.status,
            pr_review=summary.review,
        ),
    )
    return True
