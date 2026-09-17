from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from services.pr_status import PrStatus

ISSUE_KEY_PATTERN = r"^[A-Z][A-Z0-9]{1,9}-\d{1,7}$"


class ReviewerOut(BaseModel):
    name: str | None
    role: str | None
    approved: bool
    state: str | None


class PullRequestOut(BaseModel):
    repo_slug: str
    id: int
    title: str
    state: str
    status: PrStatus
    status_label: str
    draft: bool
    source_branch: str | None
    destination_branch: str | None
    url: str | None
    updated_on: datetime | None
    approvals: int
    changes_requested: int
    reviewers: list[ReviewerOut]
    build_status: str | None
    build_failed: bool
    comment_count: int | None
    match: Literal["branch", "title"]


class BranchOut(BaseModel):
    name: str
    target_date: datetime | None
    stale: bool


class RepoPrStatusOut(BaseModel):
    repo_slug: str
    status: PrStatus
    status_label: str
    pull_requests: list[PullRequestOut]
    branches: list[BranchOut]


class IssuePrSummaryOut(BaseModel):
    issue_key: str
    status: PrStatus
    status_label: str
    pr_count: int
    open_pr_count: int
    build_failed: bool
    last_activity: datetime | None
    repos: list[RepoPrStatusOut]


class PrTimelineEntryOut(BaseModel):
    """`kind` é `comment` ou o `kind` do evento (`pr_commit`, `pr_approved`, …)."""

    kind: str
    at: datetime
    actor_name: str | None
    actor_is_me: bool
    # `body` é o markdown cru do Bitbucket. A tela renderiza como texto — nunca HTML.
    body: str | None
    comment_id: int | None
    parent_id: int | None
    inline_path: str | None
    inline_from: int | None
    inline_to: int | None
    is_deleted: bool
    commit: str | None
    build: str | None
    after_changes_requested: bool


class PrTimelineOut(BaseModel):
    repo_slug: str
    pr_id: int
    title: str
    url: str | None
    # Ajuste pedido e ainda sem commit depois dele.
    pending_review: bool
    # Revisor pedindo ajuste, mas o pedido é anterior ao histórico local.
    request_before_history: bool
    entries: list[PrTimelineEntryOut]


class PrStatusBadgeOut(BaseModel):
    """Versão enxuta para os cards da árvore."""

    status: PrStatus
    status_label: str
    pr_count: int
    open_pr_count: int
    build_failed: bool


class PrStatusBatchIn(BaseModel):
    keys: list[str] = Field(min_length=1, max_length=2000)

    @field_validator("keys")
    @classmethod
    def _normalize(cls, value: list[str]) -> list[str]:
        import re

        pattern = re.compile(ISSUE_KEY_PATTERN)
        keys = sorted({k.strip().upper() for k in value})
        invalid = [k for k in keys if not pattern.match(k)]
        if invalid:
            raise ValueError(f"Chaves inválidas: {', '.join(invalid[:5])}")
        return keys
