from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from database.pool import get_pool
from schemas.issue_schemas import ChangelogOut, IssueDetailOut, IssuePickOut
from schemas.pr_status_schemas import ISSUE_KEY_PATTERN
from security.credential_store import CredentialStore, get_credential_store
from services import card_updates, issue_service

router = APIRouter(prefix="/issues", tags=["issues"])

Pool = Annotated[asyncpg.Pool, Depends(get_pool)]
Store = Annotated[CredentialStore, Depends(get_credential_store)]
IssueKey = Annotated[str, Path(pattern=ISSUE_KEY_PATTERN)]


@router.get("", response_model=list[IssuePickOut])
async def pick_issues(
    pool: Pool,
    store: Store,
    q: Annotated[str, Query(max_length=200)] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    mine: bool = False,
):
    """Tarefas do espelho para escolher numa lista, filtradas por qualquer campo visível."""
    return await issue_service.pick(pool, store, q=q, limit=limit, mine=mine)


@router.get("/{issue_key}", response_model=IssueDetailOut)
async def issue_detail(pool: Pool, store: Store, issue_key: IssueKey):
    """Tudo o que o espelho sabe da tarefa: campos, descrição, dependências, PRs, comentários."""
    try:
        return await issue_service.get_detail(pool, store, issue_key)
    except issue_service.IssueNotFound as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"{issue_key} não está no espelho local."
        ) from exc


@router.get("/{issue_key}/changelog", response_model=ChangelogOut)
async def issue_changelog(store: Store, issue_key: IssueKey):
    """Histórico de mudanças, buscado ao vivo no Jira (não fica no espelho)."""
    return await issue_service.get_changelog(store, issue_key)


@router.post("/{issue_key}/seen", status_code=status.HTTP_204_NO_CONTENT)
async def mark_issue_seen(pool: Pool, issue_key: IssueKey):
    """O dev abriu o card: apaga a bolinha de atualização até a próxima mudança."""
    if not await card_updates.mark_seen(pool, issue_key):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"{issue_key} não está no espelho local."
        )
