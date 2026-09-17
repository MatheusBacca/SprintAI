from collections.abc import Iterable
from typing import Any

import asyncpg

from repositories.notes_repo import escape_like

Executor = asyncpg.Connection | asyncpg.Pool


async def issue(conn: Executor, key: str) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        SELECT key, project_key, issue_type, is_subtask, summary, description_adf, description_text,
               status, status_category, priority, assignee_account_id, assignee_name,
               reporter_name, story_points, due_date, parent_key, labels, components,
               created_at, updated_at, resolved_at, synced_at
        FROM jira_issue WHERE key = $1
        """,
        key,
    )
    return dict(row) if row else None


async def sprints_of(conn: Executor, key: str) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT s.id, s.name, s.state, s.squad
        FROM jira_sprint_issue si JOIN jira_sprint s ON s.id = si.sprint_id
        WHERE si.issue_key = $1
        ORDER BY s.start_date DESC NULLS LAST, s.id DESC
        """,
        key,
    )
    return [dict(r) for r in rows]


async def comments(conn: Executor, key: str) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT id, author_name, body_adf, body_text, created_at, updated_at
        FROM jira_comment WHERE issue_key = $1 ORDER BY created_at
        """,
        key,
    )
    return [dict(r) for r in rows]


async def links(conn: Executor, key: str) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT l.id, l.target_key, l.link_type, l.direction, l.label,
               COALESCE(t.summary, l.target_summary) AS summary,
               COALESCE(t.status, l.target_status) AS status,
               t.status_category,
               COALESCE(t.issue_type, l.target_type) AS issue_type,
               t.assignee_name,
               (t.key IS NOT NULL) AS in_mirror
        FROM jira_issue_link l
        LEFT JOIN jira_issue t ON t.key = l.target_key
        WHERE l.source_key = $1
        ORDER BY l.link_type, l.direction, l.target_key
        """,
        key,
    )
    return [dict(r) for r in rows]


async def related_issues(conn: Executor, keys: Iterable[str]) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT key, summary, status, status_category, issue_type, assignee_name, parent_key
        FROM jira_issue WHERE key = ANY($1::text[])
        """,
        list(keys),
    )
    return [dict(r) for r in rows]


async def children(conn: Executor, key: str) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT key, summary, status, status_category, issue_type, assignee_name
        FROM jira_issue WHERE parent_key = $1 ORDER BY key
        """,
        key,
    )
    return [dict(r) for r in rows]


async def pick(
    conn: Executor,
    *,
    terms: list[str],
    account_id: str | None,
    limit: int,
    mine: bool = False,
) -> list[dict[str, Any]]:
    """Tarefas do espelho para escolher numa lista (vínculo do lembrete).

    Cada termo precisa aparecer em algum campo — chave, título, status, tipo,
    responsável, pai, labels ou componentes —, sem acento nem caixa: "qualif 8458"
    acha a WAI-8458 pelo título e pelo número juntos. Concluídas vão para o fim e,
    entre as abertas, as minhas vêm primeiro. `mine` restringe às minhas — sem
    `account_id` salvo não há como saber quais são, e nada é filtrado.
    """
    haystack = """f_unaccent(lower(concat_ws(' ', i.key, i.summary, i.status, i.issue_type,
        i.assignee_name, i.parent_key, array_to_string(i.labels, ' '),
        array_to_string(i.components, ' '))))"""
    likes = [f"%{escape_like(t.lower())}%" for t in terms]
    rows = await conn.fetch(
        f"""
        SELECT i.key, i.summary, i.issue_type, i.status, i.status_category, i.assignee_name,
               coalesce(i.assignee_account_id = $2, false) AS is_mine
        FROM jira_issue i
        WHERE NOT EXISTS (
            SELECT 1 FROM unnest($1::text[]) AS t(like_term)
            WHERE {haystack} NOT LIKE f_unaccent(t.like_term)
        )
          AND (NOT $5::boolean OR $2::text IS NULL OR i.assignee_account_id = $2)
        ORDER BY upper(i.key) = upper($3) DESC,
                 i.status_category = 'done',
                 coalesce(i.assignee_account_id = $2, false) DESC,
                 i.updated_at DESC NULLS LAST
        LIMIT $4
        """,
        likes,
        account_id,
        " ".join(terms),
        limit,
        mine,
    )
    return [dict(r) for r in rows]
