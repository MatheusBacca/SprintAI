"""Repositórios locais do Workspace: descoberta no disco + ajustes do dev + espelho.

O vínculo efetivo de cada pasta sai, nesta ordem, do ajuste do dev (Configurações ›
Workspace) e do remote `origin`. A branch base, do ajuste, da `main_branch` do Bitbucket (o
espelho sabe o que o servidor diz), do `origin/HEAD` do clone e, por último, do palpite.
"""

import asyncio

import asyncpg

from repositories import workspace_repo
from schemas.workspace_schemas import WorkspaceRepoOut, WorkspaceReposOut, WorkspaceRepoUpdate
from security.paths import Roots
from services.workspace.discovery import LocalRepo, discover


async def refresh(pool: asyncpg.Pool, roots: Roots) -> list[LocalRepo]:
    """Lê o disco e acerta a tabela. São dois arquivos por pasta — barato o bastante para
    rodar a cada listagem, e a tela nunca mostra uma branch atual de ontem."""
    found = await asyncio.to_thread(discover, roots.projects)
    async with pool.acquire() as conn, conn.transaction():
        await workspace_repo.upsert_detected(
            conn,
            [
                {
                    "slug": r.slug,
                    "local_path": str(r.path),
                    "has_git": r.has_git,
                    "remote_url": r.remote_url,
                    "bb_slug": r.bb_slug,
                    "current_branch": r.current_branch,
                    "detached": r.detached,
                    "base_branch": r.base_branch,
                    "base_source": r.base_source,
                }
                for r in found
            ],
        )
        await workspace_repo.mark_missing(conn, [r.slug for r in found])
    return found


async def list_repos(pool: asyncpg.Pool, roots: Roots) -> WorkspaceReposOut:
    await refresh(pool, roots)
    rows = await workspace_repo.list_repos(pool)
    mirror = await workspace_repo.mirror_main_branches(pool)
    return WorkspaceReposOut(root=str(roots.projects), repos=[to_out(r, mirror) for r in rows])


async def update_repo(
    pool: asyncpg.Pool, slug: str, payload: WorkspaceRepoUpdate
) -> WorkspaceRepoOut | None:
    link_override = {"auto": None, "none": "", "manual": payload.bb_slug}[payload.link]
    updated = await workspace_repo.set_overrides(
        pool, slug, link_override=link_override, base_branch_override=payload.base_branch
    )
    if not updated:
        return None
    row = await workspace_repo.get_repo(pool, slug)
    return to_out(row, await workspace_repo.mirror_main_branches(pool))


def to_out(row, mirror: dict[str, str | None]) -> WorkspaceRepoOut:
    bb_slug, link = effective_link(row["link_override"], row["detected_bb_slug"])
    base, base_source = effective_base(
        row["base_branch_override"],
        mirror.get(bb_slug) if bb_slug else None,
        row["detected_base"],
        row["detected_base_source"],
    )
    return WorkspaceRepoOut(
        slug=row["slug"],
        path=row["local_path"],
        present=row["present"],
        has_git=row["has_git"],
        remote_url=row["remote_url"],
        bb_slug=bb_slug,
        link=link,
        in_mirror=bb_slug in mirror if bb_slug else False,
        base_branch=base,
        base_source=base_source,
        current_branch=row["current_branch"],
        detached=row["detached"],
        detected_at=row["detected_at"],
    )


def effective_link(override: str | None, detected: str | None) -> tuple[str | None, str]:
    if override is None:
        return detected, "auto"
    if override == "":
        return None, "none"
    return override, "manual"


def effective_base(
    override: str | None,
    mirror_main: str | None,
    detected: str | None,
    detected_source: str | None,
) -> tuple[str | None, str | None]:
    if override:
        return override, "manual"
    if mirror_main:
        return mirror_main, "bitbucket"
    if detected:
        return detected, detected_source
    return None, None
