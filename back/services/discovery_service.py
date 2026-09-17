"""Descoberta de boards, sprints, campos e repositórios.

Alimenta a configuração do escopo de sincronização (B4) e serve de verificação
dos clientes contra os dados reais.
"""

import re
from datetime import datetime
from typing import Any

from integrations.bitbucket_client import BitbucketClient
from integrations.errors import SprintsNotSupported
from integrations.jira_client import SPRINT_STATES, JiraClient
from schemas.discovery_schemas import (
    BitbucketRepositoryOut,
    JiraBoardOut,
    JiraBoardSprintsOut,
    JiraFieldOut,
    JiraFieldsOut,
    JiraSprintOut,
)

# "Sprint 73 - Growth" → "Growth"; "Sprint 12" ou "🛠️BUG-SUPORT" → None
_SQUAD_SUFFIX = re.compile(r"^sprint\s+\d+\s+-\s+(?P<squad>[^\d].*?)\s*$", re.IGNORECASE)


def squad_from_sprint_name(name: str) -> str | None:
    match = _SQUAD_SUFFIX.match(name or "")
    return match.group("squad") if match else None


def to_board(raw: dict[str, Any]) -> JiraBoardOut:
    location = raw.get("location") or {}
    return JiraBoardOut(
        id=raw["id"],
        name=raw["name"],
        type=raw.get("type", "unknown"),
        project_key=location.get("projectKey"),
        project_name=location.get("projectName") or location.get("displayName"),
    )


def to_sprint(raw: dict[str, Any]) -> JiraSprintOut:
    return JiraSprintOut(
        id=raw["id"],
        name=raw["name"],
        state=raw["state"],
        start_date=raw.get("startDate"),
        end_date=raw.get("endDate"),
        complete_date=raw.get("completeDate"),
        goal=raw.get("goal") or None,
        board_id=raw.get("originBoardId"),
        squad=squad_from_sprint_name(raw["name"]),
    )


async def jira_fields(jira: JiraClient) -> JiraFieldsOut:
    field_map = await jira.discover_fields()

    def out(field):
        return JiraFieldOut(id=field.id, name=field.name) if field else None

    return JiraFieldsOut(
        sprint=out(field_map.sprint),
        story_points=out(field_map.story_points),
        story_point_candidates=[out(f) for f in field_map.story_point_candidates],
    )


async def jira_boards(
    jira: JiraClient, *, name: str | None = None, project_key: str | None = None
) -> list[JiraBoardOut]:
    return [to_board(b) async for b in jira.iter_boards(name=name, project_key=project_key)]


async def jira_board_sprints(
    jira: JiraClient, board_id: int, *, states: tuple[str, ...] = SPRINT_STATES
) -> JiraBoardSprintsOut:
    try:
        sprints = [to_sprint(s) async for s in jira.iter_sprints(board_id, states=states)]
    except SprintsNotSupported:
        return JiraBoardSprintsOut(board_id=board_id, supports_sprints=False, sprints=[])
    return JiraBoardSprintsOut(board_id=board_id, supports_sprints=True, sprints=sprints)


async def bitbucket_repositories(
    bitbucket: BitbucketClient, *, updated_since: datetime | None = None, limit: int = 500
) -> list[BitbucketRepositoryOut]:
    repos: list[BitbucketRepositoryOut] = []
    async for raw in bitbucket.iter_repositories(updated_since=updated_since):
        repos.append(
            BitbucketRepositoryOut(
                slug=raw["slug"],
                name=raw.get("name") or raw["slug"],
                updated_on=raw.get("updated_on"),
                is_private=raw.get("is_private"),
                main_branch=(raw.get("mainbranch") or {}).get("name"),
                project_key=(raw.get("project") or {}).get("key"),
                project_name=(raw.get("project") or {}).get("name"),
            )
        )
        if len(repos) >= limit:
            break
    return repos
