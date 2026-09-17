"""Busca global sobre `search_document` (mantido por triggers, migration 0006).

Um documento casa por full-text em português sem acento, por trecho parcial (trigram) ou
pela chave de tarefa. Chave exata e termo no título pesam mais; os resultados vêm já
limitados por tipo (janela por `entity_type`) para a tela agrupada.
"""

import re
from datetime import datetime
from typing import Any

import asyncpg

from repositories.notes_repo import escape_like

Executor = asyncpg.Connection | asyncpg.Pool

_KEY = re.compile(r"^[A-Z][A-Z0-9]{1,9}-\d{1,7}$")


async def search(
    conn: Executor,
    *,
    q: str,
    types: list[str],
    since: datetime | None,
    limit: int,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    term = q.strip()
    args: list[Any] = [term, f"%{escape_like(term.lower())}%", types]
    key_match = "false"
    if _KEY.match(term.upper()):
        # Só vira parâmetro quando usado: o asyncpg não infere o tipo de parâmetro ausente.
        args.append(term.upper())
        key_match = f"d.issue_keys @> ARRAY[${len(args)}]::text[]"
    since_sql = ""
    if since is not None:
        args.append(since)
        since_sql = f"AND d.occurred_at >= ${len(args)}"
    args += [offset, offset + limit]

    rows = await conn.fetch(
        f"""
        WITH q AS (SELECT websearch_to_tsquery('portuguese', f_unaccent($1)) AS tsq),
        matches AS (
            SELECT d.*,
                   ts_rank_cd(d.search, q.tsq)
                   + CASE WHEN {key_match} THEN 3 ELSE 0 END
                   + CASE WHEN f_unaccent(lower(d.title)) LIKE f_unaccent($2) THEN 1 ELSE 0 END
                   AS rank
            FROM search_document d, q
            WHERE d.entity_type = ANY($3::text[])
              {since_sql}
              AND (d.search @@ q.tsq
                   OR f_unaccent(lower(d.title || ' ' || d.keywords || ' ' || d.content))
                      LIKE f_unaccent($2)
                   OR {key_match})
        ),
        ranked AS (
            SELECT m.*,
                   row_number() OVER (PARTITION BY entity_type
                                      ORDER BY rank DESC, occurred_at DESC NULLS LAST,
                                               entity_id) AS position,
                   count(*) OVER (PARTITION BY entity_type) AS type_total
            FROM matches m
        )
        SELECT r.entity_type, r.entity_id, r.issue_key, r.issue_keys, r.title, r.content, r.meta,
               r.occurred_at, r.rank, r.type_total,
               i.summary AS issue_summary, (i.key IS NOT NULL) AS issue_in_mirror
        FROM ranked r
        LEFT JOIN jira_issue i ON i.key = r.issue_key
        WHERE r.position > ${len(args) - 1} AND r.position <= ${len(args)}
        ORDER BY r.entity_type, r.position
        """,
        *args,
    )
    totals: dict[str, int] = {}
    items = []
    for row in rows:
        data = dict(row)
        totals[data["entity_type"]] = data.pop("type_total")
        items.append(data)
    # Tipo com resultados só além do offset pedido ainda precisa do total.
    if offset and len(types) == 1 and not items:
        totals[types[0]] = await count(conn, q=q, types=types, since=since)
    return items, totals


async def count(conn: Executor, *, q: str, types: list[str], since: datetime | None) -> int:
    _, totals = await search(conn, q=q, types=types, since=since, limit=1, offset=0)
    return sum(totals.values())
