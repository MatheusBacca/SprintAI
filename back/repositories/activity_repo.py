"""Leitura e escrita das transições de status e do feed de atividade (B8).

As duas escritas são idempotentes (`ON CONFLICT DO NOTHING` na chave única): rodar o
sync de novo sobre o mesmo changelog não duplica nada.
"""

from collections.abc import Iterable
from datetime import datetime
from typing import Any

import asyncpg

Executor = asyncpg.Connection | asyncpg.Pool

EVENT_COLUMNS = """
    e.id, e.dedupe_key, e.source, e.kind, e.issue_key, e.repo_slug, e.pr_id, e.actor_name,
    e.actor_is_me, e.occurred_at, e.title, e.detail
"""


async def insert_transitions(conn: Executor, rows: Iterable[dict[str, Any]]) -> int:
    rows = list(rows)
    if not rows:
        return 0
    inserted = await conn.fetchval(
        """
        WITH novo AS (
            INSERT INTO jira_status_transition (changelog_id, issue_key, from_status, to_status,
                from_category, to_category, author_name, changed_at)
            SELECT * FROM unnest($1::text[], $2::text[], $3::text[], $4::text[], $5::text[],
                                 $6::text[], $7::text[], $8::timestamptz[])
            ON CONFLICT (changelog_id) DO NOTHING
            RETURNING 1
        )
        SELECT count(*)::int FROM novo
        """,
        [r["changelog_id"] for r in rows],
        [r["issue_key"] for r in rows],
        [r["from_status"] for r in rows],
        [r["to_status"] for r in rows],
        [r["from_category"] for r in rows],
        [r["to_category"] for r in rows],
        [r["author_name"] for r in rows],
        [r["changed_at"] for r in rows],
    )
    return inserted or 0


async def insert_events(conn: Executor, rows: Iterable[dict[str, Any]]) -> int:
    rows = list(rows)
    if not rows:
        return 0
    inserted = 0
    for row in rows:
        done = await conn.fetchval(
            """
            INSERT INTO activity_event (dedupe_key, source, kind, issue_key, repo_slug, pr_id,
                actor_name, actor_is_me, occurred_at, title, detail)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (dedupe_key) DO NOTHING
            RETURNING 1
            """,
            row["dedupe_key"],
            row["source"],
            row["kind"],
            row["issue_key"],
            row["repo_slug"],
            row["pr_id"],
            row["actor_name"],
            row["actor_is_me"],
            row["occurred_at"],
            row["title"],
            row.get("detail") or {},
        )
        inserted += 1 if done else 0
    return inserted


async def status_categories(conn: Executor) -> dict[str, str]:
    """Status → categoria, pelo que já existe no espelho (o changelog não traz a categoria)."""
    rows = await conn.fetch(
        "SELECT DISTINCT status, status_category FROM jira_issue WHERE status IS NOT NULL"
    )
    return {r["status"]: r["status_category"] for r in rows}


async def comments_of(
    conn: Executor, issue_keys: Iterable[str], *, since: datetime | None = None
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT id, issue_key, author_name, author_account_id, body_text, created_at, updated_at
        FROM jira_comment
        WHERE issue_key = ANY($1::text[])
          AND ($2::timestamptz IS NULL OR coalesce(updated_at, created_at) >= $2)
        """,
        list(issue_keys),
        since,
    )
    return [dict(r) for r in rows]


async def transitions_for(conn: Executor, issue_keys: Iterable[str]) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT issue_key, from_status, to_status, from_category, to_category, changed_at
        FROM jira_status_transition
        WHERE issue_key = ANY($1::text[])
        ORDER BY issue_key, changed_at
        """,
        list(issue_keys),
    )
    return [dict(r) for r in rows]


