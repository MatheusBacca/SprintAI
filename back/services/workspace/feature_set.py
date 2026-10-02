"""Conjunto da feature: as tarefas que um workspace desenha dentro da moldura (B16).

- **Raiz Épico, Enhancements ou Feature** — desce até `MAX_DEPTH` níveis. Filha é quem tem
  a raiz no `parent`, quem aponta para ela por link de hierarquia (a Tarefa fatiada que
  "Relates" o Enhancements) e, do lado da raiz, a tarefa que ela própria liga por link de
  hierarquia (é assim que a filha de outro dev aparece: só o snapshot do link, tracejada).
- **Raiz Tarefa** — ela, as subtarefas e as vizinhas por Blocks, "is caused by" e Relates
  entre tarefas. O pai entra como contexto, fora da moldura, pela subida de ancestrais.

O espelho, no escopo padrão, só guarda as tarefas do dev: filha de outro dev pelo `parent`
não aparece (o `parent` não é link, não deixa snapshot).
"""

from dataclasses import dataclass, field
from typing import Any

import asyncpg

from repositories import sprint_repo, workspace_repo
from services.hierarchy import (
    BLOCK_LINK_TYPE,
    CAUSE_LINK_TYPE,
    HIERARCHY_LINK_TYPES,
    PARENT_ISSUE_TYPES,
)

MAX_DEPTH = 3
NEIGHBOR_LINK_TYPES = frozenset({BLOCK_LINK_TYPE, CAUSE_LINK_TYPE, "Relates"})


class IssueNotInMirror(Exception):
    pass


@dataclass
class FeatureSet:
    root: dict[str, Any]
    # Linhas do espelho e as montadas a partir do snapshot de um link (`partial_keys`).
    rows: dict[str, dict[str, Any]] = field(default_factory=dict)
    partial_keys: set[str] = field(default_factory=set)
    # Links que só existem do lado da raiz: viram o link "da filha para a raiz" que a
    # árvore precisa para subir a tarefa parcial até o pai certo.
    extra_links: list[dict[str, Any]] = field(default_factory=list)

    @property
    def keys(self) -> list[str]:
        return sorted(self.rows)


def is_parent_type(row: dict[str, Any] | None) -> bool:
    return bool(row) and row.get("issue_type") in PARENT_ISSUE_TYPES


async def load(pool: asyncpg.Pool, root_key: str) -> FeatureSet:
    found = await sprint_repo.issues_by_keys(pool, [root_key])
    if not found:
        raise IssueNotInMirror(root_key)
    feature = FeatureSet(root=found[0], rows={root_key: found[0]})
    if is_parent_type(found[0]):
        await _descend(pool, feature)
    else:
        await _neighbors(pool, feature)
    return feature


async def _descend(pool: asyncpg.Pool, feature: FeatureSet) -> None:
    frontier = {feature.root["key"]}
    for _ in range(MAX_DEPTH):
        if not frontier:
            return
        parents = {k for k in frontier if is_parent_type(feature.rows.get(k))}
        new: set[str] = set()

        for row in await workspace_repo.children_of(pool, frontier):
            new |= _add(feature, row)

        if parents:
            incoming = [
                link
                for link in await workspace_repo.links_to(pool, parents)
                if link["link_type"] in HIERARCHY_LINK_TYPES
            ]
            sources = {link["source_key"] for link in incoming} - set(feature.rows)
            for row in await sprint_repo.issues_by_keys(pool, sources):
                new |= _add(feature, row)

            outgoing = [
                link
                for link in await sprint_repo.links_from(pool, parents)
                if link["link_type"] in HIERARCHY_LINK_TYPES
                and link.get("target_type") not in PARENT_ISSUE_TYPES
            ]
            targets = {link["target_key"] for link in outgoing} - set(feature.rows)
            in_mirror = {r["key"]: r for r in await sprint_repo.issues_by_keys(pool, targets)}
            for link in outgoing:
                target = link["target_key"]
                if target in feature.rows:
                    continue
                if target in in_mirror:
                    new |= _add(feature, in_mirror[target])
                else:
                    new |= _add_partial(feature, link, feature.rows[link["source_key"]])
        frontier = new


async def _neighbors(pool: asyncpg.Pool, feature: FeatureSet) -> None:
    root_key = feature.root["key"]
    for row in await workspace_repo.children_of(pool, [root_key]):
        _add(feature, row)

    outgoing = [
        link
        for link in await sprint_repo.links_from(pool, [root_key])
        if link["link_type"] in NEIGHBOR_LINK_TYPES
        and link.get("target_type") not in PARENT_ISSUE_TYPES
    ]
    incoming = [
        link
        for link in await workspace_repo.links_to(pool, [root_key])
        if link["link_type"] in NEIGHBOR_LINK_TYPES
    ]
    wanted = {link["target_key"] for link in outgoing} | {link["source_key"] for link in incoming}
    in_mirror = {r["key"]: r for r in await sprint_repo.issues_by_keys(pool, wanted)}
    for row in in_mirror.values():
        if not is_parent_type(row):
            _add(feature, row)
    for link in outgoing:
        if link["target_key"] not in feature.rows and link["target_key"] not in in_mirror:
            _add_partial(feature, link, None)


def _add(feature: FeatureSet, row: dict[str, Any]) -> set[str]:
    if row["key"] in feature.rows:
        return set()
    feature.rows[row["key"]] = row
    return {row["key"]}


def _add_partial(
    feature: FeatureSet, link: dict[str, Any], parent: dict[str, Any] | None
) -> set[str]:
    key = link["target_key"]
    if key in feature.rows:
        return set()
    feature.rows[key] = {
        "key": key,
        "summary": link.get("target_summary") or "",
        "issue_type": link.get("target_type") or "?",
        "status": link.get("target_status") or "?",
        "status_category": None,
        "story_points": None,
        "assignee_account_id": None,
        "assignee_name": None,
        "parent_key": None,
        "updated_at": None,
    }
    feature.partial_keys.add(key)
    if parent is not None:
        # O link existe só do lado do pai; a árvore sobe pelo link da filha.
        feature.extra_links.append(
            {
                "source_key": key,
                "target_key": parent["key"],
                "link_type": link["link_type"],
                "direction": "outward",
                "label": link.get("label"),
                "target_summary": parent.get("summary"),
                "target_status": parent.get("status"),
                "target_type": parent.get("issue_type"),
            }
        )
    return {key}
