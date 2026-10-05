"""Workspace: a feature aberta numa aba, com os cards, os repos envolvidos e (no front) a
linha do tempo e os terminais de cada repo (B16).

Repo envolvido sai de quatro fontes, e a resposta diz qual:

- `branch` — branch local (ou do `origin`) com a chave de uma tarefa do conjunto;
- `pr` — PR ou branch do espelho do Bitbucket ligado a uma tarefa do conjunto;
- `title` — o `[repo]` do começo do título de uma tarefa do conjunto;
- `pin` — o dev fixou o repo neste workspace.

O que o dev esconde (`hide`) continua na resposta com `hidden`, para a tela poder mostrar
de novo.
"""

import asyncio
import dataclasses
from collections import defaultdict
from pathlib import Path

import asyncpg

from repositories import pr_status_repo, workspace_repo
from schemas.sprint_schemas import TreeEdgeOut, TreeGroupOut
from schemas.workspace_schemas import (
    InvolvedRepoOut,
    TreeFrameOut,
    WorkspaceCreate,
    WorkspaceDetailOut,
    WorkspaceOut,
    WorkspaceRepoOut,
    WorkspaceTreeOut,
    WorkspaceUpdate,
)
from security.credential_store import CredentialStore
from security.paths import Roots
from services import card_colors
from services.sprint_service import climb_ancestors, jira_identity, render_nodes
from services.sprint_tree import build_tree
from services.sync.engine import load_scope
from services.workspace import feature_set, repos_service
from services.workspace.discovery import branch_names
from utils.issue_keys import extract_issue_keys


class WorkspaceNotFound(Exception):
    pass


def to_out(row) -> WorkspaceOut:
    return WorkspaceOut(
        id=row["id"],
        kind=row["kind"],
        root_issue_key=row["root_issue_key"],
        title=row["issue_summary"] or row["title"],
        issue_type=row["issue_type"],
        status=row["status"],
        is_open=row["is_open"],
        tab_order=row["tab_order"],
        created_at=row["created_at"],
        last_opened_at=row["last_opened_at"],
    )


async def list_workspaces(pool: asyncpg.Pool) -> list[WorkspaceOut]:
    return [to_out(r) for r in await workspace_repo.list_workspaces(pool)]


async def open_workspace(pool: asyncpg.Pool, payload: WorkspaceCreate) -> tuple[WorkspaceOut, bool]:
    """(workspace, criado agora). A tarefa precisa estar no espelho: é de lá que saem os
    cards e as chaves."""
    async with pool.acquire() as conn, conn.transaction():
        if payload.root_issue_key:
            existing = await workspace_repo.workspace_for_issue(conn, payload.root_issue_key)
            if existing:
                await workspace_repo.reopen_workspace(conn, existing["id"])
                return to_out(await workspace_repo.get_workspace(conn, existing["id"])), False
            feature = await feature_set.load(pool, payload.root_issue_key)
            workspace_id = await workspace_repo.create_workspace(
                conn,
                kind="issue",
                root_issue_key=payload.root_issue_key,
                title=feature.root.get("summary") or payload.root_issue_key,
            )
        else:
            workspace_id = await workspace_repo.create_workspace(
                conn, kind="free", root_issue_key=None, title=payload.title
            )
        for slug in dict.fromkeys(payload.repos):
            await workspace_repo.set_pin(conn, workspace_id, slug, "add")
        return to_out(await workspace_repo.get_workspace(conn, workspace_id)), True


async def update_workspace(
    pool: asyncpg.Pool, workspace_id: int, payload: WorkspaceUpdate
) -> WorkspaceOut:
    updated = await workspace_repo.update_workspace(
        pool,
        workspace_id,
        title=payload.title,
        is_open=payload.is_open,
        tab_order=payload.tab_order,
    )
    if not updated:
        raise WorkspaceNotFound(workspace_id)
    return to_out(await workspace_repo.get_workspace(pool, workspace_id))


async def delete_workspace(pool: asyncpg.Pool, workspace_id: int) -> None:
    if not await workspace_repo.delete_workspace(pool, workspace_id):
        raise WorkspaceNotFound(workspace_id)


async def _workspace(pool: asyncpg.Pool, workspace_id: int):
    row = await workspace_repo.get_workspace(pool, workspace_id)
    if row is None:
        raise WorkspaceNotFound(workspace_id)
    return row


async def _feature(pool: asyncpg.Pool, row) -> feature_set.FeatureSet | None:
    if row["kind"] != "issue":
        return None
    return await feature_set.load(pool, row["root_issue_key"])


# --- Árvore --------------------------------------------------------------------------------------


