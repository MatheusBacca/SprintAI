"""Barras e segmentos da timeline (B10) — funções puras, sem banco.

Cada tarefa vira uma barra:

- **início**: a primeira transição para fora da etapa inicial (o momento em que o
  trabalho começou de verdade). Sem transição registrada, o começo da sprint;
- **fim**: `resolved_at`; quando ele não existe — e neste workflow ele **nunca** existe,
  porque as tarefas são fechadas sem resolução — a transição para a etapa final; em
  último caso, o `updated_at`. Sem nada disso, uma projeção (barra `projected`);
- **segmentos**: um trecho por status pelo qual a tarefa passou, a partir de
  `jira_status_transition`. Sem histórico, um segmento só com o status atual.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from services.progress.stages import ProgressStages


@dataclass(frozen=True)
class Segment:
    status: str
    stage_id: str | None
    color: str | None
    start: datetime
    end: datetime


@dataclass(frozen=True)
class Bar:
    start: datetime
    end: datetime
    projected: bool
    started: bool
    segments: list[Segment]


def _stage_order(stages: ProgressStages, status: str | None) -> int:
    stage = stages.stage_of(status)
    return stage.order if stage else -1


def _initial_order(stages: ProgressStages) -> int:
    return min((s.order for s in stages.stages), default=0)


def _final_order(stages: ProgressStages) -> int:
    return max((s.order for s in stages.stages), default=0)


def is_done(issue: dict[str, Any], stages: ProgressStages) -> bool:
    stage = stages.stage_of(issue.get("status"))
    if stage is not None:
        return stage.order == _final_order(stages)
    return issue.get("status_category") == "done"


def finished_at(
    issue: dict[str, Any], transitions: list[dict[str, Any]], stages: ProgressStages
) -> datetime | None:
    """Quando a tarefa chegou à etapa final. `None` se ela ainda não chegou lá."""
    if not is_done(issue, stages):
        return None
    final = _final_order(stages)
    for transition in reversed(transitions):
        if _stage_order(stages, transition["to_status"]) == final:
            return transition["changed_at"]
    # Concluída antes da janela de backfill: o último toque é a melhor aproximação.
    return issue.get("updated_at")


def started_at(
    transitions: list[dict[str, Any]], stages: ProgressStages, *, fallback: datetime
) -> tuple[datetime, bool]:
    """(quando a tarefa saiu da etapa inicial, se isso chegou a acontecer)."""
    initial = _initial_order(stages)
    for transition in transitions:
        if _stage_order(stages, transition["to_status"]) > initial:
            return transition["changed_at"], True
    return fallback, False


def segments_of(
    transitions: list[dict[str, Any]],
    *,
    current_status: str,
    start: datetime,
    end: datetime,
    stages: ProgressStages,
) -> list[Segment]:
    def make(status: str | None, seg_start: datetime, seg_end: datetime) -> Segment | None:
        if seg_end <= seg_start:
            return None
        stage = stages.stage_of(status)
        return Segment(
            status=status or current_status,
            stage_id=stage.id if stage else None,
            color=stage.color if stage else None,
            start=seg_start,
            end=seg_end,
        )

    inside = [t for t in transitions if start < t["changed_at"] < end]
    status = current_status
    if transitions:
        # O status vigente no início da barra é o "de onde saiu" da primeira transição
        # posterior a ela; se todas são anteriores, é o "para onde foi" da última.
        before = [t for t in transitions if t["changed_at"] <= start]
        after = [t for t in transitions if t["changed_at"] > start]
        if before:
            status = before[-1]["to_status"]
        elif after:
            status = after[0]["from_status"] or current_status

    result: list[Segment] = []
    cursor = start
    for transition in inside:
        if segment := make(status, cursor, transition["changed_at"]):
            result.append(segment)
        cursor = transition["changed_at"]
        status = transition["to_status"]
    if segment := make(status, cursor, end):
        result.append(segment)
    return result


def build_bar(
    issue: dict[str, Any],
    transitions: list[dict[str, Any]],
    stages: ProgressStages,
    *,
    window_start: datetime,
    window_end: datetime,
    now: datetime,
) -> Bar:
    """`window_*` são as bordas da sprint da tarefa: o fallback do início e da projeção."""
    ordered = sorted(transitions, key=lambda t: t["changed_at"])
    start, started = started_at(ordered, stages, fallback=window_start)
    start = max(min(start, window_end), window_start)

    resolved = issue.get("resolved_at") or finished_at(issue, ordered, stages)
    if resolved is not None:
        end, projected = max(resolved, start), False
    else:
        # Sprint vencida (a 73 é o caso real): a tarefa não acabou, então a barra vai
        # até hoje em vez de parar num fim de sprint que já passou.
        end, projected = max(window_end, now, start), True

    return Bar(
        start=start,
        end=end,
        projected=projected,
        started=started,
        segments=segments_of(
            ordered,
            current_status=issue.get("status") or "",
            start=start,
            end=end,
            stages=stages,
        ),
    )


def as_date(value: datetime | date | None, tz: Any = None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return (value.astimezone(tz) if tz else value).date()
    return value
