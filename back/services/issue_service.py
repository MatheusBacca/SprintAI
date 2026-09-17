"""Painel lateral da tarefa: tudo do espelho numa resposta + histórico ao vivo do Jira."""

from datetime import datetime
from typing import Any

import asyncpg

from integrations import factory
from repositories import issue_repo
from schemas.issue_schemas import (
    ChangeItemOut,
    ChangelogEntryOut,
    ChangelogOut,
    CommentOut,
    DependencyGroupOut,
    DependencyOut,
    IssueDetailOut,
    IssuePickOut,
    IssueRefOut,
    SprintRefOut,
)
from security.credential_store import CredentialStore
from services import pr_status_service
from services.blocking import blockers_without_pr
from services.hierarchy import BLOCK_LINK_TYPE, is_hierarchy_link
from services.progress.service import load_stages, stage_ref
from services.sprint_service import jira_identity

CHANGELOG_LIMIT = 200
# Proteção contra issue com histórico gigante (o Jira devolve do mais antigo ao mais novo).
CHANGELOG_SCAN_LIMIT = 2000
MAX_CHANGE_TEXT = 280
# Campos de texto longo: o histórico só diz que mudou.
LONG_TEXT_FIELDS = {"description", "environment", "comment"}


class IssueNotFound(Exception):
    pass


def _browse(site_url: str | None, key: str) -> str | None:
    return f"{site_url.rstrip('/')}/browse/{key}" if site_url else None


def _group_of(link: dict[str, Any]) -> tuple[str, str]:
    if link["link_type"] == BLOCK_LINK_TYPE:
        if link["direction"] == "outward":
            return "blocks", "Bloqueia"
        return "blocked_by", "É bloqueada por"
    if is_hierarchy_link(link["link_type"], link.get("issue_type")):
        return "hierarchy", link["label"]
    return "other", link["label"]


async def pick(
    pool: asyncpg.Pool, store: CredentialStore, *, q: str, limit: int, mine: bool = False
) -> list[IssuePickOut]:
    account_id, _ = jira_identity(store)
    rows = await issue_repo.pick(
        pool, terms=q.split(), account_id=account_id, limit=limit, mine=mine
    )
    return [IssuePickOut(**r) for r in rows]


async def get_detail(pool: asyncpg.Pool, store: CredentialStore, key: str) -> IssueDetailOut:
    row = await issue_repo.issue(pool, key)
    if row is None:
        raise IssueNotFound(key)
    account_id, site_url = jira_identity(store)

    links = await issue_repo.links(pool, key)
    children = await issue_repo.children(pool, key)
    parent_rows = (
        await issue_repo.related_issues(pool, [row["parent_key"]]) if row["parent_key"] else []
    )

    related_keys = {link["target_key"] for link in links} | {c["key"] for c in children}
    related_keys |= {p["key"] for p in parent_rows}
    summaries = await pr_status_service.summaries(pool, [key, *sorted(related_keys)])

    def ref(data: dict[str, Any], *, in_mirror: bool = True) -> dict[str, Any]:
        k = data["key"] if "key" in data else data["target_key"]
        return {
            "key": k,
            "summary": data.get("summary"),
            "status": data.get("status"),
            "status_category": data.get("status_category"),
            "issue_type": data.get("issue_type"),
            "assignee_name": data.get("assignee_name"),
            "in_mirror": in_mirror,
            "url": _browse(site_url, k),
            "pr": pr_status_service.to_badge(summaries[k])
            if in_mirror and k in summaries
            else None,
        }

    groups: dict[tuple[str, str], list[DependencyOut]] = {}
    for link in links:
        dep = DependencyOut(
            **ref(link, in_mirror=link["in_mirror"]),
            link_type=link["link_type"],
            direction=link["direction"],
            label=link["label"],
        )
        groups.setdefault(_group_of(link), []).append(dep)

    order = {"blocked_by": 0, "blocks": 1, "hierarchy": 2, "other": 3}
    dependency_groups = [
        DependencyGroupOut(kind=kind, label=label, items=items)
        for (kind, label), items in sorted(groups.items(), key=lambda g: (order[g[0][0]], g[0][1]))
    ]

    if row["parent_key"]:
        parent = (
            IssueRefOut(**ref(parent_rows[0]))
            if parent_rows
            else IssueRefOut(
                key=row["parent_key"], in_mirror=False, url=_browse(site_url, row["parent_key"])
            )
        )
    else:
        parent = None

    blocked_by = groups.get(("blocked_by", "É bloqueada por"), [])
    stages = await load_stages(pool)
    points = row["story_points"]
    return IssueDetailOut(
        key=row["key"],
        url=_browse(site_url, row["key"]),
        summary=row["summary"],
        issue_type=row["issue_type"],
        is_subtask=row["is_subtask"],
        status=row["status"],
        status_category=row["status_category"],
        priority=row["priority"],
        assignee_name=row["assignee_name"],
        is_mine=bool(account_id) and row["assignee_account_id"] == account_id,
        reporter_name=row["reporter_name"],
        story_points=float(points) if points is not None else None,
        due_date=row["due_date"],
        labels=row["labels"],
        components=row["components"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        resolved_at=row["resolved_at"],
        synced_at=row["synced_at"],
        description_adf=row["description_adf"],
        description_text=row["description_text"],
        parent=parent,
        children=[IssueRefOut(**ref(c)) for c in children],
        sprints=[SprintRefOut(**s) for s in await issue_repo.sprints_of(pool, key)],
        dependencies=dependency_groups,
        blocks=groups.get(("blocks", "Bloqueia"), []),
        blocked_by=blocked_by,
        blockers_without_pr=blockers_without_pr(
            [b.key for b in blocked_by if b.status_category != "done"], summaries
        ),
        stage=stage_ref(stages.stage_of(row["status"])),
        comments=[CommentOut(**c) for c in await issue_repo.comments(pool, key)],
        pull_requests=pr_status_service.to_detail(summaries[key]),
    )


def _short(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value if len(value) <= MAX_CHANGE_TEXT else value[: MAX_CHANGE_TEXT - 1] + "…"


def changelog_entry(raw: dict[str, Any]) -> ChangelogEntryOut:
    items = []
    for item in raw.get("items") or []:
        field = item.get("field") or item.get("fieldId") or "?"
        if field.lower() in LONG_TEXT_FIELDS:
            items.append(ChangeItemOut(field=field, from_value=None, to_value="(texto alterado)"))
            continue
        items.append(
            ChangeItemOut(
                field=field,
                from_value=_short(item.get("fromString")),
                to_value=_short(item.get("toString")),
            )
        )
    return ChangelogEntryOut(
        id=str(raw["id"]),
        author_name=(raw.get("author") or {}).get("displayName"),
        created_at=datetime.fromisoformat(raw["created"].replace("Z", "+00:00")),
        items=items,
    )


async def get_changelog(store: CredentialStore, key: str) -> ChangelogOut:
    raws: list[dict[str, Any]] = []
    async with await factory.jira_client(store) as jira:
        async for raw in jira.iter_changelog(key):
            raws.append(raw)
            if len(raws) >= CHANGELOG_SCAN_LIMIT:
                break
    entries = sorted((changelog_entry(r) for r in raws), key=lambda e: e.created_at, reverse=True)
    return ChangelogOut(
        issue_key=key,
        entries=entries[:CHANGELOG_LIMIT],
        truncated=len(entries) > CHANGELOG_LIMIT,
    )
