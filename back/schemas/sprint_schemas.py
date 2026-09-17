from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from schemas.pr_status_schemas import PrStatusBadgeOut
from schemas.progress_schemas import StageRefOut

SprintState = Literal["active", "future", "closed"]


class SprintSummaryOut(BaseModel):
    id: int
    name: str
    state: SprintState
    squad: str | None = None
    goal: str | None = None
    board_id: int | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    complete_date: datetime | None = None
    issue_count: int = 0
    mine_count: int = 0
    done_count: int = 0


class TreeNodeOut(BaseModel):
    key: str
    summary: str
    issue_type: str
    status: str
    status_category: str
    story_points: float | None
    assignee_name: str | None
    is_mine: bool
    in_sprint: bool
    is_parent_type: bool
    partial: bool
    parent_key: str | None
    parent_via: Literal["parent", "link"] | None
    group: str
    depth: int
    blocked: bool
    blocked_by: list[str]
    # Bloqueadores que ainda não abriram PR: enquanto houver um, o card mostra o ícone
    # de bloqueio no lugar do ícone do tipo.
    blockers_without_pr: list[str] = []
    blocks: list[str]
    children: list[str]
    url: str | None
    pr: PrStatusBadgeOut | None
    stage: StageRefOut | None = None
    # Campos que mudaram desde o último clique no card (status, pr, story_points, assignee).
    unseen_changes: list[str] = []
    # Lembretes não arquivados vinculados à tarefa (ícone do rodapé do card).
    note_count: int = 0


class TreeEdgeOut(BaseModel):
    source: str
    target: str
    kind: Literal["parent", "link", "blocks"]
    label: str | None = None


class TreeGroupOut(BaseModel):
    key: str
    root_key: str | None
    issue_keys: list[str]


class SprintTreeOut(BaseModel):
    sprint: SprintSummaryOut
    only_mine: bool
    counters: dict[str, int]
    nodes: list[TreeNodeOut]
    edges: list[TreeEdgeOut]
    groups: list[TreeGroupOut]
