from collections.abc import Iterable
from typing import Any

import asyncpg

Executor = asyncpg.Connection | asyncpg.Pool


async def pull_requests_for(conn: Executor, issue_keys: Iterable[str]) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT repo_slug, id, title, state, draft, source_branch, destination_branch, url,
               participants, build_status, comment_count, issue_keys, updated_on
        FROM bb_pull_request
        WHERE issue_keys && $1::text[]
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
