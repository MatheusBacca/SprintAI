from collections.abc import Iterable
from typing import Any

import asyncpg

Executor = asyncpg.Connection | asyncpg.Pool


async def upsert_repositories(conn: Executor, rows: Iterable[dict[str, Any]]) -> None:
    rows = list(rows)
    if not rows:
        return
    await conn.executemany(
        """
        INSERT INTO bb_repository (slug, name, is_private, main_branch, updated_on, synced_at)
        VALUES ($1, $2, $3, $4, $5, now())
        ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name, is_private = EXCLUDED.is_private,
            main_branch = EXCLUDED.main_branch, updated_on = EXCLUDED.updated_on, synced_at = now()
        """,
        [(r["slug"], r["name"], r["is_private"], r["main_branch"], r["updated_on"]) for r in rows],
    )


async def previous_pull_requests(
    conn: Executor, repo_slug: str, pr_ids: Iterable[int]
) -> dict[int, dict[str, Any]]:
    """Linha atual do espelho, lida ANTES do upsert: é contra ela que o diff gera eventos."""
    rows = await conn.fetch(
        """
        SELECT id, state, draft, source_commit, participants, build_status, comment_count,
               created_on, updated_on
        FROM bb_pull_request
        WHERE repo_slug = $1 AND id = ANY($2::int[])
        """,
        repo_slug,
        list(pr_ids),
    )
    return {r["id"]: dict(r) for r in rows}


async def upsert_pull_requests(conn: Executor, rows: Iterable[dict[str, Any]]) -> None:
    rows = list(rows)
    if not rows:
        return
    await conn.executemany(
        """
        INSERT INTO bb_pull_request (repo_slug, id, title, description, state, draft, author_name,
            source_branch, source_commit, destination_branch, participants, comment_count,
            task_count, build_status, issue_keys, url, created_on, updated_on, author_account_id,
            synced_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18,
                $19, now())
        ON CONFLICT (repo_slug, id) DO UPDATE SET
            title = EXCLUDED.title, description = EXCLUDED.description, state = EXCLUDED.state,
            draft = EXCLUDED.draft, author_name = EXCLUDED.author_name,
            source_branch = EXCLUDED.source_branch, source_commit = EXCLUDED.source_commit,
            destination_branch = EXCLUDED.destination_branch,
            participants = EXCLUDED.participants, comment_count = EXCLUDED.comment_count,
            task_count = EXCLUDED.task_count,
            build_status = COALESCE(EXCLUDED.build_status, bb_pull_request.build_status),
            issue_keys = EXCLUDED.issue_keys, url = EXCLUDED.url,
            created_on = EXCLUDED.created_on, updated_on = EXCLUDED.updated_on,
            author_account_id = EXCLUDED.author_account_id, synced_at = now()
        """,
        [
            (
                r["repo_slug"],
                r["id"],
                r["title"],
                r["description"],
                r["state"],
                r["draft"],
                r["author_name"],
                r["source_branch"],
                r["source_commit"],
                r["destination_branch"],
                r["participants"],
                r["comment_count"],
                r["task_count"],
                r.get("build_status"),
                r["issue_keys"],
                r["url"],
                r["created_on"],
                r["updated_on"],
                r.get("author_account_id"),
            )
            for r in rows
        ],
    )


async def upsert_pr_comments(conn: Executor, rows: Iterable[dict[str, Any]]) -> int:
    rows = list(rows)
    if not rows:
        return 0
    await conn.executemany(
        """
        INSERT INTO bb_pr_comment (repo_slug, pr_id, id, parent_id, author_name,
            author_account_id, body_text, inline_path, inline_from, inline_to, is_deleted,
            created_on, updated_on, synced_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, now())
        ON CONFLICT (repo_slug, pr_id, id) DO UPDATE SET
            parent_id = EXCLUDED.parent_id, author_name = EXCLUDED.author_name,
            author_account_id = EXCLUDED.author_account_id, body_text = EXCLUDED.body_text,
            inline_path = EXCLUDED.inline_path, inline_from = EXCLUDED.inline_from,
            inline_to = EXCLUDED.inline_to, is_deleted = EXCLUDED.is_deleted,
            created_on = EXCLUDED.created_on, updated_on = EXCLUDED.updated_on,
            synced_at = now()
        """,
        [
            (
                r["repo_slug"],
                r["pr_id"],
                r["id"],
                r["parent_id"],
                r["author_name"],
                r["author_account_id"],
                r["body_text"],
                r["inline_path"],
                r["inline_from"],
                r["inline_to"],
                r["is_deleted"],
                r["created_on"],
                r["updated_on"],
            )
            for r in rows
        ],
    )
    return len(rows)


async def pr_ids_with_comments(conn: Executor, repo_slug: str, pr_ids: Iterable[int]) -> set[int]:
    """Quais desses PRs já têm comentário espelhado.

    Serve ao backfill: PR que recebeu a review antes desta tabela existir nunca mais
    teria o `comment_count` mudado, e a review ficaria invisível para sempre.
    """
    ids = list(pr_ids)
    if not ids:
        return set()
    rows = await conn.fetch(
        "SELECT DISTINCT pr_id FROM bb_pr_comment WHERE repo_slug = $1 AND pr_id = ANY($2::int[])",
        repo_slug,
        ids,
    )
    return {r["pr_id"] for r in rows}


