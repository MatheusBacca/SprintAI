import re
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from fastapi.responses import JSONResponse

from database.pool import get_pool
from schemas.pr_status_schemas import ISSUE_KEY_PATTERN
from schemas.workspace_schemas import (
    REPO_SLUG_PATTERN,
    BranchActionIn,
    BranchDeleteOut,
    BranchUpdateOut,
    CommitDetailOut,
    CommitSearchOut,
    FetchResultOut,
    GraphScope,
    RepoGraphOut,
    RepoPinIn,
    RepoRefsOut,
    WorkspaceCreate,
    WorkspaceDetailOut,
    WorkspaceOpenIn,
    WorkspaceOut,
    WorkspaceRepoOut,
    WorkspaceReposOut,
    WorkspaceRepoUpdate,
    WorkspaceTreeOut,
    WorkspaceUpdate,
)
from security.credential_store import CredentialStore, get_credential_store
from security.paths import PathNotAllowed, Roots, get_roots, resolve_allowed
from services.workspace import (
    branch_service,
    feature_set,
    graph_service,
    launcher,
    repos_service,
)
from services.workspace import workspace_service as service
from services.workspace.git_actions import GitActionError
from services.workspace.git_local import GitError, GitUnavailable

router = APIRouter(tags=["workspace"])

Pool = Annotated[asyncpg.Pool, Depends(get_pool)]
Store = Annotated[CredentialStore, Depends(get_credential_store)]
RootsDep = Annotated[Roots, Depends(get_roots)]
RepoSlug = Annotated[str, Path(pattern=REPO_SLUG_PATTERN)]


@router.get("/workspace/repos", response_model=WorkspaceReposOut)
async def list_repos(pool: Pool, roots: RootsDep):
    """Pastas de `C:\\projects`, lidas do disco agora, com o vínculo e a branch base."""
    return await repos_service.list_repos(pool, roots)


@router.put("/workspace/repos/{slug}", response_model=WorkspaceRepoOut)
async def update_repo(pool: Pool, slug: RepoSlug, payload: WorkspaceRepoUpdate):
    repo = await repos_service.update_repo(pool, slug, payload)
    if repo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Repositório local não encontrado.")
    return repo


def _git_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, graph_service.RepoUnavailable):
        return HTTPException(status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, GitUnavailable):
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    return HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router.get("/workspace/repos/{slug}/graph", response_model=RepoGraphOut)
async def repo_graph(
    pool: Pool,
    roots: RootsDep,
    slug: RepoSlug,
    keys: Annotated[list[str] | None, Query(max_length=50)] = None,
    scope: GraphScope = "feature",
    skip: Annotated[int, Query(ge=0, le=100_000)] = 0,
    limit: Annotated[int, Query(ge=1, le=1000)] = 300,
    since: Annotated[str | None, Query(pattern=r"^[0-9a-f]{20}$")] = None,
):
    """Linha do tempo das branches: refs, worktrees e commits (com os pais) do repo local.

    `keys` são as chaves da feature (`?keys=WAI-1&keys=WAI-2`); `since` é a impressão digital
    da última resposta — sem mudança no `.git`, só as worktrees voltam.
    """
    wanted = _keys_or_422(keys)
    try:
        return await graph_service.graph(
            pool, roots, slug, keys=wanted, scope=scope, skip=skip, limit=limit, since=since
        )
    except (graph_service.RepoUnavailable, GitError) as exc:
        raise _git_http_error(exc) from exc


@router.get("/workspace/repos/{slug}/commits/{sha}", response_model=CommitDetailOut)
async def commit_detail(
    pool: Pool,
    roots: RootsDep,
    slug: RepoSlug,
    sha: Annotated[str, Path(pattern=r"^[0-9a-f]{7,40}$")],
):
    try:
        return await graph_service.commit_detail(pool, roots, slug, sha)
    except (graph_service.RepoUnavailable, GitError) as exc:
        raise _git_http_error(exc) from exc


def _keys_or_422(keys: list[str] | None) -> list[str]:
    wanted = [k.strip().upper() for k in keys or []]
    if any(not re.match(ISSUE_KEY_PATTERN, k) for k in wanted):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Chave de tarefa inválida."
        )
    return wanted


def _action_error(exc: GitActionError) -> JSONResponse:
    """409 com o `code` para a tela saber o que oferecer (ex.: `unmerged` → "apagar mesmo
    assim"). A mensagem é a pronta do `git_actions`, nunca o stderr do git."""
    return JSONResponse({"detail": exc.message, "code": exc.code}, status_code=409)


@router.get("/workspace/repos/{slug}/refs", response_model=RepoRefsOut)
async def repo_refs(
    pool: Pool,
    roots: RootsDep,
    slug: RepoSlug,
    keys: Annotated[list[str] | None, Query(max_length=50)] = None,
):
    """Todas as branches locais, as `origin/` e as tags, com upstream e o selo do PR."""
    try:
        return await branch_service.refs_overview(pool, roots, slug, keys=_keys_or_422(keys))
    except (graph_service.RepoUnavailable, GitError) as exc:
        raise _git_http_error(exc) from exc