async def feed(
    conn: Executor,
    *,
    before: tuple[datetime, int] | None = None,
    limit: int = 30,
    source: str | None = None,
    only_others: bool = False,
) -> list[dict[str, Any]]:
    """Do mais novo para o mais antigo, paginado por cursor `(occurred_at, id)`."""
    rows = await conn.fetch(
        f"""
        SELECT {EVENT_COLUMNS}, i.summary AS issue_summary, i.status AS issue_status
        FROM activity_event e
        LEFT JOIN jira_issue i ON i.key = e.issue_key
        WHERE ($1::timestamptz IS NULL OR (e.occurred_at, e.id) < ($1::timestamptz, $2::bigint))
          AND ($3::text IS NULL OR e.source = $3)
          AND (NOT $4::boolean OR NOT e.actor_is_me)
        ORDER BY e.occurred_at DESC, e.id DESC
        LIMIT $5
        """,
        before[0] if before else None,
        before[1] if before else 0,
        source,
        only_others,
        limit,
    )
    return [dict(r) for r in rows]


async def events_for_pr(conn: Executor, repo_slug: str, pr_id: int) -> list[dict[str, Any]]:
    """Eventos de UM PR, do mais antigo para o mais novo (é uma linha do tempo, não um feed)."""
    rows = await conn.fetch(
        f"""
        SELECT {EVENT_COLUMNS}
        FROM activity_event e
        WHERE e.source = 'bitbucket' AND e.repo_slug = $1 AND e.pr_id = $2
        ORDER BY e.occurred_at, e.id
        """,
        repo_slug,
        pr_id,
    )
    return [dict(r) for r in rows]


async def purge_before(conn: Executor, cutoff: datetime) -> int:
    return int(
        (await conn.execute("DELETE FROM activity_event WHERE occurred_at < $1", cutoff)).split()[
            -1
        ]
    )


async def counts(conn: Executor) -> dict[str, int]:
    row = await conn.fetchrow(
        """
        SELECT (SELECT count(*) FROM activity_event) AS events,
               (SELECT count(*) FROM jira_status_transition) AS transitions
        """
    )
    return dict(row)


async def mine_updated_since(conn: Executor, account_id: str | None, since: datetime) -> list[str]:
    """Backfill: só as minhas tarefas mexidas dentro da janela."""
    rows = await conn.fetch(
        """
        SELECT key FROM jira_issue
        WHERE ($1::text IS NULL OR assignee_account_id = $1) AND updated_at >= $2
        ORDER BY updated_at DESC
        """,
        account_id,
        since,
    )
    return [r["key"] for r in rows]


async def recent_by_sprint(
    conn: Executor,
    sprint_ids: Iterable[int],
    *,
    since: datetime,
    account_id: str | None,
    only_others: bool = True,
) -> list[dict[str, Any]]:
    """Tarefas das sprints que receberam evento desde `since` — uma linha por tarefa,
    com o evento mais recente e quantos houve. Épico não é trabalho: fica de fora."""
    rows = await conn.fetch(
        """
        SELECT * FROM (
            SELECT DISTINCT ON (si.sprint_id, e.issue_key)
                   si.sprint_id, e.issue_key, e.kind, e.title, e.actor_name, e.occurred_at,
                   e.source, e.repo_slug, e.pr_id,
                   i.summary, i.status, i.status_category, i.story_points,
                   count(*) OVER (PARTITION BY si.sprint_id, e.issue_key)::int AS event_count
            FROM activity_event e
            JOIN jira_sprint_issue si ON si.issue_key = e.issue_key
            JOIN jira_issue i ON i.key = e.issue_key
            WHERE si.sprint_id = ANY($1::int[])
              AND e.occurred_at >= $2
              AND (NOT $3::boolean OR NOT e.actor_is_me)
              AND ($4::text IS NULL OR i.assignee_account_id = $4)
              AND f_unaccent(lower(i.issue_type)) <> ALL (ARRAY['epico', 'epic'])
            ORDER BY si.sprint_id, e.issue_key, e.occurred_at DESC, e.id DESC
        ) u
        ORDER BY u.sprint_id, u.occurred_at DESC
        """,
        list(sprint_ids),
        since,
        only_others,
        account_id,
    )
    return [dict(r) for r in rows]
