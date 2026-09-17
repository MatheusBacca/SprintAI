from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel

from schemas.pr_status_schemas import IssuePrSummaryOut, PrStatusBadgeOut
from schemas.progress_schemas import StageRefOut


class IssueRefOut(BaseModel):
    """Outra issue citada no painel (pai, filha, link)."""

    key: str
    summary: str | None = None
    status: str | None = None
    status_category: str | None = None
    issue_type: str | None = None
    assignee_name: str | None = None
    in_mirror: bool = True
    url: str | None = None
    pr: PrStatusBadgeOut | None = None


class IssuePickOut(BaseModel):
    """Uma linha da lista de tarefas para vincular (lembrete)."""

    key: str
    summary: str
    issue_type: str
    status: str
    status_category: str
    assignee_name: str | None
    is_mine: bool


class DependencyOut(IssueRefOut):
    link_type: str
    direction: Literal["inward", "outward"]
    label: str


class DependencyGroupOut(BaseModel):
    label: str
    kind: Literal["blocks", "blocked_by", "hierarchy", "other"]
    items: list[DependencyOut]


class SprintRefOut(BaseModel):
    id: int
    name: str
    state: str
    squad: str | None = None


class CommentOut(BaseModel):
    id: str
    author_name: str | None
    body_adf: dict[str, Any] | None
    body_text: str | None
    created_at: datetime
    updated_at: datetime | None


class IssueDetailOut(BaseModel):
    key: str
    url: str | None
    summary: str
    issue_type: str
    is_subtask: bool
    status: str
    status_category: str
    priority: str | None
    assignee_name: str | None
    is_mine: bool
    reporter_name: str | None
    story_points: float | None
    due_date: date | None
    labels: list[str]
    components: list[str]
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    synced_at: datetime
    description_adf: dict[str, Any] | None
    description_text: str | None
    parent: IssueRefOut | None
    children: list[IssueRefOut]
    sprints: list[SprintRefOut]
    dependencies: list[DependencyGroupOut]
    blocks: list[DependencyOut]
    blocked_by: list[DependencyOut]
    # Mesma regra do card do canvas (`services/blocking.py`): bloqueadores não concluídos
    # que ainda não abriram PR.
    blockers_without_pr: list[str] = []
    stage: StageRefOut | None = None
    comments: list[CommentOut]
    pull_requests: IssuePrSummaryOut


class ChangeItemOut(BaseModel):
    field: str
    from_value: str | None
    to_value: str | None


class ChangelogEntryOut(BaseModel):
    id: str
    author_name: str | None
    created_at: datetime
    items: list[ChangeItemOut]


class ChangelogOut(BaseModel):
    issue_key: str
    entries: list[ChangelogEntryOut]
    truncated: bool
