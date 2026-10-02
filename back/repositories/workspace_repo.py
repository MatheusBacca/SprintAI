from collections.abc import Iterable
from typing import Any

import asyncpg

from repositories.sprint_repo import ISSUE_COLUMNS

Executor = asyncpg.Connection | asyncpg.Pool

REPO_COLUMNS = """
    slug, local_path, present, has_git, remote_url, detected_bb_slug, current_branch, detached,
    detected_base, detected_base_source, link_override, base_branch_override, detected_at
"""


async def list_repos(conn: Executor) -> list[asyncpg.Record]:
    return await conn.fetch(f"SELECT {REPO_COLUMNS} FROM workspace_repo ORDER BY lower(slug)")


async def get_repo(conn: Executor, slug: str) -> asyncpg.Record | None:
    return await conn.fetchrow(f"SELECT {REPO_COLUMNS} FROM workspace_repo WHERE slug = $1", slug)


async def upsert_detected(conn: Executor, rows: Iterable[dict[str, Any]]) -> None:
    """Grava o que a descoberta achou. Linha igual não é reescrita — `detected_at` diz quando
    o disco mudou, não quando a tela foi aberta."""
    rows = list(rows)
    if not rows:
        return
    await conn.executemany(
        """
        INSERT INTO workspace_repo (
            slug, local_path, present, has_git, remote_url, detected_bb_slug, current_branch,
            detached, detected_base, detected_base_source
        ) VALUES ($1, $2, true, $3, $4, $5, $6, $7, $8, $9)
        ON CONFLICT (slug) DO UPDATE SET
            local_path = EXCLUDED.local_path, present = true, has_git = EXCLUDED.has_git,
            remote_url = EXCLUDED.remote_url, detected_bb_slug = EXCLUDED.detected_bb_slug,
            current_branch = EXCLUDED.current_branch, detached = EXCLUDED.detached,
            detected_base = EXCLUDED.detected_base,
            detected_base_source = EXCLUDED.detected_base_source,
            detected_at = now(), updated_at = now()
        WHERE (workspace_repo.local_path, workspace_repo.present, workspace_repo.has_git,
               workspace_repo.remote_url, workspace_repo.detected_bb_slug,
               workspace_repo.current_branch, workspace_repo.detached,
               workspace_repo.detected_base, workspace_repo.detected_base_source)
            IS DISTINCT FROM
              (EXCLUDED.local_path, true, EXCLUDED.has_git, EXCLUDED.remote_url,
               EXCLUDED.detected_bb_slug, EXCLUDED.current_branch, EXCLUDED.detached,
               EXCLUDED.detected_base, EXCLUDED.detected_base_source)
        """,
        [
            (
                r["slug"],
                r["local_path"],
                r["has_git"],
                r["remote_url"],
                r["bb_slug"],
                r["current_branch"],
                r["detached"],
                r["base_branch"],
                r["base_source"],
            )
            for r in rows
        ],
    )


async def mark_missing(conn: Executor, present_slugs: Iterable[str]) -> None:
    await conn.execute(
        """
        UPDATE workspace_repo SET present = false, detected_at = now(), updated_at = now()
        WHERE present AND NOT (slug = ANY($1::text[]))
        """,
        list(present_slugs),
    )


async def set_overrides(
    conn: Executor, slug: str, *, link_override: str | None, base_branch_override: str | None
) -> bool:
    status = await conn.execute(
        """
        UPDATE workspace_repo
        SET link_override = $2, base_branch_override = $3, updated_at = now()
        WHERE slug = $1
        """,
        slug,
        link_override,
        base_branch_override,
    )
    return status.endswith(" 1")


async def mirror_main_branches(conn: Executor) -> dict[str, str | None]:
    """Repos do espelho do Bitbucket e a branch principal de cada um."""
    rows = await conn.fetch("SELECT slug, main_branch FROM bb_repository")
    return {r["slug"]: r["main_branch"] for r in rows}


# --- Workspaces (B16) ------------------------------------------------------------------------

WORKSPACE_COLUMNS = """
    w.id, w.kind, w.root_issue_key, w.title, w.is_open, w.tab_order, w.created_at,
    w.last_opened_at, i.summary AS issue_summary, i.issue_type, i.status
"""
WORKSPACE_FROM = "workspace w LEFT JOIN jira_issue i ON i.key = w.root_issue_key"


