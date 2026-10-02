"""Linha do tempo das branches de um repo local (B15) — o `gitk --all` do Workspace.

Junta, de um repo de `C:\\projects`:

- as refs (locais, `origin/` e tags), com upstream, à frente/atrás e a worktree que está
  com cada branch aberta;
- os commits alcançáveis, com os pais, para a tela desenhar as pistas;
- as alterações não commitadas de cada worktree;
- e, do espelho do Bitbucket, os PRs cuja branch de origem é uma das refs.

**Só da feature** = a branch base (local e `origin/`) mais as branches que têm a chave da
tarefa — é o que mostra de onde a feature saiu e se a base andou. **Todas** = branches,
remotas e tags (o `--all` sem o `stash`).

O git só roda quando a impressão digital do `.git` muda; a tela pergunta a cada poucos
segundos com `since=<impressão>` e, sem mudança, recebe só as worktrees. O "não commitado"
tem validade curta própria: editar um arquivo não passa pelo `.git`.
"""

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import asyncpg

from repositories import pr_status_repo, workspace_repo
from schemas.workspace_schemas import (
    CommitDetailOut,
    CommitFileOut,
    GraphCommitOut,
    GraphRefOut,
    GraphScope,
    GraphWorktreeOut,
    IssuePrStatusOut,
    RepoGraphOut,
    WorktreeChangesOut,
)
from security.paths import PathNotAllowed, Roots, is_under, resolve_allowed
from services import pr_status_service
from services.pr_status import pull_request_link
from services.sync.engine import load_scope
from services.workspace import git_local
from services.workspace.repos_service import to_out
from utils.issue_keys import extract_issue_keys

CHANGES_TTL_SECONDS = 4.0
MAX_CACHE_ENTRIES = 256


class RepoUnavailable(Exception):
    """Repo desconhecido, sem git, com a pasta sumida ou fora das raízes."""


@dataclass(frozen=True)
class RepoContext:
    slug: str
    path: Path
    git_dir: Path
    base_branch: str | None
    bb_slug: str | None


