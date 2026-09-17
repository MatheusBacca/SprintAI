from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal
from typing import Any

import asyncpg

from services.sync.mappers import IssueRows

Executor = asyncpg.Connection | asyncpg.Pool


async def upsert_board(conn: Executor, row: dict[str, Any]) -> None:
    await conn.execute(
        """
        INSERT INTO jira_board (id, name, type, project_key, project_name, synced_at)
        VALUES ($1, $2, $3, $4, $5, now())
        ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, type = EXCLUDED.type,
            project_key = EXCLUDED.project_key, project_name = EXCLUDED.project_name,
            synced_at = now()
        """,
        row["id"],
        row["name"],
        row["type"],
        row.get("project_key"),
        row.get("project_name"),
    )


async def upsert_sprints(conn: Executor, rows: Iterable[dict[str, Any]]) -> None:
    rows = list(rows)
    if not rows:
        return
    await conn.executemany(
        """
        INSERT INTO jira_sprint (id, board_id, name, state, squad, goal, start_date, end_date,
                                 complete_date, synced_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, now())
        ON CONFLICT (id) DO UPDATE SET
            board_id = COALESCE(EXCLUDED.board_id, jira_sprint.board_id),
            name = EXCLUDED.name, state = EXCLUDED.state, squad = EXCLUDED.squad,
            goal = COALESCE(EXCLUDED.goal, jira_sprint.goal),
            start_date = COALESCE(EXCLUDED.start_date, jira_sprint.start_date),
            end_date = COALESCE(EXCLUDED.end_date, jira_sprint.end_date),
            complete_date = COALESCE(EXCLUDED.complete_date, jira_sprint.complete_date),
            synced_at = now()
        """,
        [
            (
                r["id"],
                r["board_id"],
                r["name"],
                r["state"],
                r["squad"],
                r["goal"],
                r["start_date"],
                r["end_date"],
                r["complete_date"],
            )
            for r in rows
        ],
    )


async def set_sprints_in_scope(conn: Executor, board_ids: list[int], sprint_ids: list[int]) -> None:
    await conn.execute(
        """
        UPDATE jira_sprint SET in_scope = (id = ANY($2::int[]))
        WHERE board_id = ANY($1::int[]) OR in_scope
        """,
        board_ids,
        sprint_ids,
    )


async def closed_sprints_pending(conn: Executor, sprint_ids: list[int]) -> set[int]:
    rows = await conn.fetch(
        "SELECT id FROM jira_sprint WHERE id = ANY($1::int[]) AND issues_synced_at IS NULL",
        sprint_ids,
    )
    return {r["id"] for r in rows}


async def mark_sprint_issues_synced(conn: Executor, sprint_ids: Iterable[int]) -> None:
    await conn.execute(
        "UPDATE jira_sprint SET issues_synced_at = now() WHERE id = ANY($1::int[])",
        list(sprint_ids),
    )


async def local_updated_at(conn: Executor, keys: Iterable[str]) -> dict[str, datetime]:
    rows = await conn.fetch(
        "SELECT key, updated_at FROM jira_issue WHERE key = ANY($1::text[])", list(keys)
    )
    return {r["key"]: r["updated_at"] for r in rows}


async def existing_keys(conn: Executor, keys: Iterable[str]) -> set[str]:
    rows = await conn.fetch("SELECT key FROM jira_issue WHERE key = ANY($1::text[])", list(keys))
    return {r["key"] for r in rows}