async def list_workspaces(conn: Executor) -> list[asyncpg.Record]:
    return await conn.fetch(
        f"""
        SELECT {WORKSPACE_COLUMNS} FROM {WORKSPACE_FROM}
        ORDER BY w.is_open DESC, w.tab_order, w.last_opened_at DESC
        """
    )


async def get_workspace(conn: Executor, workspace_id: int) -> asyncpg.Record | None:
    return await conn.fetchrow(
        f"SELECT {WORKSPACE_COLUMNS} FROM {WORKSPACE_FROM} WHERE w.id = $1", workspace_id
    )


async def workspace_for_issue(conn: Executor, issue_key: str) -> asyncpg.Record | None:
    return await conn.fetchrow(
        f"SELECT {WORKSPACE_COLUMNS} FROM {WORKSPACE_FROM} WHERE w.root_issue_key = $1",
        issue_key,
    )


async def create_workspace(
    conn: Executor, *, kind: str, root_issue_key: str | None, title: str
) -> int:
    """A aba nova entra no fim das abertas."""
    return await conn.fetchval(
        """
        INSERT INTO workspace (kind, root_issue_key, title, tab_order)
        VALUES ($1, $2, $3,
                (SELECT coalesce(max(tab_order), -1) + 1 FROM workspace WHERE is_open))
        RETURNING id
        """,
        kind,
        root_issue_key,
        title,
    )


async def reopen_workspace(conn: Executor, workspace_id: int) -> None:
    await conn.execute(
        """
        UPDATE workspace SET
            tab_order = CASE WHEN is_open THEN tab_order
                             ELSE (SELECT coalesce(max(tab_order), -1) + 1
                                   FROM workspace WHERE is_open) END,
            is_open = true, last_opened_at = now()
        WHERE id = $1
        """,
        workspace_id,
    )


async def update_workspace(
    conn: Executor,
    workspace_id: int,
    *,
    title: str | None,
    is_open: bool | None,
    tab_order: int | None,
) -> bool:
    status = await conn.execute(
        """
        UPDATE workspace SET
            title = coalesce($2, title),
            is_open = coalesce($3, is_open),
            tab_order = coalesce($4, tab_order),
            last_opened_at = CASE WHEN $3 THEN now() ELSE last_opened_at END
        WHERE id = $1
        """,
        workspace_id,
        title,
        is_open,
        tab_order,
    )
    return status.endswith(" 1")


async def delete_workspace(conn: Executor, workspace_id: int) -> bool:
    status = await conn.execute("DELETE FROM workspace WHERE id = $1", workspace_id)
    return status.endswith(" 1")


async def pins(conn: Executor, workspace_id: int) -> dict[str, str]:
    rows = await conn.fetch(
        "SELECT repo_slug, mode FROM workspace_repo_pin WHERE workspace_id = $1", workspace_id
    )
    return {r["repo_slug"]: r["mode"] for r in rows}


async def set_pin(conn: Executor, workspace_id: int, repo_slug: str, mode: str | None) -> None:
    if mode is None:
        await conn.execute(
            "DELETE FROM workspace_repo_pin WHERE workspace_id = $1 AND repo_slug = $2",
            workspace_id,
            repo_slug,
        )
        return
    await conn.execute(
        """
        INSERT INTO workspace_repo_pin (workspace_id, repo_slug, mode) VALUES ($1, $2, $3)
        ON CONFLICT (workspace_id, repo_slug) DO UPDATE SET mode = EXCLUDED.mode
        """,
        workspace_id,
        repo_slug,
        mode,
    )


# --- Descida da feature ------------------------------------------------------------------------

async def children_of(conn: Executor, keys: Iterable[str]) -> list[dict[str, Any]]:
    """Filhas pelo campo `parent` — só as que estão no espelho (as do dev, no escopo padrão)."""
    rows = await conn.fetch(
        f"SELECT {ISSUE_COLUMNS} FROM jira_issue i WHERE i.parent_key = ANY($1::text[])",
        list(keys),
    )
    return [dict(r) for r in rows]


async def links_to(conn: Executor, keys: Iterable[str]) -> list[dict[str, Any]]:
    """Links gravados do lado de quem aponta para as chaves — o espelho grava o link na
    origem, então a "volta" de um Relates mora na outra tarefa."""
    rows = await conn.fetch(
        """
        SELECT source_key, target_key, link_type, direction, label, target_summary,
               target_status, target_type
        FROM jira_issue_link WHERE target_key = ANY($1::text[])
        """,
        list(keys),
    )
    return [dict(r) for r in rows]
