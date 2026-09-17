from datetime import date, datetime

from pydantic import BaseModel

from schemas.note_schemas import NoteOut
from schemas.pr_status_schemas import PrStatusBadgeOut
from schemas.sprint_schemas import SprintState


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