async def tree(pool: asyncpg.Pool, store: CredentialStore, workspace_id: int) -> WorkspaceTreeOut:
    row = await _workspace(pool, workspace_id)
    frame = TreeFrameOut(id=f"workspace:{workspace_id}", label="na feature")
    feature = await _feature(pool, row)
    if feature is None:
        return WorkspaceTreeOut(
            workspace_id=workspace_id, frame=frame, counters={}, nodes=[], edges=[], groups=[]
        )

    account_id, site_url = jira_identity(store)
    issues = list(feature.rows.values())
    related, links = await climb_ancestors(pool, issues)
    built = build_tree(
        sprint_issues=issues,
        related_issues=list(related.values()),
        links=links + feature.extra_links,
        my_account_id=account_id,
    )
    for key in feature.partial_keys:
        if key in built.nodes:
            built.nodes[key].partial = True
    return WorkspaceTreeOut(
        workspace_id=workspace_id,
        frame=frame,
        counters=built.counters,
        nodes=await render_nodes(pool, built, site_url),
        edges=[TreeEdgeOut(**vars(e)) for e in built.edges],
        groups=[TreeGroupOut(**vars(g)) for g in built.groups],
    )


# --- Repos envolvidos ----------------------------------------------------------------------------


async def detail(pool: asyncpg.Pool, roots: Roots, workspace_id: int) -> WorkspaceDetailOut:
    row = await _workspace(pool, workspace_id)
    feature = await _feature(pool, row)
    keys = feature.keys if feature else []
    summaries = {k: r.get("summary") for k, r in feature.rows.items()} if feature else {}
    repos = await involved_repos(pool, roots, workspace_id, keys, summaries)
    return WorkspaceDetailOut(workspace=to_out(row), keys=keys, repos=repos)


async def involved_repos(
    pool: asyncpg.Pool,
    roots: Roots,
    workspace_id: int,
    keys: list[str],
    summaries: dict[str, str | None],
) -> list[InvolvedRepoOut]:
    local = (await repos_service.list_repos(pool, roots)).repos
    by_slug = {r.slug: r for r in local}
    by_bb = {r.bb_slug: r.slug for r in local if r.bb_slug}
    pins = await workspace_repo.pins(pool, workspace_id)

    sources: dict[str, set[str]] = defaultdict(set)
    branches: dict[str, set[str]] = defaultdict(set)
    issue_keys: dict[str, set[str]] = defaultdict(set)
    remote_only: dict[str, str] = {}
    colors = await card_colors.load_colors(pool)

    if keys:
        project_keys = (await load_scope(pool)).jira.project_keys
        wanted = set(keys)

        names = await asyncio.to_thread(_local_branch_names, [r for r in local if _has_clone(r)])
        for slug, repo_branches in names.items():
            for name in repo_branches:
                hit = wanted & set(extract_issue_keys(name, project_keys=project_keys))
                if hit:
                    sources[slug].add("branch")
                    branches[slug].add(name)
                    issue_keys[slug] |= hit

        mirror_rows = await pr_status_repo.pull_requests_for(pool, keys)
        mirror_rows += await pr_status_repo.branches_for(pool, keys)
        for mirror in mirror_rows:
            slug = by_bb.get(mirror["repo_slug"]) or remote_only.setdefault(
                mirror["repo_slug"], mirror["repo_slug"]
            )
            sources[slug].add("pr")
            issue_keys[slug] |= wanted & set(mirror["issue_keys"])

        known = set(colors.known) | set(by_slug) | set(by_bb)
        resolver = dataclasses.replace(colors, known=tuple(sorted(known)))
        for key, summary in summaries.items():
            for named in resolver.title_repos(summary):
                slug = named if named in by_slug else by_bb.get(named, named)
                if slug not in by_slug:
                    remote_only.setdefault(slug, named)
                sources[slug].add("title")
                issue_keys[slug].add(key)

    for slug, mode in pins.items():
        if mode == "add":
            sources[slug].add("pin")
            if slug not in by_slug:
                remote_only.setdefault(slug, slug)

    result = []
    for slug in sorted(set(sources) | {s for s, m in pins.items() if m == "hide"}):
        repo = by_slug.get(slug)
        bb_slug = repo.bb_slug if repo else remote_only.get(slug)
        result.append(
            InvolvedRepoOut(
                slug=slug,
                path=repo.path if repo and _has_clone(repo) else None,
                local=bool(repo and _has_clone(repo)),
                bb_slug=bb_slug,
                base_branch=repo.base_branch if repo else None,
                current_branch=repo.current_branch if repo else None,
                sources=sorted(sources.get(slug, set()), key=SOURCE_ORDER.index),
                branches=sorted(branches.get(slug, set())),
                issue_keys=sorted(issue_keys.get(slug, set())),
                hidden=pins.get(slug) == "hide",
                # A cor é cadastrada pelo repo do Bitbucket; a pasta pode ter outro nome.
                color=colors.repos.get(slug) or colors.repos.get(bb_slug or ""),
            )
        )
    return result


SOURCE_ORDER = ["branch", "pr", "title", "pin"]


def _has_clone(repo: WorkspaceRepoOut) -> bool:
    return repo.present and repo.has_git


def _local_branch_names(repos: list[WorkspaceRepoOut]) -> dict[str, set[str]]:
    return {repo.slug: branch_names(Path(repo.path) / ".git") for repo in repos}


async def set_pin(pool: asyncpg.Pool, workspace_id: int, slug: str, mode: str) -> None:
    await _workspace(pool, workspace_id)
    await workspace_repo.set_pin(pool, workspace_id, slug, None if mode == "auto" else mode)
