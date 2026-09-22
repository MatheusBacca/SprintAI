from collections.abc import Iterable
from typing import Any

import asyncpg

Executor = asyncpg.Connection | asyncpg.Pool


async def pull_requests_for(conn: Executor, issue_keys: Iterable[str]) -> list[dict[str, Any]]:
    """O PR e, do histórico, as duas datas que dizem se a correção já subiu.

    O espelho guarda só o estado atual do participante — "pediu ajustes" fica lá até o
    revisor mexer de novo. Quando a correção entrou é o `activity_event` que sabe.
    """
    rows = await conn.fetch(
        """
        SELECT p.repo_slug, p.id, p.title, p.state, p.draft, p.source_branch,
               p.destination_branch, p.url, p.participants, p.build_status, p.comment_count,
               p.issue_keys, p.updated_on,
               h.last_changes_requested_at, h.last_commit_at
        FROM bb_pull_request p
        LEFT JOIN LATERAL (
            SELECT max(e.occurred_at) FILTER (WHERE e.kind = 'pr_changes_requested')
                       AS last_changes_requested_at,
                   max(e.occurred_at) FILTER (WHERE e.kind = 'pr_commit') AS last_commit_at
            FROM activity_event e
            WHERE e.source = 'bitbucket' AND e.repo_slug = p.repo_slug AND e.pr_id = p.id
        ) h ON true
        WHERE p.issue_keys && $1::text[]
        """,
        list(issue_keys),
    )
    return [dict(r) for r in rows]


async def branches_for(conn: Executor, issue_keys: Iterable[str]) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT repo_slug, name, target_date, issue_keys
        FROM bb_branch
        WHERE issue_keys && $1::text[]
        """,
        list(issue_keys),
    )
    return [dict(r) for r in rows]
