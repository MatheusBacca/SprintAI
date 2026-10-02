"""Painel de branches da linha do tempo: todas as refs do repo, a busca no histórico e as três
ações de escrita (fetch --prune, avançar e apagar branch local).

A escrita é serializada por repo: dois cliques seguidos (ou duas abas) não disparam dois
`git` brigando pelo mesmo lock.
"""

import asyncio
from pathlib import Path

import asyncpg

from schemas.workspace_schemas import (
    BranchDeleteOut,
    BranchUpdateOut,
    CommitSearchOut,
    FetchResultOut,
    RepoRefsOut,
)
from security.paths import PathNotAllowed, Roots, resolve_allowed
from services.sync.engine import load_scope
from services.workspace import git_actions, git_local
from services.workspace.graph_service import (
    branch_name,
    branch_prs,
    clear_cache,
    commit_out,
    issue_status,
    ref_out,
    repo_context,
)
from utils.issue_keys import extract_issue_keys

SEARCH_LIMIT = 100
KIND_ORDER = {"local": 0, "remote": 1, "tag": 2}

_locks: dict[str, asyncio.Lock] = {}


def _lock(slug: str) -> asyncio.Lock:
    return _locks.setdefault(slug, asyncio.Lock())


async def refs_overview(
    pool: asyncpg.Pool, roots: Roots, slug: str, *, keys: list[str]
) -> RepoRefsOut:
    ctx = await repo_context(pool, roots, slug)
    refs = await git_local.list_refs(ctx.path)
    worktrees = await git_local.list_worktrees(ctx.path)
    main_path = worktrees[0].path if worktrees else None
    project_keys = (await load_scope(pool)).jira.project_keys
    wanted = {k.upper() for k in keys}
    base_names = {ctx.base_branch, f"origin/{ctx.base_branch}"} if ctx.base_branch else set()
    prs = await branch_prs(pool, ctx.bb_slug, [branch_name(r) for r in refs if r.kind != "tag"])

    out = []
    for ref in refs:
        ref_keys = extract_issue_keys(ref.name, project_keys=project_keys)
        in_feature = bool(wanted & set(ref_keys))
        out.append(ref_out(ref, ref_keys, in_feature, ref.name in base_names, main_path, prs))
    # Mais recente primeiro dentro de cada grupo: é a branch em que se está mexendo.
    out.sort(
        key=lambda r: (
            KIND_ORDER[r.kind],
            -(r.committed_at.timestamp() if r.committed_at else 0),
            r.name,
        )
    )
    return RepoRefsOut(
        repo=slug,
        base_branch=ctx.base_branch,
        fetched_at=git_local.fetched_at(ctx.git_dir),
        refs=out,
        issue_status=await issue_status(pool, [k for r in out for k in r.issue_keys]),
    )


async def search(pool: asyncpg.Pool, roots: Roots, slug: str, query: str) -> CommitSearchOut:
    ctx = await repo_context(pool, roots, slug)
    commits = await git_local.search(ctx.path, query, limit=SEARCH_LIMIT)
    project_keys = (await load_scope(pool)).jira.project_keys
    out = [commit_out(c, project_keys) for c in commits]
    return CommitSearchOut(
        query=query,
        commits=out,
        issue_status=await issue_status(pool, [k for c in out for k in c.issue_keys]),
    )


async def fetch(pool: asyncpg.Pool, roots: Roots, slug: str) -> FetchResultOut:
    ctx = await repo_context(pool, roots, slug)
    async with _lock(slug):
        result = await git_actions.fetch_prune(ctx.path)
    clear_cache()
    return FetchResultOut(
        added=result.added,
        updated=result.updated,
        pruned=result.pruned,
        tags=result.tags,
        fetched_at=git_local.fetched_at(ctx.git_dir),
    )


async def update_branch(pool: asyncpg.Pool, roots: Roots, slug: str, name: str) -> BranchUpdateOut:
    ctx = await repo_context(pool, roots, slug)

    def allowed(path: str) -> Path | None:
        try:
            return resolve_allowed(path, [roots.projects])
        except PathNotAllowed:
            return None

    async with _lock(slug):
        result = await git_actions.update_branch(ctx.path, name, worktree_allowed=allowed)
    clear_cache()
    return BranchUpdateOut(
        name=result.name, before=result.before, after=result.after, mode=result.mode
    )


async def delete_branch(
    pool: asyncpg.Pool, roots: Roots, slug: str, name: str, *, force: bool
) -> BranchDeleteOut:
    ctx = await repo_context(pool, roots, slug)
    async with _lock(slug):
        worktrees = await git_local.list_worktrees(ctx.path)
        target = await git_actions.delete_branch(
            ctx.path, name, force=force, base_branch=ctx.base_branch, worktrees=worktrees
        )
    clear_cache()
    return BranchDeleteOut(name=name, target=target)
