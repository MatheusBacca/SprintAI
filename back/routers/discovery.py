from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from integrations import factory
from schemas.discovery_schemas import (
    BitbucketRepositoryOut,
    JiraBoardOut,
    JiraBoardSprintsOut,
    JiraFieldsOut,
)
from security.credential_store import CredentialStore, get_credential_store
from services import discovery_service

router = APIRouter(tags=["discovery"])

Store = Annotated[CredentialStore, Depends(get_credential_store)]
VALID_STATES = {"active", "future", "closed"}


@router.get("/jira/fields", response_model=JiraFieldsOut)
async def jira_fields(store: Store):
    async with await factory.jira_client(store) as jira:
        return await discovery_service.jira_fields(jira)


@router.get("/jira/boards", response_model=list[JiraBoardOut])
async def jira_boards(
    store: Store,
    name: Annotated[str | None, Query(max_length=100)] = None,
    project_key: Annotated[str | None, Query(pattern=r"^[A-Z][A-Z0-9_]{0,19}$")] = None,
):
    async with await factory.jira_client(store) as jira:
        return await discovery_service.jira_boards(jira, name=name, project_key=project_key)


@router.get("/jira/boards/{board_id}/sprints", response_model=JiraBoardSprintsOut)
async def jira_board_sprints(
    store: Store,
    board_id: int,
    state: Annotated[str, Query(description="Lista separada por vírgula")] = "active,future",
):
    states = tuple(s for s in (p.strip() for p in state.split(",")) if s in VALID_STATES)
    async with await factory.jira_client(store) as jira:
        return await discovery_service.jira_board_sprints(
            jira, board_id, states=states or ("active", "future")
        )


@router.get("/bitbucket/repositories", response_model=list[BitbucketRepositoryOut])
async def bitbucket_repositories(
    store: Store,
    updated_since: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
):
    async with factory.bitbucket_client(store) as bitbucket:
        return await discovery_service.bitbucket_repositories(
            bitbucket, updated_since=updated_since, limit=limit
        )
