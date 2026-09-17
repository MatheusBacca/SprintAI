"""Contextos da tarefa: CRUD, relações com outras tarefas, resolução e busca."""

from typing import Any

import asyncpg

from repositories.notes_repo import escape_like

Executor = asyncpg.Connection | asyncpg.Pool

CONTEXT_COLUMNS = """
    c.id, c.issue_key, c.kind, c.title, c.body, c.tags, c.status, c.resolved_in_issue_key,
    c.resolution, c.resolved_at, c.source, c.created_at, c.updated_at
"""

UPDATABLE = ("issue_key", "kind", "title", "body", "tags")

# Pontos em aberto primeiro; dentro do grupo, o mais recente.
DEFAULT_ORDER = "(c.kind = 'open_point' AND c.status = 'open') DESC, c.updated_at DESC, c.id DESC"


async def create(conn: asyncpg.Connection, data: dict[str, Any]) -> int:
    return await conn.fetchval(
        """
        INSERT INTO task_context (issue_key, kind, title, body, tags, source)
        VALUES ($1, $2, $3, $4, $5, $6) RETURNING id
        """,
        data["issue_key"],
        data["kind"],
        data["title"],
        data["body"],
        data["tags"],
        data.get("source", "manual"),
    )


async def get(conn: Executor, context_id: int) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        f"SELECT {CONTEXT_COLUMNS} FROM task_context c WHERE c.id = $1", context_id
    )
    return dict(row) if row else None


async def update(conn: asyncpg.Connection, context_id: int, changes: dict[str, Any]) -> bool:
    fields = {k: v for k, v in changes.items() if k in UPDATABLE}
    if not fields:
        return await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM task_context WHERE id = $1)", context_id
        )
    assignments = ", ".join(f"{name} = ${i}" for i, name in enumerate(fields, start=2))
    status = await conn.execute(
        f"UPDATE task_context SET {assignments}, updated_at = now() WHERE id = $1",
        context_id,
        *fields.values(),
    )
    return status.endswith(" 1")


async def replace_relations(
    conn: asyncpg.Connection, context_id: int, relations: list[tuple[str, str]]
) -> None:
    """Troca as relações manuais; a relação `resolves` é da resolução e fica."""
    keys = [key for key, _ in relations]
    await conn.execute(
        """
        DELETE FROM context_relation
        WHERE context_id = $1 AND relation <> 'resolves' AND NOT (issue_key = ANY($2::text[]))
        """,
        context_id,
        keys,
    )
    await conn.executemany(
        """
        INSERT INTO context_relation (context_id, issue_key, relation) VALUES ($1, $2, $3)
        ON CONFLICT (context_id, issue_key) DO UPDATE SET relation = EXCLUDED.relation
        WHERE context_relation.relation <> 'resolves'
        """,
        [(context_id, key, relation) for key, relation in relations],
    )


async def delete(conn: Executor, context_id: int) -> bool:
    status = await conn.execute("DELETE FROM task_context WHERE id = $1", context_id)
    return status.endswith(" 1")


async def resolve(
    conn: asyncpg.Connection, context_id: int, issue_key: str, resolution: str
) -> bool:
    status = await conn.execute(
        """
        UPDATE task_context
        SET status = 'resolved', resolved_in_issue_key = $2, resolution = $3,
            resolved_at = now(), updated_at = now()
        WHERE id = $1 AND kind = 'open_point'
        """,
        context_id,
        issue_key,
        resolution,
    )
    if not status.endswith(" 1"):
        return False
    await conn.execute(
        "DELETE FROM context_relation WHERE context_id = $1 AND relation = 'resolves'", context_id
    )
    # Resolvido na própria tarefa de origem não vira relação com ela mesma.
    await conn.execute(
        """
        INSERT INTO context_relation (context_id, issue_key, relation)
        SELECT $1, $2, 'resolves' FROM task_context WHERE id = $1 AND issue_key <> $2
        ON CONFLICT (context_id, issue_key) DO UPDATE SET relation = 'resolves'
        """,
        context_id,
        issue_key,
    )
    return True


async def reopen(conn: asyncpg.Connection, context_id: int) -> bool:
    status = await conn.execute(
        """
        UPDATE task_context
        SET status = 'open', resolved_in_issue_key = NULL, resolution = '', resolved_at = NULL,
            updated_at = now()
        WHERE id = $1
        """,
        context_id,
    )
    if not status.endswith(" 1"):
        return False
    await conn.execute(
        "DELETE FROM context_relation WHERE context_id = $1 AND relation = 'resolves'", context_id
    )
    return True


