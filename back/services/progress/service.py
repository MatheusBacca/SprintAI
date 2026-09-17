"""Progresso da sprint: mapa de etapas salvo, progresso por tarefa e agregação (B9).

`real` é a média ponderada por Story Points das minhas tarefas não-épico da sprint
(tarefa sem SP conta 1, senão sumiria da conta). `esperado` é quanto do tempo útil da
sprint já passou — a linha que a barra real persegue.

Sprint `active` com `end_date` no passado é tratada como **vencida**: o esperado é 100%
e a Home avisa. Acontece de verdade (a Sprint 73 - Growth terminou em 11/09 e continuou
ativa), e sem a marcação o progresso pareceria adiantado.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import asyncpg

from realtime import bus
from repositories import settings_repo
from schemas.progress_schemas import StageRefOut
from services.progress.sources import Progress, ProgressSource, StatusSource, resolve
from services.progress.stages import ProgressStages, Stage

SETTING_KEY = "progress_stages"
EPIC_TYPES = {"épico", "epico", "epic"}


def stage_ref(stage: Stage | None) -> StageRefOut | None:
    return StageRefOut(id=stage.id, label=stage.label, color=stage.color) if stage else None


async def load_stages(pool: asyncpg.Pool) -> ProgressStages:
    return ProgressStages.from_setting(await settings_repo.get_setting(pool, SETTING_KEY))


async def save_stages(pool: asyncpg.Pool, stages: ProgressStages) -> ProgressStages:
    await settings_repo.set_setting(pool, SETTING_KEY, stages.to_setting())
    bus.publish(bus.PROGRESS_CHANGED, {"stages": True})
    return stages


def sources_for(stages: ProgressStages) -> list[ProgressSource]:
    """Ordem de prioridade das fontes. A `checklist` entra na frente na F13."""
    return [StatusSource(stages)]


def issue_progress(issue: dict[str, Any], sources: list[ProgressSource]) -> Progress:
    return resolve(issue, sources)


def business_days(start: date, end: date) -> int:
    """Dias úteis (seg–sex) de `start` a `end`, inclusive nas duas pontas."""
    if end < start:
        return 0
    days = 0
    current = start
    while current <= end:
        if current.weekday() < 5:
            days += 1
        current += timedelta(days=1)
    return days


def expected_ratio(start: date | None, end: date | None, today: date) -> float | None:
    """Fração do tempo útil da sprint já decorrida (0..1). Sem datas, não há esperado."""
    if start is None or end is None:
        return None
    total = business_days(start, end)
    if total == 0:
        return 1.0 if today >= end else 0.0
    if today < start:
        return 0.0
    if today >= end:
        return 1.0
    return min(1.0, business_days(start, min(today, end)) / total)


def is_epic(issue: dict[str, Any]) -> bool:
    return (issue.get("issue_type") or "").strip().lower() in EPIC_TYPES


@dataclass
class SprintProgress:
    sprint_id: int
    name: str
    state: str
    start: date | None
    end: date | None
    real: float
    expected: float | None
    overdue_active: bool
    issue_count: int
    done_count: int
    story_points: float
    by_stage: dict[str, float]


def aggregate(
    issues: list[dict[str, Any]],
    sources: list[ProgressSource],
) -> tuple[float, dict[str, float], float, int]:
    """(real, peso por etapa, total de SP contados, concluídas)."""
    total_weight = 0.0
    weighted = 0.0
    by_stage: dict[str, float] = {}
    done = 0
    for issue in issues:
        progress = resolve(issue, sources)
        points = issue.get("story_points")
        weight = float(points) if points else 1.0
        total_weight += weight
        weighted += progress.value * weight
        stage = progress.stage_id or f"categoria:{issue.get('status_category') or '?'}"
        by_stage[stage] = by_stage.get(stage, 0.0) + weight
        if progress.value >= 1.0:
            done += 1
    real = weighted / total_weight if total_weight else 0.0
    return real, by_stage, total_weight, done


def sprint_progress(
    sprint: dict[str, Any],
    issues: list[dict[str, Any]],
    sources: list[ProgressSource],
    *,
    today: date,
    tz: Any = None,
) -> SprintProgress:
    mine = [i for i in issues if not is_epic(i)]
    real, by_stage, points, done = aggregate(mine, sources)
    start = _as_date(sprint.get("start_date"), tz)
    end = _as_date(sprint.get("end_date"), tz)
    overdue = bool(sprint.get("state") == "active" and end and end < today)
    return SprintProgress(
        sprint_id=sprint["id"],
        name=sprint["name"],
        state=sprint["state"],
        start=start,
        end=end,
        real=real,
        expected=1.0 if overdue else expected_ratio(start, end, today),
        overdue_active=overdue,
        issue_count=len(mine),
        done_count=done,
        story_points=points,
        by_stage=by_stage,
    )


def _as_date(value: Any, tz: Any = None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return (value.astimezone(tz) if tz else value).date()
    return value
