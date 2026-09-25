"""Lembretes: CRUD e busca.

Busca combina:
- full-text em português sem acento (título e tags pesam mais que o corpo);
- trecho parcial ("integ" encontra "integração"), para a modal que filtra enquanto digita;
- chave de tarefa vinculada ("WAI-8295").
"""

from datetime import datetime
from typing import Any

import asyncpg

Executor = asyncpg.Connection | asyncpg.Pool

NOTE_COLUMNS = """
    n.id, n.title, n.body, n.color, n.tags, n.repos, n.pinned, n.archived, n.remind_at,
    n.reminded_at,
    n.created_at, n.updated_at,
    (n.remind_at IS NOT NULL AND n.reminded_at IS NULL AND n.remind_at <= now()
     AND NOT n.archived) AS reminder_due
"""

UPDATABLE = ("title", "body", "color", "tags", "repos", "pinned", "archived", "remind_at")


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def create(conn: asyncpg.Connection, data: dict[str, Any]) -> int:
    return await conn.fetchval(
        """
        INSERT INTO note (title, body, color, tags, pinned, remind_at, repos)
        VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id
        """,
        data["title"],
        data["body"],
        data["color"],
        data["tags"],
        data["pinned"],
        data["remind_at"],
        data.get("repos", []),
    )


async def update(conn: asyncpg.Connection, note_id: int, changes: dict[str, Any]) -> bool:
    fields = {k: v for k, v in changes.items() if k in UPDATABLE}
    if "remind_at" in fields:
        # Novo horário (ou horário removido) rearma a notificação.
        fields["reminded_at"] = None
    if not fields:
        return await conn.fetchval("SELECT EXISTS (SELECT 1 FROM note WHERE id = $1)", note_id)
    assignments = ", ".join(f"{name} = ${i}" for i, name in enumerate(fields, start=2))
    status = await conn.execute(
        f"UPDATE note SET {assignments}, updated_at = now() WHERE id = $1",
        note_id,
        *fields.values(),
    )
    return status.endswith(" 1")


async def replace_issue_keys(conn: asyncpg.Connection, note_id: int, keys: list[str]) -> None:
    await conn.execute(
        "DELETE FROM note_issue_link WHERE note_id = $1 AND NOT (issue_key = ANY($2::text[]))",
        note_id,
        keys,
    )
    await conn.executemany(
        "INSERT INTO note_issue_link (note_id, issue_key) VALUES ($1, $2) ON CONFLICT DO NOTHING",
        [(note_id, key) for key in keys],
    )


async def delete(conn: Executor, note_id: int) -> bool:
    status = await conn.execute("DELETE FROM note WHERE id = $1", note_id)
    return status.endswith(" 1")


async def get(conn: Executor, note_id: int) -> dict[str, Any] | None:
    row = await conn.fetchrow(f"SELECT {NOTE_COLUMNS} FROM note n WHERE n.id = $1", note_id)
    return dict(row) if row else None


