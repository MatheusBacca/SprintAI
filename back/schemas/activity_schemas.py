from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

ActivitySource = Literal["jira", "bitbucket", "local"]


class ActivityEventOut(BaseModel):
    id: int
    source: ActivitySource
    kind: str
    issue_key: str | None
    issue_summary: str | None
    issue_status: str | None
    issue_url: str | None
    repo_slug: str | None
    pr_id: int | None
    pr_url: str | None
    actor_name: str | None
    actor_is_me: bool
    occurred_at: datetime
    title: str
    detail: dict[str, Any]


class ActivityFeedOut(BaseModel):
    events: list[ActivityEventOut]
    # Opaco: só volta para o `GET /api/activity?cursor=`. Nulo quando acabou.
    next_cursor: str | None