class _Cache:
    """Cache em memória por chave; a impressão digital faz parte da chave, então entrada
    velha só some por tamanho — nunca é servida depois que o `.git` muda."""

    def __init__(self) -> None:
        self._data: dict[tuple, tuple[float, Any]] = {}

    def get(self, key: tuple, max_age: float | None = None) -> Any | None:
        hit = self._data.get(key)
        if hit is None:
            return None
        stored_at, value = hit
        if max_age is not None and time.monotonic() - stored_at > max_age:
            return None
        return value

    def put(self, key: tuple, value: Any) -> Any:
        if len(self._data) >= MAX_CACHE_ENTRIES:
            for old in sorted(self._data, key=lambda k: self._data[k][0])[: MAX_CACHE_ENTRIES // 4]:
                del self._data[old]
        self._data[key] = (time.monotonic(), value)
        return value

    def clear(self) -> None:
        self._data.clear()


_cache = _Cache()


def clear_cache() -> None:
    _cache.clear()


async def repo_context(pool: asyncpg.Pool, roots: Roots, slug: str) -> RepoContext:
    row = await workspace_repo.get_repo(pool, slug)
    if row is None or not row["present"] or not row["has_git"]:
        raise RepoUnavailable("Repositório local não encontrado ou sem git.")
    try:
        path = resolve_allowed(row["local_path"], roots.all())
    except PathNotAllowed as exc:
        raise RepoUnavailable(str(exc)) from exc
    git_dir = path / ".git"
    if not git_dir.is_dir():
        raise RepoUnavailable("Repositório local sem pasta .git.")
    repo = to_out(row, await workspace_repo.mirror_main_branches(pool))
    return RepoContext(
        slug=slug, path=path, git_dir=git_dir, base_branch=repo.base_branch, bb_slug=repo.bb_slug
    )


async def graph(
    pool: asyncpg.Pool,
    roots: Roots,
    slug: str,
    *,
    keys: list[str],
    scope: GraphScope,
    skip: int,
    limit: int,
    since: str | None = None,
) -> RepoGraphOut:
    ctx = await repo_context(pool, roots, slug)
    fp = await asyncio.to_thread(git_local.fingerprint, ctx.git_dir)

    worktrees = await _cached(("worktrees", ctx.path, fp), git_local.list_worktrees(ctx.path))
    worktrees_out = await _worktrees_out(worktrees, roots, fp)
    base = RepoGraphOut(
        repo=slug,
        path=str(ctx.path),
        base_branch=ctx.base_branch,
        scope=scope,
        keys=keys,
        fingerprint=fp,
        fetched_at=git_local.fetched_at(ctx.git_dir),
        worktrees=worktrees_out,
        skip=skip,
        limit=limit,
    )
    if since == fp and skip == 0:
        return base.model_copy(update={"unchanged": True})

    refs = await _cached(("refs", ctx.path, fp), git_local.list_refs(ctx.path))
    project_keys = (await load_scope(pool)).jira.project_keys
    main_path = worktrees[0].path if worktrees else None
    wanted = {k.upper() for k in keys}
    base_names = {ctx.base_branch, f"origin/{ctx.base_branch}"} if ctx.base_branch else set()

    classified = []
    for ref in refs:
        ref_keys = extract_issue_keys(ref.name, project_keys=project_keys)
        classified.append((ref, ref_keys, bool(wanted & set(ref_keys)), ref.name in base_names))

    revisions = _revisions(scope, classified, worktrees, main_path)
    page = await _cached(
        ("log", ctx.path, fp, tuple(revisions), skip, limit),
        git_local.log(ctx.path, revisions, skip=skip, limit=limit + 1),
    )
    commits = page[:limit]

    # O weaction-api tem mais de mil refs (cada PR antigo deixa um `origin/`). Volta só quem
    # etiqueta um commit desta página, mais as da feature, a base e as abertas em worktree —
    # a página seguinte traz as etiquetas dela.
    shas = {c.sha for c in commits}
    classified = [
        item
        for item in classified
        if item[0].target in shas or item[2] or item[3] or item[0].worktree
    ]
    prs = await branch_prs(pool, ctx.bb_slug, [branch_name(ref) for ref, *_ in classified])
    commits_out = [commit_out(c, project_keys) for c in commits]
    refs_out = [
        ref_out(ref, ref_keys, in_feature, is_base, main_path, prs)
        for ref, ref_keys, in_feature, is_base in classified
    ]
    return base.model_copy(
        update={
            "refs": refs_out,
            "commits": commits_out,
            "has_more": len(page) > limit,
            "issue_status": await issue_status(
                pool, [k for item in commits_out + refs_out for k in item.issue_keys]
            ),
        }
    )


def ref_out(ref, ref_keys, in_feature, is_base, main_path, prs) -> GraphRefOut:
    return GraphRefOut(
        name=ref.name,
        kind=ref.kind,
        target=ref.target,
        upstream=ref.upstream,
        ahead=ref.ahead,
        behind=ref.behind,
        gone=ref.gone,
        worktree=ref.worktree,
        is_head=bool(main_path and ref.kind == "local" and ref.worktree == main_path),
        is_base=is_base,
        in_feature=in_feature,
        issue_keys=ref_keys,
        pull_requests=prs.get(branch_name(ref), []) if ref.kind != "tag" else [],
        committed_at=ref.committed_at,
        subject=ref.subject,
    )


def commit_out(c: git_local.Commit, project_keys: list[str]) -> GraphCommitOut:
    return GraphCommitOut(
        sha=c.sha,
        parents=list(c.parents),
        author=c.author,
        authored_at=c.authored_at,
        committed_at=c.committed_at,
        subject=c.subject,
        issue_keys=extract_issue_keys(c.subject, project_keys=project_keys),
    )


async def issue_status(pool: asyncpg.Pool, keys) -> dict[str, IssuePrStatusOut]:
    """Status de PR de cada chave que aparece — a cor do `WAI-XXXX` na linha do tempo. Chave
    sem nenhum PR nem branch no espelho volta como "Sem PR", igual ao card."""
    unique = sorted(set(keys))
    if not unique:
        return {}
    summaries = await pr_status_service.summaries(pool, unique)
    return {
        key: IssuePrStatusOut(status=summary.status, status_label=summary.label)
        for key, summary in summaries.items()
    }


def _revisions(scope, classified, worktrees, main_path) -> list[str]:
    """O que o `git log` percorre. Worktree em HEAD destacado entra pelo hash — sem ela, o
    trabalho de uma sessão do Claude numa worktree solta não apareceria no grafo."""
    detached_heads = [wt.head for wt in worktrees if wt.detached and wt.head]
    if scope == "all":
        return ["--branches", "--remotes", "--tags", *detached_heads]
    revisions = [
        ref.full for ref, _keys, in_feature, is_base in classified if in_feature or is_base
    ]
    if not any(in_feature for _ref, _keys, in_feature, _base in classified):
        # Sem branch da tarefa (ou Workspace livre): a branch aberta no clone principal.
        revisions += [
            ref.full
            for ref, *_ in classified
            if ref.kind == "local" and main_path and ref.worktree == main_path
        ]
    return list(dict.fromkeys(revisions))


def branch_name(ref: git_local.Ref) -> str:
    """Nome que o Bitbucket usa como `source_branch`: `origin/x` é a mesma branch `x`."""
    if ref.kind == "remote" and "/" in ref.name:
        return ref.name.split("/", 1)[1]
    return ref.name


async def branch_prs(pool: asyncpg.Pool, bb_slug: str | None, names: list[str]) -> dict:
    if not bb_slug or not names:
        return {}
    rows = await pr_status_repo.pull_requests_for_branches(pool, bb_slug, set(names))
    if not rows:
        return {}
    rule = await pr_status_service.load_rule(pool)
    by_branch: dict[str, list] = {}
    for row in sorted(rows, key=lambda r: r["updated_on"], reverse=True):
        pr = pull_request_link(None, row, rule)
        if pr.url:
            by_branch.setdefault(row["source_branch"], []).append(pr_status_service.link_out(pr))
    return by_branch


def _locate(worktrees, roots: Roots) -> list[tuple[Path | None, bool]]:
    """(caminho real ou nulo se sumiu, dentro das raízes) de cada worktree."""
    found = []
    for wt in worktrees:
        path = Path(wt.path)
        try:
            resolved = path.resolve(strict=True)
        except (OSError, RuntimeError):
            found.append((None, is_under(path, roots.all())))
            continue
        found.append((resolved, is_under(resolved, roots.all())))
    return found


async def _worktrees_out(worktrees, roots: Roots, fp: str) -> list[GraphWorktreeOut]:
    locations = await asyncio.to_thread(_locate, worktrees, roots)

    async def one(index: int, wt: git_local.Worktree) -> GraphWorktreeOut:
        resolved, inside = locations[index]
        changes = None
        if inside and resolved is not None and not wt.bare:
            try:
                found = await _cached(
                    ("changes", wt.path, fp),
                    git_local.worktree_changes(resolved),
                    max_age=CHANGES_TTL_SECONDS,
                )
                changes = WorktreeChangesOut(
                    changed=found.changed, untracked=found.untracked, conflicted=found.conflicted
                )
            except git_local.GitError:
                changes = None
        return GraphWorktreeOut(
            path=wt.path,
            head=wt.head,
            branch=wt.branch,
            detached=wt.detached,
            is_main=index == 0,
            locked=wt.locked,
            prunable=wt.prunable or resolved is None,
            outside_roots=not inside,
            changes=changes,
        )

    return list(await asyncio.gather(*(one(i, wt) for i, wt in enumerate(worktrees))))


async def _cached(key: tuple, coro, *, max_age: float | None = None):
    hit = _cache.get(key, max_age)
    if hit is not None:
        coro.close()
        return hit
    return _cache.put(key, await coro)


async def commit_detail(pool: asyncpg.Pool, roots: Roots, slug: str, sha: str) -> CommitDetailOut:
    ctx = await repo_context(pool, roots, slug)
    detail = await git_local.show(ctx.path, sha)
    project_keys = (await load_scope(pool)).jira.project_keys
    return CommitDetailOut(
        sha=detail.sha,
        parents=list(detail.parents),
        author=detail.author,
        authored_at=detail.authored_at,
        committer=detail.committer,
        committed_at=detail.committed_at,
        message=detail.message,
        issue_keys=extract_issue_keys(detail.message, project_keys=project_keys),
        files=[CommitFileOut(path=f.path, added=f.added, deleted=f.deleted) for f in detail.files],
        files_truncated=detail.files_truncated,
    )
