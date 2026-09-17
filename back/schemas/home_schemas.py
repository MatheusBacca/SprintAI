from datetime import date, datetime

from pydantic import BaseModel

from schemas.note_schemas import NoteOut
from schemas.pr_status_schemas import PrStatusBadgeOut
from schemas.progress_schemas import ProgressOut, SprintProgressOut
from schemas.week_schemas import WeekIssueOut


class HomePendingOut(BaseModel):
    """Top N de cada bloco da Semana; `total` diz quanto ficou de fora."""

    overdue: list[WeekIssueOut]
    due: list[WeekIssueOut]
    slicing: list[WeekIssueOut]
    without_sprint: list[WeekIssueOut]
    total: int


class HomeOut(BaseModel):
    today: date
    timezone: str
    filtered_by_assignee: bool
    week_start: date
    week_end: date
    sprints: list[SprintProgressOut]
    pending: HomePendingOut
    reminders: list[NoteOut]


class TimelineSprintOut(BaseModel):
    id: int
    name: str
    state: str
    squad: str | None
    start: date | None
    end: date | None
    overdue_active: bool
    current: bool


class TimelineSegmentOut(BaseModel):
    status: str
    stage_id: str | None
    color: str | None
    start: datetime
    end: datetime


class TimelineIssueOut(BaseModel):
    key: str
    summary: str
    issue_type: str
    status: str
    status_category: str
    story_points: float | None
    assignee_name: str | None
    url: str | None
    due_date: date | None
    resolved_at: datetime | None
    sprint_id: int | None
    start: datetime
    end: datetime
    # `projected`: ainda não terminou, a barra vai até o fim da sprint.
    projected: bool
    # `started`: já houve transição para fora da etapa inicial.
    started: bool
    progress: ProgressOut
    segments: list[TimelineSegmentOut]
    pr: PrStatusBadgeOut | None


class TimelineGroupOut(BaseModel):
    key: str | None
    summary: str
    issue_type: str | None
    url: str | None
    progress: float
    issues: list[TimelineIssueOut]


class TimelineLinkOut(BaseModel):
    source: str
    target: str


class TimelineOut(BaseModel):
    today: date
    timezone: str
    start: date
    end: date
    sprints: list[TimelineSprintOut]
    groups: list[TimelineGroupOut]
    links: list[TimelineLinkOut]
