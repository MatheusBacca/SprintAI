from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class JiraFieldOut(BaseModel):
    id: str
    name: str


class JiraFieldsOut(BaseModel):
    sprint: JiraFieldOut | None
    story_points: JiraFieldOut | None
    story_point_candidates: list[JiraFieldOut]


class JiraBoardOut(BaseModel):
    id: int
    name: str
    type: str
    project_key: str | None = None
    project_name: str | None = None


class JiraSprintOut(BaseModel):
    id: int
    name: str
    state: Literal["active", "future", "closed"]
    start_date: datetime | None = None
    end_date: datetime | None = None
    complete_date: datetime | None = None
    goal: str | None = None
    board_id: int | None = None
    # "Sprint 73 - Growth" → "Growth". Boards com várias squads usam esse sufixo.
    squad: str | None = None


class JiraBoardSprintsOut(BaseModel):
    board_id: int
    supports_sprints: bool
    sprints: list[JiraSprintOut]


class BitbucketRepositoryOut(BaseModel):
    slug: str
    name: str
    updated_on: datetime | None = None
    is_private: bool | None = None
    main_branch: str | None = None
    project_key: str | None = None
    project_name: str | None = None
