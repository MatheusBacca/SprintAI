from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from schemas.note_schemas import NoteOut
from schemas.pr_status_schemas import PrStatusBadgeOut
from schemas.progress_schemas import StageRefOut
from schemas.sprint_schemas import SprintState

# Onde a tarefa terminou o dia comparado com onde começou (`services/week_summary.py`).
WeekOutcome = Literal["entregue", "avancou", "voltou", "mexeu"]


class WeekIssueOut(BaseModel):
    key: str
    summary: str
    issue_type: str
    status: str
    status_category: str
    priority: str | None
    story_points: float | None
    due_date: date | None
    parent_key: str | None
    parent_summary: str | None
    sprint_name: str | None
    sprint_state: SprintState | None
    updated_at: datetime
    resolved_at: datetime | None
    open_points: int
    url: str | None
    pr: PrStatusBadgeOut | None


class WeekMoveOut(BaseModel):
    """Um status por onde a tarefa passou no dia."""

    status: str
    stage: StageRefOut | None
    at: datetime
    author_name: str | None
    # Nulo quando o evento do feed que dizia quem foi já saiu pela retenção.
    by_me: bool | None


class WeekDayIssueOut(BaseModel):
    key: str
    summary: str
    issue_type: str
    story_points: float | None
    # Onde a tarefa estava quando o dia começou.
    from_status: str | None
    from_stage: StageRefOut | None
    moves: list[WeekMoveOut]
    outcome: WeekOutcome


class WeekDayOut(BaseModel):
    day: date
    issues: list[WeekDayIssueOut]


class WeekSummaryOut(BaseModel):
    # As colunas do kanban, na ordem de Configurações › Progresso.
    stages: list[StageRefOut]
    # A partir de qual etapa um avanço conta como entrega.
    delivery_stage: StageRefOut | None
    days: list[WeekDayOut]


class WeekOut(BaseModel):
    start: date
    end: date
    today: date
    timezone: str
    # Sem accountId salvo na conexão o filtro "minhas" não é aplicado.
    filtered_by_assignee: bool
    without_sprint: list[WeekIssueOut]
    due: list[WeekIssueOut]
    overdue: list[WeekIssueOut]
    slicing: list[WeekIssueOut]
    reminders: list[NoteOut]
    pending_reminders: list[NoteOut]
    summary: WeekSummaryOut