async def search(
    conn: Executor,
    *,
    q: str | None = None,
    issue_key: str | None = None,
    kinds: list[str] | None = None,
    status: str | None = None,
    tags: list[str] | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    where: list[str] = []
    args: list[Any] = []

    def arg(value: Any) -> str:
        args.append(value)
        return f"${len(args)}"

    rank_sql = "NULL::real"
    order_sql = DEFAULT_ORDER
    if q and q.strip():
        term = q.strip()
        tsq = f"websearch_to_tsquery('portuguese', f_unaccent({arg(term)}))"
        like = arg(f"%{escape_like(term.lower())}%")
        key = arg(term.upper())
        where.append(
            f"""(
                c.search @@ {tsq}
                OR f_unaccent(lower(c.title || ' ' || c.body)) LIKE f_unaccent({like})
                OR f_unaccent(f_tags_text(c.tags)) LIKE f_unaccent({like})
                OR c.issue_key = {key} OR c.resolved_in_issue_key = {key}
                OR EXISTS (SELECT 1 FROM context_relation r
                           WHERE r.context_id = c.id AND r.issue_key = {key})
            )"""
        )
        title_bonus = (
            f"CASE WHEN f_unaccent(lower(c.title)) LIKE f_unaccent({like}) THEN 0.5 ELSE 0 END"
        )
        rank_sql = f"ts_rank(c.search, {tsq}) + {title_bonus}"
        order_sql = f"rank DESC NULLS LAST, {DEFAULT_ORDER}"
    if issue_key:
        where.append(f"c.issue_key = {arg(issue_key)}")
    if kinds:
        where.append(f"c.kind = ANY({arg(kinds)}::text[])")
    if status:
        where.append(f"c.status = {arg(status)}")
    if tags:
        where.append(f"c.tags @> {arg(tags)}::text[]")

    where_sql = " AND ".join(where) or "true"
    total = await conn.fetchval(f"SELECT count(*) FROM task_context c WHERE {where_sql}", *args)
    rows = await conn.fetch(
        f"""
        SELECT {CONTEXT_COLUMNS}, {rank_sql} AS rank
        FROM task_context c
        WHERE {where_sql}
        ORDER BY {order_sql}
        LIMIT {arg(limit)} OFFSET {arg(offset)}
        """,
        *args,
    )
    return [dict(r) for r in rows], total


async def for_issue(conn: Executor, issue_key: str) -> dict[str, list[dict[str, Any]]]:
    """Contextos da tarefa, os que a citam e os pontos em aberto das tarefas vizinhas."""
    own = await conn.fetch(
        f"SELECT {CONTEXT_COLUMNS} FROM task_context c WHERE c.issue_key = $1 "
        f"ORDER BY {DEFAULT_ORDER}",
        issue_key,
    )
    linked = await conn.fetch(
        f"""
        SELECT {CONTEXT_COLUMNS} FROM task_context c
        WHERE c.issue_key <> $1
          AND (c.resolved_in_issue_key = $1
               OR EXISTS (SELECT 1 FROM context_relation r
                          WHERE r.context_id = c.id AND r.issue_key = $1))
        ORDER BY {DEFAULT_ORDER}
        """,
        issue_key,
    )
    nearby = await conn.fetch(
        f"""
        WITH me AS (SELECT key, parent_key FROM jira_issue WHERE key = $1),
        neighbors AS (
            SELECT parent_key AS key FROM me WHERE parent_key IS NOT NULL
            UNION SELECT i.key FROM jira_issue i, me WHERE i.parent_key = me.key
            UNION SELECT i.key FROM jira_issue i, me
                  WHERE me.parent_key IS NOT NULL AND i.parent_key = me.parent_key
            UNION SELECT target_key FROM jira_issue_link WHERE source_key = $1
            UNION SELECT source_key FROM jira_issue_link WHERE target_key = $1
        )
        SELECT {CONTEXT_COLUMNS} FROM task_context c
        WHERE c.kind = 'open_point' AND c.status = 'open'
          AND c.issue_key IN (SELECT key FROM neighbors WHERE key <> $1)
          AND NOT EXISTS (SELECT 1 FROM context_relation r
                          WHERE r.context_id = c.id AND r.issue_key = $1)
        ORDER BY c.updated_at DESC
        LIMIT 30
        """,
        issue_key,
    )
    return {
        "own": [dict(r) for r in own],
        "linked": [dict(r) for r in linked],
        "nearby_open": [dict(r) for r in nearby],
    }


async def relations(conn: Executor, context_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    rows = await conn.fetch(
        """
        SELECT context_id, issue_key, relation FROM context_relation
        WHERE context_id = ANY($1::bigint[])
        ORDER BY created_at, issue_key
        """,
        context_ids,
    )
    out: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        out.setdefault(row["context_id"], []).append(
            {"key": row["issue_key"], "relation": row["relation"]}
        )
    return out


async def issue_info(conn: Executor, keys: list[str]) -> dict[str, dict[str, Any]]:
    rows = await conn.fetch(
        "SELECT key, summary, status, status_category FROM jira_issue WHERE key = ANY($1::text[])",
        keys,
    )
    return {r["key"]: dict(r) for r in rows}


async def counts(conn: Executor) -> dict[str, Any]:
    rows = await conn.fetch("SELECT kind, count(*)::int AS count FROM task_context GROUP BY kind")
    open_points = await conn.fetchval(
        "SELECT count(*)::int FROM task_context WHERE kind = 'open_point' AND status = 'open'"
    )
    return {"open_points": open_points, "by_kind": {r["kind"]: r["count"] for r in rows}}
