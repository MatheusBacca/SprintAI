from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from database.pool import get_pool
from schemas.conclude_schemas import BitbucketMembersOut, PrReviewersOut, ReviewersIn
from schemas.pr_status_schemas import (
    ISSUE_KEY_PATTERN,
    IssuePrSummaryOut,
    PrStatusBadgeOut,
    PrStatusBatchIn,
    PrTimelineOut,
)
from security.credential_store import CredentialStore, get_credential_store
from services import pr_reviewers, pr_status_service, pr_timeline_service
from services.issue_actions import IssueActionConflict
from services.sync.engine import SyncEngine, get_sync_engine

router = APIRouter(tags=["pull-requests"])

Pool = Annotated[asyncpg.Pool, Depends(get_pool)]
Store = Annotated[CredentialStore, Depends(get_credential_store)]
Engine = Annotated[SyncEngine, Depends(get_sync_engine)]

# Mesmo formato que o Bitbucket aceita no slug — o valor vai direto para a consulta.
REPO_SLUG_PATTERN = r"^[a-zA-Z0-9][\w.-]{0,98}$"


@router.get("/issues/{issue_key}/pull-requests", response_model=IssuePrSummaryOut)
async def issue_pull_requests(
    pool: Pool, issue_key: Annotated[str, Path(pattern=ISSUE_KEY_PATTERN)]
):
    """Detalhe por repositório: PRs (aprovações, ajustes, build) e branches sem PR."""
    result = await pr_status_service.summaries(pool, [issue_key])
    return pr_status_service.to_detail(result[issue_key])


@router.get("/pull-requests/{repo_slug}/{pr_id}/timeline", response_model=PrTimelineOut)
async def pull_request_timeline(
    pool: Pool,
    store: Store,
    repo_slug: Annotated[str, Path(pattern=REPO_SLUG_PATTERN)],
    pr_id: Annotated[int, Path(ge=1)],
):
    """Histórico do PR: comentários da review e os eventos (commit, aprovação, build)."""
    result = await pr_timeline_service.timeline(pool, store, repo_slug, pr_id)
    if result is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"O PR #{pr_id} de {repo_slug} não está no espelho local.",
        )
    return result


@router.post("/pr-status", response_model=dict[str, PrStatusBadgeOut])
async def pr_status_batch(pool: Pool, body: PrStatusBatchIn):
    """Status agregado de várias tarefas de uma vez (cards da árvore da sprint)."""
    result = await pr_status_service.summaries(pool, body.keys)
    return {key: pr_status_service.to_badge(summary) for key, summary in result.items()}


@router.get("/bitbucket/members", response_model=BitbucketMembersOut)
async def bitbucket_members(store: Store, refresh: Annotated[bool, Query()] = False):
    """Quem pode ser reviewer: os membros do workspace, guardados por meia hora."""
    return BitbucketMembersOut(members=await pr_reviewers.members(store, refresh=refresh))


@router.put("/pull-requests/{repo_slug}/{pr_id}/reviewers", response_model=PrReviewersOut)
async def set_pull_request_reviewers(
    pool: Pool,
    store: Store,
    engine: Engine,
    repo_slug: Annotated[str, Path(pattern=REPO_SLUG_PATTERN)],
    pr_id: Annotated[int, Path(ge=1)],
    body: ReviewersIn,
):
    """Põe e tira reviewers do PR aberto. A tela só chama depois da confirmação do dev."""
    try:
        return await pr_reviewers.update(pool, store, engine, repo_slug, pr_id, body)
    except pr_reviewers.PullRequestNotInMirror as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except IssueActionConflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=exc.message) from exc