def _decimal(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


async def save_issue(conn: asyncpg.Connection, rows: IssueRows) -> None:
    """Grava issue + sprints + links + comentários de uma vez (chamar dentro de transação)."""
    i = rows.issue
    # Issue movida de projeto volta com chave nova e mesmo id: remove a linha antiga.
    await conn.execute("DELETE FROM jira_issue WHERE id = $1 AND key <> $2", i["id"], i["key"])
    await conn.execute(
        """
        INSERT INTO jira_issue (key, id, project_key, issue_type, is_subtask, summary,
            description_adf, description_text, status, status_category, priority,
            assignee_account_id, assignee_name, reporter_name, story_points, due_date,
            parent_key, labels, components, created_at, updated_at, resolved_at, raw, synced_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17,
                $18, $19, $20, $21, $22, $23, now())
        ON CONFLICT (key) DO UPDATE SET
            id = EXCLUDED.id, project_key = EXCLUDED.project_key,
            issue_type = EXCLUDED.issue_type, is_subtask = EXCLUDED.is_subtask,
            summary = EXCLUDED.summary, description_adf = EXCLUDED.description_adf,
            description_text = EXCLUDED.description_text, status = EXCLUDED.status,
            status_category = EXCLUDED.status_category, priority = EXCLUDED.priority,
            assignee_account_id = EXCLUDED.assignee_account_id,
            assignee_name = EXCLUDED.assignee_name, reporter_name = EXCLUDED.reporter_name,
            story_points = EXCLUDED.story_points, due_date = EXCLUDED.due_date,
            parent_key = EXCLUDED.parent_key, labels = EXCLUDED.labels,
            components = EXCLUDED.components, created_at = EXCLUDED.created_at,
            updated_at = EXCLUDED.updated_at, resolved_at = EXCLUDED.resolved_at,
            raw = EXCLUDED.raw, synced_at = now()
        """,
        i["key"],
        i["id"],
        i["project_key"],
        i["issue_type"],
        i["is_subtask"],
        i["summary"],
        i["description_adf"],
        i["description_text"],
        i["status"],
        i["status_category"],
        i["priority"],
        i["assignee_account_id"],
        i["assignee_name"],
        i["reporter_name"],
        _decimal(i["story_points"]),
        i["due_date"],
        i["parent_key"],
        i["labels"],
        i["components"],
        i["created_at"],
        i["updated_at"],
        i["resolved_at"],
        i["raw"],
    )

    await upsert_sprints(conn, rows.sprints)
    sprint_ids = [s["id"] for s in rows.sprints]
    await conn.execute(
        "DELETE FROM jira_sprint_issue WHERE issue_key = $1 AND NOT (sprint_id = ANY($2::int[]))",
        i["key"],
        sprint_ids,
    )
    if sprint_ids:
        await conn.executemany(
            "INSERT INTO jira_sprint_issue (sprint_id, issue_key) VALUES ($1, $2) "
            "ON CONFLICT DO NOTHING",
            [(sid, i["key"]) for sid in sprint_ids],
        )

    await conn.execute("DELETE FROM jira_issue_link WHERE source_key = $1", i["key"])
    if rows.links:
        await conn.executemany(
            """
            INSERT INTO jira_issue_link (id, source_key, target_key, link_type, direction, label,
                target_summary, target_status, target_type)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT DO NOTHING
            """,
            [
                (
                    link["id"],
                    link["source_key"],
                    link["target_key"],
                    link["link_type"],
                    link["direction"],
                    link["label"],
                    link["target_summary"],
                    link["target_status"],
                    link["target_type"],
                )
                for link in rows.links
            ],
        )

    await replace_comments(conn, i["key"], rows.comments)


async def replace_comments(
    conn: asyncpg.Connection, issue_key: str, comments: list[dict[str, Any]]
) -> None:
    await conn.execute(
        "DELETE FROM jira_comment WHERE issue_key = $1 AND NOT (id = ANY($2::text[]))",
        issue_key,
        [c["id"] for c in comments],
    )
    if comments:
        await conn.executemany(
            """
            INSERT INTO jira_comment (id, issue_key, author_name, author_account_id, body_adf,
                body_text, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (id) DO UPDATE SET issue_key = EXCLUDED.issue_key,
                author_name = EXCLUDED.author_name, author_account_id = EXCLUDED.author_account_id,
                body_adf = EXCLUDED.body_adf, body_text = EXCLUDED.body_text,
                updated_at = EXCLUDED.updated_at
            """,
            [
                (
                    c["id"],
                    c["issue_key"],
                    c["author_name"],
                    c["author_account_id"],
                    c["body_adf"],
                    c["body_text"],
                    c["created_at"],
                    c["updated_at"],
                )
                for c in comments
            ],
        )


async def replace_sprint_members(conn: Executor, sprint_id: int, issue_keys: Iterable[str]) -> None:
    """Membros atuais de uma sprint ativa/futura (tira quem saiu dela)."""
    keys = list(issue_keys)
    await conn.execute(
        "DELETE FROM jira_sprint_issue WHERE sprint_id = $1 AND NOT (issue_key = ANY($2::text[]))",
        sprint_id,
        keys,
    )
    await conn.execute(
        """
        INSERT INTO jira_sprint_issue (sprint_id, issue_key)
        SELECT $1, key FROM jira_issue WHERE key = ANY($2::text[])
        ON CONFLICT DO NOTHING
        """,
        sprint_id,
        keys,
    )


async def counts(conn: Executor) -> dict[str, int]:
    row = await conn.fetchrow(
        """
        SELECT
            (SELECT count(*) FROM jira_issue) AS issues,
            (SELECT count(*) FROM jira_sprint WHERE in_scope) AS sprints_in_scope,
            (SELECT count(*) FROM jira_comment) AS comments,
            (SELECT count(*) FROM jira_issue_link) AS links
        """
    )
    return dict(row)


async def scope_sprints(conn: Executor) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT s.id, s.name, s.state, s.squad, s.board_id, s.start_date, s.end_date,
               s.issues_synced_at, count(si.issue_key)::int AS issue_count
        FROM jira_sprint s
        LEFT JOIN jira_sprint_issue si ON si.sprint_id = s.id
        WHERE s.in_scope
        GROUP BY s.id
        ORDER BY CASE s.state WHEN 'active' THEN 0 WHEN 'future' THEN 1 ELSE 2 END,
                 s.squad NULLS LAST, s.end_date DESC NULLS LAST, s.id DESC
        """
    )
    return [dict(r) for r in rows]


async def prune_not_mine(conn: asyncpg.Connection, account_id: str) -> int:
    """Remove do espelho o que não é do dev: tarefas de outros que não são pais
    (campo parent ou link de hierarquia) de tarefas dele. Devolve quantas saíram."""
    from services.hierarchy import HIERARCHY_LINK_TYPES, PARENT_ISSUE_TYPES

    await conn.execute(
        """
        DELETE FROM jira_sprint_issue si USING jira_issue i
        WHERE si.issue_key = i.key AND i.assignee_account_id IS DISTINCT FROM $1
        """,
        account_id,
    )
    status = await conn.execute(
        """
        WITH RECURSIVE keep(key) AS (
            SELECT key FROM jira_issue WHERE assignee_account_id = $1
            UNION
            SELECT up.key
            FROM keep k
            CROSS JOIN LATERAL (
                SELECT i.parent_key AS key FROM jira_issue i
                WHERE i.key = k.key AND i.parent_key IS NOT NULL
                UNION ALL
                SELECT l.target_key FROM jira_issue_link l
                WHERE l.source_key = k.key
                  AND l.link_type = ANY($2::text[]) AND l.target_type = ANY($3::text[])
            ) up
        )
        DELETE FROM jira_issue WHERE key NOT IN (SELECT key FROM keep)
        """,
        account_id,
        sorted(HIERARCHY_LINK_TYPES),
        sorted(PARENT_ISSUE_TYPES),
    )
    return int(status.rsplit(" ", 1)[-1])


async def my_issue_keys(conn: Executor, account_id: str) -> list[str]:
    rows = await conn.fetch("SELECT key FROM jira_issue WHERE assignee_account_id = $1", account_id)
    return [r["key"] for r in rows]


async def reset_closed_sprints(conn: Executor) -> None:
    """Força recarregar as sprints fechadas (ex.: escopo passou de "só as minhas" para "todas")."""
    await conn.execute("UPDATE jira_sprint SET issues_synced_at = NULL")
