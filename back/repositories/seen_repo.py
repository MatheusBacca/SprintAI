"""Fotos do que o dev já viu de cada card (`issue_seen`)."""

from collections.abc import Iterable
from typing import Any

import asyncpg

Executor = asyncpg.Connection | asyncpg.Pool


async def snapshots(conn: Executor, keys: Iterable[str]) -> dict[str, dict[str, Any]]:
    rows = await conn.fetch(
        "SELECT issue_key, snapshot FROM issue_seen WHERE issue_key = ANY($1::text[])",
        list(keys),
    )
    return {r["issue_key"]: r["snapshot"] for r in rows}


async def insert_missing(conn: Executor, snapshots_by_key: dict[str, dict[str, Any]]) -> None:
    """Primeira foto de cada card. Quem já tem foto não é tocado."""
    if not snapshots_by_key:
        return
    await conn.executemany(
        "INSERT INTO issue_seen (issue_key, snapshot) VALUES ($1, $2) "
        "ON CONFLICT (issue_key) DO NOTHING",
        list(snapshots_by_key.items()),
    )


async def upsert(conn: Executor, issue_key: str, snapshot: dict[str, Any]) -> None:
    """Refaz a foto somando à anterior: um campo que a tela não mandou continua valendo."""
    await conn.execute(
        """
        INSERT INTO issue_seen (issue_key, snapshot, seen_at) VALUES ($1, $2, now())
        ON CONFLICT (issue_key) DO UPDATE
            SET snapshot = issue_seen.snapshot || EXCLUDED.snapshot, seen_at = now()
        """,
        issue_key,
        snapshot,
    )


async def merge_existing(conn: Executor, issue_key: str, fields: dict[str, Any]) -> None:
    """Soma campos à foto que já existe, sem criar uma: card que nunca foi desenhado
    ganha a foto inteira na primeira carga do canvas."""
    await conn.execute(
        "UPDATE issue_seen SET snapshot = snapshot || $2::jsonb WHERE issue_key = $1",
        issue_key,
        fields,
    )