async def search(
    conn: Executor,
    *,
    q: str | None = None,
    tags: list[str] | None = None,
    issue_key: str | None = None,
    pinned: bool | None = None,
    archived: bool | None = False,
    due: str = "any",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    where: list[str] = []
    args: list[Any] = []

    def arg(value: Any) -> str:
        args.append(value)
        return f"${len(args)}"

    rank_sql = "NULL::real"
    if q and q.strip():
        term = q.strip()
        tsq = f"websearch_to_tsquery('portuguese', f_unaccent({arg(term)}))"
        like = arg(f"%{escape_like(term.lower())}%")
        key = arg(term.upper())
        where.append(
            f"""(
                n.search @@ {tsq}
                OR f_unaccent(lower(n.title || ' ' || n.body)) LIKE f_unaccent({like})
                OR f_unaccent(f_tags_text(n.tags)) LIKE f_unaccent({like})
                OR lower(f_tags_text(n.repos)) LIKE {like}
                OR EXISTS (
                    SELECT 1 FROM note_issue_link l WHERE l.note_id = n.id AND l.issue_key = {key}
                )
            )"""
        )
        # Casar no título vale mais que casar só no corpo.
        title_bonus = (
            f"CASE WHEN f_unaccent(lower(n.title)) LIKE f_unaccent({like}) THEN 0.5 ELSE 0 END"
        )
        rank_sql = f"ts_rank(n.search, {tsq}) + {title_bonus}"
    if tags:
        where.append(f"n.tags @> {arg(tags)}::text[]")
    if issue_key:
        key_param = arg(issue_key)
        where.append(
            "EXISTS (SELECT 1 FROM note_issue_link l "
            f"WHERE l.note_id = n.id AND l.issue_key = {key_param})"
        )
    if pinned is not None:
        where.append(f"n.pinned = {arg(pinned)}")
    if archived is not None:
        where.append(f"n.archived = {arg(archived)}")
    if due == "upcoming":
        where.append("n.remind_at > now()")
    elif due == "overdue":
        where.append("n.remind_at <= now() AND n.reminded_at IS NULL")
    elif due == "none":
        where.append("n.remind_at IS NULL")

    where_sql = " AND ".join(where) or "true"
    total = await conn.fetchval(f"SELECT count(*) FROM note n WHERE {where_sql}", *args)
    rows = await conn.fetch(
        f"""
        SELECT {NOTE_COLUMNS}, {rank_sql} AS rank
        FROM note n
        WHERE {where_sql}
        ORDER BY n.pinned DESC, rank DESC NULLS LAST, n.updated_at DESC, n.id DESC
        LIMIT {arg(limit)} OFFSET {arg(offset)}
        """,
        *args,
    )
    return [dict(r) for r in rows], total


async def active_counts(conn: Executor, issue_keys: list[str]) -> dict[str, int]:
    """Lembretes não arquivados por tarefa — o mesmo número do painel da tarefa."""
    rows = await conn.fetch(
        """
        SELECT l.issue_key, count(*) AS total
        FROM note_issue_link l
        JOIN note n ON n.id = l.note_id
        WHERE l.issue_key = ANY($1::text[]) AND NOT n.archived
        GROUP BY l.issue_key
        """,
        issue_keys,
    )
    return {r["issue_key"]: r["total"] for r in rows}


async def linked_issues(conn: Executor, note_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    rows = await conn.fetch(
        """
        SELECT l.note_id, l.issue_key AS key, i.summary, i.status, i.status_category,
               (i.key IS NOT NULL) AS in_mirror
        FROM note_issue_link l
        LEFT JOIN jira_issue i ON i.key = l.issue_key
        WHERE l.note_id = ANY($1::bigint[])
        ORDER BY l.created_at, l.issue_key
        """,
        note_ids,
    )
    out: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        data = dict(row)
        out.setdefault(data.pop("note_id"), []).append(data)
    return out


async def tag_counts(conn: Executor) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT tag, count(*)::int AS count
        FROM note, unnest(tags) AS tag
        WHERE NOT archived
        GROUP BY tag ORDER BY count DESC, tag
        """
    )
    return [dict(r) for r in rows]


async def due_reminders(conn: Executor) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        f"""
        SELECT {NOTE_COLUMNS} FROM note n
        WHERE n.remind_at <= now() AND n.reminded_at IS NULL AND NOT n.archived
        ORDER BY n.remind_at
        """
    )
    return [dict(r) for r in rows]


async def acknowledge(conn: Executor, note_id: int) -> bool:
    status = await conn.execute(
        "UPDATE note SET reminded_at = now(), updated_at = now() WHERE id = $1", note_id
    )
    return status.endswith(" 1")


async def snooze(conn: Executor, note_id: int, until: datetime) -> bool:
    status = await conn.execute(
        "UPDATE note SET remind_at = $2, reminded_at = NULL, updated_at = now() WHERE id = $1",
        note_id,
        until,
    )
    return status.endswith(" 1")


async def relevant(
    conn: Executor, *, now: datetime, until: datetime, issue_keys: list[str], limit: int = 8
) -> list[dict[str, Any]]:
    """Lembretes que a Home mostra: vencidos ainda não vistos, os das próximas horas,
    os fixados e os ligados a uma tarefa da sprint ativa. Vencido primeiro.

    "Vencido" e "próximas horas" contam a partir do mesmo `now` que deu o `until`. Com o
    `now()` do banco numa ponta e o relógio da Home na outra, um lembrete futuro para a
    Home virava "vencido" assim que o relógio real passava dele."""
    rows = await conn.fetch(
        f"""
        SELECT {NOTE_COLUMNS}, NULL::real AS rank,
               (n.remind_at IS NOT NULL AND n.reminded_at IS NULL AND n.remind_at <= $1)
                   AS overdue
        FROM note n
        WHERE NOT n.archived AND (
            (n.remind_at IS NOT NULL AND n.reminded_at IS NULL AND n.remind_at <= $1)
            OR (n.remind_at > $1 AND n.remind_at <= $2)
            OR n.pinned
            OR EXISTS (SELECT 1 FROM note_issue_link l
                       WHERE l.note_id = n.id AND l.issue_key = ANY($3::text[]))
        )
        ORDER BY overdue DESC, n.pinned DESC, n.remind_at NULLS LAST, n.updated_at DESC
        LIMIT $4
        """,
        now,
        until,
        issue_keys,
        limit,
    )
    return [dict(r) for r in rows]