async def known_pr_comment_ids(conn: Executor, repo_slug: str, pr_id: int) -> set[int]:
    """IDs já espelhados — o diff contra eles é o que vira evento de comentário novo."""
    rows = await conn.fetch(
        "SELECT id FROM bb_pr_comment WHERE repo_slug = $1 AND pr_id = $2", repo_slug, pr_id
    )
    return {r["id"] for r in rows}


async def pr_comments(conn: Executor, repo_slug: str, pr_id: int) -> list[dict[str, Any]]:
    """Comentários de um PR, do mais antigo para o mais novo.

    Apagados no Bitbucket continuam na linha do tempo (sem corpo): some-los abriria
    um buraco entre o pedido de ajuste e a correção.
    """
    rows = await conn.fetch(
        """
        SELECT id, parent_id, author_name, author_account_id, body_text, inline_path,
               inline_from, inline_to, is_deleted, created_on, updated_on
        FROM bb_pr_comment
        WHERE repo_slug = $1 AND pr_id = $2
        ORDER BY created_on NULLS LAST, id
        """,
        repo_slug,
        pr_id,
    )
    return [dict(r) for r in rows]


async def pull_request(conn: Executor, repo_slug: str, pr_id: int) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        SELECT repo_slug, id, title, state, url, source_branch, destination_branch,
               author_name, participants, created_on, updated_on
        FROM bb_pull_request
        WHERE repo_slug = $1 AND id = $2
        """,
        repo_slug,
        pr_id,
    )
    return dict(row) if row else None


async def set_build_status(conn: Executor, repo_slug: str, pr_id: int, status: str | None) -> None:
    await conn.execute(
        "UPDATE bb_pull_request SET build_status = $3 WHERE repo_slug = $1 AND id = $2",
        repo_slug,
        pr_id,
        status,
    )


async def upsert_branches(conn: Executor, rows: Iterable[dict[str, Any]]) -> None:
    rows = list(rows)
    if not rows:
        return
    await conn.executemany(
        """
        INSERT INTO bb_branch (repo_slug, name, target_hash, target_date, issue_keys, synced_at)
        VALUES ($1, $2, $3, $4, $5, now())
        ON CONFLICT (repo_slug, name) DO UPDATE SET target_hash = EXCLUDED.target_hash,
            target_date = EXCLUDED.target_date, issue_keys = EXCLUDED.issue_keys, synced_at = now()
        """,
        [
            (r["repo_slug"], r["name"], r["target_hash"], r["target_date"], r["issue_keys"])
            for r in rows
        ],
    )


async def counts(conn: Executor) -> dict[str, int]:
    row = await conn.fetchrow(
        """
        SELECT
            (SELECT count(*) FROM bb_repository) AS repositories,
            (SELECT count(*) FROM bb_pull_request) AS pull_requests,
            (SELECT count(*) FROM bb_branch) AS branches
        """
    )
    return dict(row)


async def prune(
    conn: Executor,
    *,
    repo_slugs: list[str],
    my_identities: list[str] | None,
    my_issue_keys: list[str],
) -> dict[str, int]:
    """Tira do espelho repositórios não escolhidos e, com `my_identities`, PRs/branches
    que não são do dev (nem autor, nem participante, nem ligados a tarefas dele)."""
    removed = {"pull_requests": 0, "branches": 0}
    status = await conn.execute(
        "DELETE FROM bb_pull_request WHERE NOT (repo_slug = ANY($1::text[]))", repo_slugs
    )
    removed["pull_requests"] += _affected(status)
    status = await conn.execute(
        "DELETE FROM bb_branch WHERE NOT (repo_slug = ANY($1::text[]))", repo_slugs
    )
    removed["branches"] += _affected(status)
    await conn.execute("DELETE FROM bb_repository WHERE NOT (slug = ANY($1::text[]))", repo_slugs)

    if my_identities is not None:
        status = await conn.execute(
            """
            DELETE FROM bb_pull_request p
            WHERE NOT (
                -- PR gravado antes da migration 0003 não tem autor: NULL não pode salvar a linha
                COALESCE(p.author_account_id = ANY($1::text[]), false)
                OR p.issue_keys && $2::text[]
                OR EXISTS (
                    SELECT 1 FROM jsonb_array_elements(p.participants) x
                    WHERE x->>'account_id' = ANY($1::text[])
                )
            )
            """,
            my_identities,
            my_issue_keys,
        )
        removed["pull_requests"] += _affected(status)
        status = await conn.execute(
            "DELETE FROM bb_branch WHERE NOT (issue_keys && $1::text[])", my_issue_keys
        )
        removed["branches"] += _affected(status)
    return removed


def _affected(status: str) -> int:
    return int(status.rsplit(" ", 1)[-1])


async def reset_repo_cursors(conn: Executor) -> None:
    """Força a carga inicial de novo (ex.: filtro passou de "só os meus" para "todos")."""
    await conn.execute("DELETE FROM sync_state WHERE resource LIKE 'bitbucket:repo:%'")