@router.get("/workspace/repos/{slug}/search", response_model=CommitSearchOut)
async def search_commits(
    pool: Pool,
    roots: RootsDep,
    slug: RepoSlug,
    q: Annotated[str, Query(min_length=2, max_length=200)],
):
    """Commits de qualquer branch, remota ou tag pela mensagem, pelo autor ou pelo hash."""
    try:
        return await branch_service.search(pool, roots, slug, q.strip())
    except (graph_service.RepoUnavailable, GitError) as exc:
        raise _git_http_error(exc) from exc


@router.post("/workspace/repos/{slug}/fetch", response_model=FetchResultOut)
async def fetch_repo(pool: Pool, roots: RootsDep, slug: RepoSlug):
    """`git fetch origin --prune`. Traz do Bitbucket; não escreve nada lá."""
    try:
        return await branch_service.fetch(pool, roots, slug)
    except GitActionError as exc:
        return _action_error(exc)
    except graph_service.RepoUnavailable as exc:
        raise _git_http_error(exc) from exc


@router.post("/workspace/repos/{slug}/branches/update", response_model=BranchUpdateOut)
async def update_branch(pool: Pool, roots: RootsDep, slug: RepoSlug, payload: BranchActionIn):
    """Avança a branch local até o upstream — só fast-forward."""
    try:
        return await branch_service.update_branch(pool, roots, slug, payload.name)
    except GitActionError as exc:
        return _action_error(exc)
    except (graph_service.RepoUnavailable, GitError) as exc:
        raise _git_http_error(exc) from exc


@router.post("/workspace/repos/{slug}/branches/delete", response_model=BranchDeleteOut)
async def delete_branch(pool: Pool, roots: RootsDep, slug: RepoSlug, payload: BranchActionIn):
    """Apaga a branch **local** (`-d`; `-D` com `force`). Branch no Bitbucket não se apaga daqui."""
    try:
        return await branch_service.delete_branch(
            pool, roots, slug, payload.name, force=payload.force
        )
    except GitActionError as exc:
        return _action_error(exc)
    except (graph_service.RepoUnavailable, GitError) as exc:
        raise _git_http_error(exc) from exc


@router.post("/workspace/open", status_code=status.HTTP_204_NO_CONTENT)
async def open_folder(roots: RootsDep, payload: WorkspaceOpenIn):
    """Abre a pasta no VS Code (`ide`) ou no Windows Terminal (`terminal`)."""
    try:
        folder = resolve_allowed(payload.path, [roots.projects])
    except PathNotAllowed as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    if not folder.is_dir():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Não é uma pasta.")
    try:
        launcher.launch(payload.target, folder)
    except launcher.LauncherUnavailable as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc


# --- Workspaces ----------------------------------------------------------------------------------


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, detail="Workspace não encontrado.")


@router.get("/workspaces", response_model=list[WorkspaceOut])
async def list_workspaces(pool: Pool):
    return await service.list_workspaces(pool)


@router.post("/workspaces", response_model=WorkspaceOut)
async def open_workspace(pool: Pool, payload: WorkspaceCreate, response: Response):
    """Abre o workspace da tarefa (reabre se já existe) ou cria um livre."""
    try:
        workspace, created = await service.open_workspace(pool, payload)
    except feature_set.IssueNotInMirror as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Tarefa fora do espelho — sincronize antes."
        ) from exc
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return workspace


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceDetailOut)
async def workspace_detail(pool: Pool, roots: RootsDep, workspace_id: int):
    try:
        return await service.detail(pool, roots, workspace_id)
    except service.WorkspaceNotFound as exc:
        raise _not_found() from exc
    except feature_set.IssueNotInMirror as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="A tarefa do workspace saiu do espelho."
        ) from exc


@router.get("/workspaces/{workspace_id}/tree", response_model=WorkspaceTreeOut)
async def workspace_tree(pool: Pool, store: Store, workspace_id: int):
    try:
        return await service.tree(pool, store, workspace_id)
    except service.WorkspaceNotFound as exc:
        raise _not_found() from exc
    except feature_set.IssueNotInMirror as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="A tarefa do workspace saiu do espelho."
        ) from exc


@router.patch("/workspaces/{workspace_id}", response_model=WorkspaceOut)
async def update_workspace(pool: Pool, workspace_id: int, payload: WorkspaceUpdate):
    try:
        return await service.update_workspace(pool, workspace_id, payload)
    except service.WorkspaceNotFound as exc:
        raise _not_found() from exc


@router.delete("/workspaces/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(pool: Pool, workspace_id: int):
    try:
        await service.delete_workspace(pool, workspace_id)
    except service.WorkspaceNotFound as exc:
        raise _not_found() from exc


@router.put("/workspaces/{workspace_id}/repos/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def pin_repo(pool: Pool, workspace_id: int, slug: RepoSlug, payload: RepoPinIn):
    """`add` fixa o repo no workspace, `hide` esconde um que a descoberta achou e `auto`
    volta ao que a descoberta diz."""
    try:
        await service.set_pin(pool, workspace_id, slug, payload.mode)
    except service.WorkspaceNotFound as exc:
        raise _not_found() from exc
