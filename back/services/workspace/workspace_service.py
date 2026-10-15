"""Workspace: a feature aberta numa aba, com os cards, os repos envolvidos e (no front) a
linha do tempo e os terminais de cada repo (B16).

Repo envolvido sai de cinco fontes, e a resposta diz qual:

- `project` — o workspace é a aba de um projeto do Bitbucket, e o repo é do projeto;
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


class WorkspaceFixed(Exception):
    """A aba de um projeto não fecha nem se apaga: ela sai das escolhas do sync."""


def to_out(row) -> WorkspaceOut:
    return WorkspaceOut(
        id=row["id"],
        kind=row["kind"],
        root_issue_key=row["root_issue_key"],
        project_key=row["project_key"],
        title=row["issue_summary"] or row["title"],
        issue_type=row["issue_type"],
        status=row["status"],
        is_open=row["is_open"],
        tab_order=row["tab_order"],
        created_at=row["created_at"],
        last_opened_at=row["last_opened_at"],
    )


async def list_workspaces(pool: asyncpg.Pool) -> list[WorkspaceOut]:
    await sync_project_workspaces(pool)
    return [to_out(r) for r in await workspace_repo.list_workspaces(pool)]


async def sync_project_workspaces(pool: asyncpg.Pool) -> None:
    """Uma aba fixa por projeto do Bitbucket dos repos escolhidos no sync (OrganIA, weon).

    É a pré-seleção que o dev montava à mão com um workspace livre por projeto — e esse
    livre, quando tem o nome do projeto, é o que vira a aba, com o título e os repos
    fixados ou escondidos que já tinha. Projeto que sai do sync devolve a aba como livre."""
    projects = await workspace_repo.mirror_projects(pool)
    # A lista é lida a cada abertura do Workspace: só trava e escreve quando há o que mudar.
    if _projects_in_sync(projects, await workspace_repo.list_workspaces(pool)):
        return
    async with pool.acquire() as conn, conn.transaction():
        await workspace_repo.lock_project_workspaces(conn)
        rows = await workspace_repo.list_workspaces(conn)
        by_project = {r["project_key"]: r for r in rows if r["kind"] == "project"}
        free = [r for r in rows if r["kind"] == "free"]
        for key, project in sorted(projects.items(), key=lambda p: p[1]["name"] or p[0]):
            row = by_project.get(key)
            if row is not None:
                if not row["is_open"]:
                    await workspace_repo.reopen_workspace(conn, row["id"])
                continue
            names = {_name_key(key), _name_key(project["name"])}
            mine = next((r for r in free if _name_key(r["title"]) in names), None)
            if mine is not None:
                free.remove(mine)
                await workspace_repo.adopt_project_workspace(conn, mine["id"], key)
            else:
                await workspace_repo.create_project_workspace(conn, key, project["name"] or key)
        for key, row in by_project.items():
            if key not in projects:
                await workspace_repo.release_project_workspace(conn, row["id"])


def _projects_in_sync(projects: dict[str, dict], rows) -> bool:
    """Cada projeto já tem a sua aba aberta, e nenhuma aba é de projeto que saiu."""
    open_tabs = {r["project_key"]: r["is_open"] for r in rows if r["kind"] == "project"}
    return set(open_tabs) == set(projects) and all(open_tabs.values())


def _name_key(name: str | None) -> str:
    """`WeON`, `weon` e `WEON` são o mesmo projeto — a mesma regra do colchete do título."""
    return card_colors.repo_key(name)


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
    if payload.is_open is False and (await _workspace(pool, workspace_id))["kind"] == "project":
        raise WorkspaceFixed(workspace_id)
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
    if (await _workspace(pool, workspace_id))["kind"] == "project":
        raise WorkspaceFixed(workspace_id)
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
    repos = await involved_repos(
        pool, roots, workspace_id, keys, summaries, project_key=row["project_key"]
    )
    return WorkspaceDetailOut(workspace=to_out(row), keys=keys, repos=repos)


@dataclasses.dataclass
class IssueRepoLinks:
    """Repo de cada tarefa, pelas três fontes automáticas. A chave dos mapas é a pasta em
    `C:\\projects` — ou o slug do Bitbucket, quando o repo não tem clone (`remote_only`)."""

    sources: dict[str, set[str]] = dataclasses.field(default_factory=lambda: defaultdict(set))
    branches: dict[str, set[str]] = dataclasses.field(default_factory=lambda: defaultdict(set))
    issue_keys: dict[str, set[str]] = dataclasses.field(default_factory=lambda: defaultdict(set))
    remote_only: dict[str, str] = dataclasses.field(default_factory=dict)


async def link_issue_repos(
    pool: asyncpg.Pool,
    local: list[WorkspaceRepoOut],
    keys: list[str],
    summaries: dict[str, str | None],
    colors: card_colors.CardColors,
) -> IssueRepoLinks:
    """Branch local com a chave, PR/branch do espelho do Bitbucket e o `[repo]` do título.
    É o que os "Repositórios envolvidos" do Workspace e o menu "WAIs por repositório" do
    topo leem — um para as tarefas de uma feature, o outro para o espelho inteiro."""
    links = IssueRepoLinks()
    if not keys:
        return links
    by_slug = {r.slug: r for r in local}
    by_bb = {r.bb_slug: r.slug for r in local if r.bb_slug}
    project_keys = (await load_scope(pool)).jira.project_keys
    wanted = set(keys)

    names = await asyncio.to_thread(_local_branch_names, [r for r in local if _has_clone(r)])
    for slug, repo_branches in names.items():
        for name in repo_branches:
            hit = wanted & set(extract_issue_keys(name, project_keys=project_keys))
            if hit:
                links.sources[slug].add("branch")
                links.branches[slug].add(name)
                links.issue_keys[slug] |= hit

    mirror_rows = await pr_status_repo.pull_requests_for(pool, keys)
    mirror_rows += await pr_status_repo.branches_for(pool, keys)
    for mirror in mirror_rows:
        slug = by_bb.get(mirror["repo_slug"]) or links.remote_only.setdefault(
            mirror["repo_slug"], mirror["repo_slug"]
        )
        links.sources[slug].add("pr")
        links.issue_keys[slug] |= wanted & set(mirror["issue_keys"])

    known = set(colors.known) | set(by_slug) | set(by_bb)
    resolver = dataclasses.replace(colors, known=tuple(sorted(known)))
    for key, summary in summaries.items():
        for named in resolver.title_repos(summary):
            slug = named if named in by_slug else by_bb.get(named, named)
            if slug not in by_slug:
                links.remote_only.setdefault(slug, named)
            links.sources[slug].add("title")
            links.issue_keys[slug].add(key)
    return links


async def involved_repos(
    pool: asyncpg.Pool,
    roots: Roots,
    workspace_id: int,
    keys: list[str],
    summaries: dict[str, str | None],
    *,
    project_key: str | None = None,
) -> list[InvolvedRepoOut]:
    local = (await repos_service.list_repos(pool, roots)).repos
    by_slug = {r.slug: r for r in local}
    pins = await workspace_repo.pins(pool, workspace_id)
    colors = await card_colors.load_colors(pool)
    links = await link_issue_repos(pool, local, keys, summaries, colors)
    sources, branches, issue_keys = links.sources, links.branches, links.issue_keys
    remote_only = links.remote_only

    if project_key:
        by_bb = {r.bb_slug: r.slug for r in local if r.bb_slug}
        project = (await workspace_repo.mirror_projects(pool)).get(project_key)
        for bb_slug in project["slugs"] if project else []:
            slug = by_bb.get(bb_slug) or remote_only.setdefault(bb_slug, bb_slug)
            sources[slug].add("project")

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


SOURCE_ORDER = ["project", "branch", "pr", "title", "pin"]


def _has_clone(repo: WorkspaceRepoOut) -> bool:
    return repo.present and repo.has_git


def _local_branch_names(repos: list[WorkspaceRepoOut]) -> dict[str, set[str]]:
    return {repo.slug: branch_names(Path(repo.path) / ".git") for repo in repos}


async def set_pin(pool: asyncpg.Pool, workspace_id: int, slug: str, mode: str) -> None:
    await _workspace(pool, workspace_id)
    await workspace_repo.set_pin(pool, workspace_id, slug, None if mode == "auto" else mode)
