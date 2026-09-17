from typing import Any

import asyncpg

from realtime import bus
from repositories import contexts_repo
from schemas.context_schemas import (
    ContextCountsOut,
    ContextCreate,
    ContextListOut,
    ContextOut,
    ContextUpdate,
    IssueContextsOut,
    RelationOut,
    ResolveIn,
)
from schemas.note_schemas import LinkedIssueOut
from security.credential_store import CredentialStore
from services.sprint_service import jira_identity


class ContextNotFound(Exception):
    pass


class ContextConflict(ValueError):
    """Operação que o estado atual do contexto não permite (vira 422 com a mensagem)."""


async def _hydrate(
    pool: asyncpg.Pool, store: CredentialStore, rows: list[dict[str, Any]]
) -> list[ContextOut]:
    if not rows:
        return []
    relations = await contexts_repo.relations(pool, [r["id"] for r in rows])
    keys = {r["issue_key"] for r in rows}
    keys |= {r["resolved_in_issue_key"] for r in rows if r["resolved_in_issue_key"]}
    keys |= {rel["key"] for rels in relations.values() for rel in rels}
    info = await contexts_repo.issue_info(pool, sorted(keys))

    _, site_url = jira_identity(store)
    browse = f"{site_url.rstrip('/')}/browse/" if site_url else None

    def linked(key: str) -> dict[str, Any]:
        data = info.get(key)
        return {
            "key": key,
            "summary": data["summary"] if data else None,
            "status": data["status"] if data else None,
            "status_category": data["status_category"] if data else None,
            "in_mirror": data is not None,
            "url": f"{browse}{key}" if browse else None,
        }

    out = []
    for row in rows:
        row = dict(row)
        resolved_in = row.pop("resolved_in_issue_key")
        out.append(
            ContextOut(
                **row,
                issue=LinkedIssueOut(**linked(row.pop("issue_key"))),
                resolved_in=LinkedIssueOut(**linked(resolved_in)) if resolved_in else None,
                relations=[
                    RelationOut(**linked(rel["key"]), relation=rel["relation"])
                    for rel in relations.get(row["id"], [])
                ],
            )
        )
    return out


async def get(pool: asyncpg.Pool, store: CredentialStore, context_id: int) -> ContextOut:
    row = await contexts_repo.get(pool, context_id)
    if row is None:
        raise ContextNotFound(context_id)
    return (await _hydrate(pool, store, [row]))[0]


async def create(pool: asyncpg.Pool, store: CredentialStore, payload: ContextCreate) -> ContextOut:
    async with pool.acquire() as conn, conn.transaction():
        context_id = await contexts_repo.create(conn, payload.model_dump())
        await contexts_repo.replace_relations(
            conn, context_id, [(r.issue_key, r.relation) for r in payload.relations]
        )
    bus.publish(bus.CONTEXT_CHANGED, {"id": context_id, "action": "created"})
    return await get(pool, store, context_id)


async def update(
    pool: asyncpg.Pool, store: CredentialStore, context_id: int, payload: ContextUpdate
) -> ContextOut:
    changes = payload.model_dump(exclude_unset=True, exclude={"relations"})
    if "title" in changes and changes["title"] is not None:
        changes["title"] = changes["title"].strip()
    changes = {k: v for k, v in changes.items() if v is not None}

    async with pool.acquire() as conn, conn.transaction():
        current = await contexts_repo.get(conn, context_id)
        if current is None:
            raise ContextNotFound(context_id)
        if changes.get("kind", current["kind"]) != "open_point" and current["status"] == "resolved":
            raise ContextConflict("Reabra o ponto resolvido antes de mudar o tipo.")
        try:
            await contexts_repo.update(conn, context_id, changes)
        except asyncpg.CheckViolationError as exc:
            raise ContextConflict("Escreva um título ou um texto para o contexto.") from exc
        if payload.relations is not None:
            issue_key = changes.get("issue_key", current["issue_key"])
            await contexts_repo.replace_relations(
                conn,
                context_id,
                [(r.issue_key, r.relation) for r in payload.relations if r.issue_key != issue_key],
            )
    bus.publish(bus.CONTEXT_CHANGED, {"id": context_id, "action": "updated"})
    return await get(pool, store, context_id)


async def delete(pool: asyncpg.Pool, context_id: int) -> None:
    if not await contexts_repo.delete(pool, context_id):
        raise ContextNotFound(context_id)
    bus.publish(bus.CONTEXT_CHANGED, {"id": context_id, "action": "deleted"})


async def resolve(
    pool: asyncpg.Pool, store: CredentialStore, context_id: int, payload: ResolveIn
) -> ContextOut:
    async with pool.acquire() as conn, conn.transaction():
        current = await contexts_repo.get(conn, context_id)
        if current is None:
            raise ContextNotFound(context_id)
        if current["kind"] != "open_point":
            raise ContextConflict("Só pontos em aberto são resolvidos.")
        await contexts_repo.resolve(conn, context_id, payload.issue_key, payload.resolution.strip())
    bus.publish(bus.CONTEXT_CHANGED, {"id": context_id, "action": "resolved"})
    return await get(pool, store, context_id)


async def reopen(pool: asyncpg.Pool, store: CredentialStore, context_id: int) -> ContextOut:
    async with pool.acquire() as conn, conn.transaction():
        if not await contexts_repo.reopen(conn, context_id):
            raise ContextNotFound(context_id)
    bus.publish(bus.CONTEXT_CHANGED, {"id": context_id, "action": "reopened"})
    return await get(pool, store, context_id)


async def search(pool: asyncpg.Pool, store: CredentialStore, **filters: Any) -> ContextListOut:
    rows, total = await contexts_repo.search(pool, **filters)
    return ContextListOut(items=await _hydrate(pool, store, rows), total=total)


async def for_issue(pool: asyncpg.Pool, store: CredentialStore, issue_key: str) -> IssueContextsOut:
    groups = await contexts_repo.for_issue(pool, issue_key)
    return IssueContextsOut(
        own=await _hydrate(pool, store, groups["own"]),
        linked=await _hydrate(pool, store, groups["linked"]),
        nearby_open=await _hydrate(pool, store, groups["nearby_open"]),
    )


async def counts(pool: asyncpg.Pool) -> ContextCountsOut:
    return ContextCountsOut(**await contexts_repo.counts(pool))
