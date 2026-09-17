from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

RunStatus = Literal["running", "success", "partial", "failed"]


class SyncRunOut(BaseModel):
    id: int
    trigger: Literal["manual", "scheduled"]
    status: RunStatus
    started_at: datetime
    finished_at: datetime | None = None
    stats: dict[str, Any] = {}
    errors: list[dict[str, Any]] = []


class SyncStatusOut(BaseModel):
    running: bool
    current_stage: str | None = None
    current_run_id: int | None = None
    last_run: SyncRunOut | None = None
    last_success_at: datetime | None = None
    next_run_in_seconds: int | None = None
    counts: dict[str, int]


class SyncTriggerOut(BaseModel):
    run_id: int


class ScopeSprintOut(BaseModel):
    id: int
    name: str
    state: Literal["active", "future", "closed"]
    squad: str | None = None
    board_id: int | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    issues_synced_at: datetime | None = None
    issue_count: int
