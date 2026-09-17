"""Visão Semana: tarefas minhas soltas, com prazo, cards "Analisar e fatiar" e lembretes.

"Minhas" = Responsável é o dev conectado (`account_id` da conexão). Sem `account_id`
salvo, não filtra — com o escopo padrão ("só as minhas") o espelho já é só dele.
"""

from datetime import date, datetime
from typing import Any

import asyncpg

from repositories.notes_repo import NOTE_COLUMNS

Executor = asyncpg.Connection | asyncpg.Pool

# Título de card de fatiamento ("Analisar e fatiar a: ...", "Analisar e Fatiar - ...").
SLICING_PATTERN = "analisar e fatiar%"
# Épico é contêiner: não é trabalho a fazer na semana.
EPIC_TYPES = ["Épico", "Epic"]

ISSUE_COLUMNS = """
    i.key, i.summary, i.issue_type, i.status, i.status_category, i.priority, i.story_points,
    i.due_date, i.parent_key, p.summary AS parent_summary, i.updated_at, i.resolved_at,
    sp.name AS sprint_name, sp.state AS sprint_state,
    (SELECT count(*)::int FROM task_context c
     WHERE c.issue_key = i.key AND c.kind = 'open_point' AND c.status = 'open') AS open_points
"""

# Sprint mais relevante da tarefa: ativa > futura > fechada mais recente.
SPRINT_JOIN = """
    LEFT JOIN jira_issue p ON p.key = i.parent_key
    LEFT JOIN LATERAL (
        SELECT s.name, s.state FROM jira_sprint_issue si JOIN jira_sprint s ON s.id = si.sprint_id
        WHERE si.issue_key = i.key
        ORDER BY CASE s.state WHEN 'active' THEN 0 WHEN 'future' THEN 1 ELSE 2 END,
                 s.start_date DESC NULLS LAST
        LIMIT 1
    ) sp ON true
"""

MINE = "($1::text IS NULL OR i.assignee_account_id = $1)"
PRIORITY_ORDER = """
    CASE i.priority WHEN 'Highest' THEN 0 WHEN 'High' THEN 1 WHEN 'Medium' THEN 2
                    WHEN 'Low' THEN 3 WHEN 'Lowest' THEN 4 ELSE 5 END
"""


async def without_sprint(conn: Executor, account_id: str | None) -> list[dict[str, Any]]:
    """Minhas em aberto que não estão em sprint ativa nem futura (inclui sobra de fechada)."""
    rows = await conn.fetch(
        f"""
        SELECT {ISSUE_COLUMNS} FROM jira_issue i {SPRINT_JOIN}
        WHERE {MINE} AND i.status_category <> 'done'
          AND NOT (i.issue_type = ANY($2::text[]))
          AND f_unaccent(lower(i.summary)) NOT LIKE $3
          AND NOT EXISTS (
              SELECT 1 FROM jira_sprint_issue si JOIN jira_sprint s ON s.id = si.sprint_id
              WHERE si.issue_key = i.key AND s.state IN ('active', 'future'))
        ORDER BY (sp.state = 'closed') DESC NULLS LAST, {PRIORITY_ORDER}, i.updated_at DESC
        """,
        account_id,
        EPIC_TYPES,
        SLICING_PATTERN,
    )
    return [dict(r) for r in rows]


async def due_between(
    conn: Executor, account_id: str | None, start: date, end: date
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        f"""
        SELECT {ISSUE_COLUMNS} FROM jira_issue i {SPRINT_JOIN}
        WHERE {MINE} AND i.due_date BETWEEN $2 AND $3
        ORDER BY i.due_date, (i.status_category = 'done'), {PRIORITY_ORDER}
        """,
        account_id,
        start,
        end,
    )
    return [dict(r) for r in rows]


async def overdue_before(
    conn: Executor, account_id: str | None, start: date
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        f"""
        SELECT {ISSUE_COLUMNS} FROM jira_issue i {SPRINT_JOIN}
        WHERE {MINE} AND i.due_date < $2 AND i.status_category <> 'done'
        ORDER BY i.due_date, {PRIORITY_ORDER}
        """,
        account_id,
        start,
    )
    return [dict(r) for r in rows]


async def slicing_cards(
    conn: Executor, account_id: str | None, since: datetime, until: datetime
) -> list[dict[str, Any]]:
    """Cards "Analisar e fatiar": os em aberto e os concluídos dentro da semana."""
    rows = await conn.fetch(
        f"""
        SELECT {ISSUE_COLUMNS} FROM jira_issue i {SPRINT_JOIN}
        WHERE {MINE} AND f_unaccent(lower(i.summary)) LIKE $2
          AND (i.status_category <> 'done'
               OR coalesce(i.resolved_at, i.updated_at) >= $3
                  AND coalesce(i.resolved_at, i.updated_at) < $4)
        ORDER BY (i.status_category = 'done'),
                 CASE i.status_category WHEN 'indeterminate' THEN 0 ELSE 1 END,
                 i.updated_at DESC
        """,
        account_id,
        SLICING_PATTERN,
        since,
        until,
    )
    return [dict(r) for r in rows]


async def reminders_between(
    conn: Executor, since: datetime, until: datetime
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        f"""
        SELECT {NOTE_COLUMNS}, NULL::real AS rank FROM note n
        WHERE NOT n.archived AND n.remind_at >= $1 AND n.remind_at < $2
        ORDER BY n.remind_at
        """,
        since,
        until,
    )
    return [dict(r) for r in rows]


async def pending_reminders_before(conn: Executor, since: datetime) -> list[dict[str, Any]]:
    """Lembretes de antes da semana que venceram e ainda não foram vistos."""
    rows = await conn.fetch(
        f"""
        SELECT {NOTE_COLUMNS}, NULL::real AS rank FROM note n
        WHERE NOT n.archived AND n.remind_at < $1 AND n.reminded_at IS NULL
        ORDER BY n.remind_at
        """,
        since,
    )
    return [dict(r) for r in rows]
