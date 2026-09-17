from collections.abc import Iterable
from typing import Any

import asyncpg

Executor = asyncpg.Connection | asyncpg.Pool

ISSUE_COLUMNS = """
    i.key, i.summary, i.issue_type, i.status, i.status_category, i.story_points,
    i.assignee_account_id, i.assignee_name, i.parent_key, i.updated_at
"""


async def scope_sprints(conn: Executor, my_account_id: str | None) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT s.id, s.name, s.state, s.squad, s.goal, s.board_id, s.start_date, s.end_date,
               s.complete_date,
               count(i.key)::int AS issue_count,
               count(i.key) FILTER (WHERE i.assignee_account_id = $1)::int AS mine_count,
               count(i.key) FILTER (WHERE i.status_category = 'done')::int AS done_count
        FROM jira_sprint s
        LEFT JOIN jira_sprint_issue si ON si.sprint_id = s.id
        LEFT JOIN jira_issue i ON i.key = si.issue_key
        WHERE s.in_scope
        GROUP BY s.id
        ORDER BY CASE s.state WHEN 'active' THEN 0 WHEN 'future' THEN 1 ELSE 2 END,
                 CASE WHEN s.state = 'closed' THEN s.complete_date END DESC NULLS LAST,
                 s.start_date NULLS LAST, s.id
        """,
        my_account_id,
    )
    return [dict(r) for r in rows]


async def sprint(conn: Executor, sprint_id: int) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        SELECT id, name, state, squad, goal, board_id, start_date, end_date, complete_date
        FROM jira_sprint WHERE id = $1
        """,
        sprint_id,
    )
    return dict(row) if row else None


async def sprint_issues(conn: Executor, sprint_id: int) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        f"""
        SELECT {ISSUE_COLUMNS}
        FROM jira_sprint_issue si JOIN jira_issue i ON i.key = si.issue_key
        WHERE si.sprint_id = $1
        """,
        sprint_id,
    )
    return [dict(r) for r in rows]


async def issues_by_keys(conn: Executor, keys: Iterable[str]) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        f"SELECT {ISSUE_COLUMNS} FROM jira_issue i WHERE i.key = ANY($1::text[])", list(keys)
    )
    return [dict(r) for r in rows]


async def links_from(conn: Executor, keys: Iterable[str]) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT source_key, target_key, link_type, direction, label, target_summary,
               target_status, target_type
        FROM jira_issue_link WHERE source_key = ANY($1::text[])
        """,
        list(keys),
    )
    return [dict(r) for r in rows]
