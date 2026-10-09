"""Resumo da semana: as mudanças de status das minhas tarefas, dia a dia — funções puras.

Uma linha por tarefa e dia, com o caminho que ela fez naquele dia: de onde saiu e cada
status por onde passou. O desfecho compara a etapa em que o dia terminou com a etapa em
que começou, pelo mapa de Configurações › Progresso — a categoria do Jira não serve
(`DISPONIVEL PARA REVIEW` chega como `new`).

**Entrega** é avançar até a etapa de review ou além: é quando o trabalho sai da mão do
dev (PR aberto, review aprovada, testes concluídos). Ir para review e voltar para AJUSTE
no mesmo dia não é entrega — a linha mostra o vaivém, o desfecho conta onde ela parou.
"""

from datetime import date, timedelta, tzinfo
from typing import Any

from schemas.week_schemas import WeekDayIssueOut, WeekDayOut, WeekMoveOut, WeekOutcome
from services.progress.service import stage_ref
from services.progress.stages import REVIEW, ProgressStages, Stage

# Ordem das linhas no dia: o que foi entregue primeiro, o que só mexeu por último.
OUTCOME_ORDER: dict[str, int] = {"entregue": 0, "avancou": 1, "voltou": 2, "mexeu": 3}
SATURDAY = 5


def delivery_stage(stages: ProgressStages) -> Stage | None:
    """A etapa de review; sem ela no mapa, a etapa final."""
    return stages.by_id.get(REVIEW) or max(stages.stages, key=lambda s: s.order, default=None)


def outcome(start: Stage | None, end: Stage | None, delivery: Stage | None) -> WeekOutcome:
    # Status fora do mapa não tem ordem: não dá para dizer se andou para frente.
    if start is None or end is None or start.order == end.order:
        return "mexeu"
    if end.order < start.order:
        return "voltou"
    if delivery is not None and end.order >= delivery.order:
        return "entregue"
    return "avancou"


def _issue_day(moves: list[dict[str, Any]], stages: ProgressStages, delivery: Stage | None):
    first, last = moves[0], moves[-1]
    start = stages.stage_of(first["from_status"])
    end = stages.stage_of(last["to_status"])
    issue = WeekDayIssueOut(
        key=first["issue_key"],
        summary=first["summary"],
        issue_type=first["issue_type"],
        story_points=first["story_points"],
        from_status=first["from_status"],
        from_stage=stage_ref(start),
        moves=[
            WeekMoveOut(
                status=m["to_status"],
                stage=stage_ref(stages.stage_of(m["to_status"])),
                at=m["changed_at"],
                author_name=m["author_name"],
                by_me=m["by_me"],
            )
            for m in moves
        ],
        outcome=outcome(start, end, delivery),
    )
    sort_key = (OUTCOME_ORDER[issue.outcome], -(end.order if end else -1), first["changed_at"])
    return sort_key, issue


def summarize(
    rows: list[dict[str, Any]],
    stages: ProgressStages,
    *,
    tz: tzinfo,
    start: date,
    last: date,
) -> list[WeekDayOut]:
    """Dias de `start` a `last` (hoje, na semana corrente). Dia útil aparece mesmo vazio
    — "nada andou na terça" também é resumo —; sábado e domingo, só com movimento.

    `rows` vêm em ordem cronológica (`week_repo.status_moves`).
    """
    by_day: dict[date, dict[str, list[dict[str, Any]]]] = {}
    for row in rows:
        day = row["changed_at"].astimezone(tz).date()
        by_day.setdefault(day, {}).setdefault(row["issue_key"], []).append(row)

    delivery = delivery_stage(stages)
    days: list[WeekDayOut] = []
    day = start
    while day <= last:
        issues = by_day.get(day, {})
        if issues or day.weekday() < SATURDAY:
            ordered = sorted(
                (_issue_day(moves, stages, delivery) for moves in issues.values()),
                key=lambda pair: pair[0],
            )
            days.append(WeekDayOut(day=day, issues=[issue for _, issue in ordered]))
        day += timedelta(days=1)
    return days
