"""Consultas do progresso e da timeline (B9 e B10).

Uma consulta só devolve as minhas tarefas das sprints pedidas com tudo que a Home usa:
etapa (status), peso (SP), pai para agrupar as linhas e as datas das barras.
"""

from collections.abc import Iterable
from typing import Any

import asyncpg

Executor = asyncpg.Connection | asyncpg.Pool

TIMELINE_COLUMNS = """
    i.key, i.summary, i.issue_type, i.status, i.status_category, i.priority, i.story_points,
    i.assignee_account_id, i.assignee_name, i.due_date, i.created_at, i.updated_at, i.resolved_at,
    i.parent_key, p.summary AS parent_summary, p.issue_type AS parent_type,
    si.sprint_id
"""


async def distinct_statuses(conn: Executor) -> list[dict[str, Any]]:
    """Status que existem no espelho — a tela de Configurações ordena e dá peso a eles."""
    rows = await conn.fetch(
        """
        SELECT status, status_category, count(*)::int AS issue_count
        FROM jira_issue
        GROUP BY status, status_category
        ORDER BY count(*) DESC, status
        """
    )
    return [dict(r) for r in rows]


async def sprint_issues(
    conn: Executor, sprint_ids: Iterable[int], account_id: str | None
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        f"""
        SELECT {TIMELINE_COLUMNS}
        FROM jira_sprint_issue si
        JOIN jira_issue i ON i.key = si.issue_key
        LEFT JOIN jira_issue p ON p.key = i.parent_key
        WHERE si.sprint_id = ANY($1::int[])
          AND ($2::text IS NULL OR i.assignee_account_id = $2)
        ORDER BY i.parent_key NULLS LAST, i.key
        """,
        list(sprint_ids),
        account_id,
    )
    return [dict(r) for r in rows]


async def sprints_by_ids(conn: Executor, sprint_ids: Iterable[int]) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT id, name, state, squad, goal, board_id, start_date, end_date, complete_date
        FROM jira_sprint WHERE id = ANY($1::int[])
        ORDER BY start_date NULLS LAST, id
        """,
        list(sprint_ids),
    )
    return [dict(r) for r in rows]


async def timeline_sprints(conn: Executor, *, include_next: bool) -> list[dict[str, Any]]:
    """Sprints ativas do escopo e, se pedido, a próxima futura que já tem data."""
    rows = await conn.fetch(
        """
        SELECT id, name, state, squad, goal, board_id, start_date, end_date, complete_date
        FROM jira_sprint WHERE in_scope AND state = 'active'
        ORDER BY start_date NULLS LAST, id
        """
    )
    sprints = [dict(r) for r in rows]
    if include_next:
        next_row = await conn.fetchrow(
            """
            SELECT id, name, state, squad, goal, board_id, start_date, end_date, complete_date
            FROM jira_sprint
            WHERE in_scope AND state = 'future' AND start_date IS NOT NULL
            ORDER BY start_date
            LIMIT 1
            """
        )
        if next_row:
            sprints.append(dict(next_row))
    return sprints


async def blocks_links(conn: Executor, keys: Iterable[str]) -> list[dict[str, Any]]:
    """Setas "bloqueia" entre as tarefas desenhadas (as duas pontas precisam estar na tela)."""
    rows = await conn.fetch(
        """
        SELECT source_key, target_key FROM jira_issue_link
        WHERE link_type = 'Blocks' AND direction = 'outward'
          AND source_key = ANY($1::text[]) AND target_key = ANY($1::text[])
        """,
        list(keys),
    )
    return [dict(r) for r in rows]
