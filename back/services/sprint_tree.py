"""Árvore Pai → Filhas de uma sprint — função pura, sem banco.

Regras:
- Pai de uma tarefa: campo `parent` (Épico → Tarefa → Subtarefa); sem `parent`, o
  primeiro link de hierarquia para um Épico/Enhancements (Relates, Divisão do ticket,
  implements).
- Grupo: cada ancestral de topo que é Épico/Enhancements vira a raiz de um grupo; tarefas
  sem ancestral desse tipo vão para o grupo "Sem pai" (subtarefas continuam aninhadas).
- Bloqueio: link "Blocks" entre tarefas do grafo vira seta; tarefa com bloqueador ainda
  não concluído conta como bloqueada.
- Origem: link "is caused by" entre tarefas do grafo vira seta "origina".
- Ordem das ondas (`predecessors`): bloqueadores e origens do grafo, **concluídos ou não**.
  O bloqueio se desfaz quando o bloqueador fecha; a ordem em que as coisas foram feitas,
  não — senão a sprint se desmancha numa linha só conforme as tarefas vão sendo concluídas.
"""

from dataclasses import dataclass, field
from typing import Any

from services.hierarchy import (
    BLOCK_LINK_TYPE,
    CAUSE_LINK_TYPE,
    PARENT_ISSUE_TYPES,
    is_hierarchy_link,
)

# Tipo de link → (tipo da aresta, rótulo). Origem da aresta é quem vem antes.
DEPENDENCY_LINKS = {BLOCK_LINK_TYPE: ("blocks", "bloqueia"), CAUSE_LINK_TYPE: ("causes", "origina")}

NO_PARENT_GROUP = "__sem_pai__"


@dataclass
class TreeNode:
    key: str
    summary: str
    issue_type: str
    status: str
    status_category: str
    story_points: float | None
    assignee_name: str | None
    is_mine: bool
    in_sprint: bool
    is_parent_type: bool
    parent_key: str | None = None
    parent_via: str | None = None  # "parent" | "link"
    group: str = NO_PARENT_GROUP
    depth: int = 0
    blocked_by: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    predecessors: list[str] = field(default_factory=list)
    children: list[str] = field(default_factory=list)
    # nó montado só com o snapshot do link (pai fora do espelho)
    partial: bool = False

    @property
    def blocked(self) -> bool:
        return bool(self.blocked_by)


@dataclass
class TreeEdge:
    source: str
    target: str
    kind: str  # "parent" | "link" | "blocks" | "causes"
    label: str | None = None


@dataclass
class TreeGroup:
    key: str
    root_key: str | None
    issue_keys: list[str]


@dataclass
class SprintTree:
    nodes: dict[str, TreeNode]
    edges: list[TreeEdge]
    groups: list[TreeGroup]
    counters: dict[str, int]


def _node(row: dict[str, Any], *, my_account_id: str | None, in_sprint: bool) -> TreeNode:
    points = row.get("story_points")
    return TreeNode(
        key=row["key"],
        summary=row.get("summary") or "",
        issue_type=row.get("issue_type") or "?",
        status=row.get("status") or "?",
        status_category=row.get("status_category") or "undefined",
        story_points=float(points) if points is not None else None,
        assignee_name=row.get("assignee_name"),
        is_mine=bool(my_account_id) and row.get("assignee_account_id") == my_account_id,
        in_sprint=in_sprint,
        is_parent_type=(row.get("issue_type") in PARENT_ISSUE_TYPES),
    )


def _partial_node(link: dict[str, Any]) -> TreeNode:
    return TreeNode(
        key=link["target_key"],
        summary=link.get("target_summary") or "",
        issue_type=link.get("target_type") or "?",
        status=link.get("target_status") or "?",
        status_category="undefined",
        story_points=None,
        assignee_name=None,
        is_mine=False,
        in_sprint=False,
        is_parent_type=link.get("target_type") in PARENT_ISSUE_TYPES,
        partial=True,
    )


def build_tree(
    *,
    sprint_issues: list[dict[str, Any]],
    related_issues: list[dict[str, Any]],
    links: list[dict[str, Any]],
    my_account_id: str | None,
    only_mine: bool = False,
) -> SprintTree:
    """`related_issues`: ancestrais e alvos de link de hierarquia já presentes no espelho.
    `links`: links cuja origem é qualquer issue do grafo."""
    if only_mine:
        sprint_issues = [
            r
            for r in sprint_issues
            if my_account_id and r.get("assignee_account_id") == my_account_id
        ]

    nodes: dict[str, TreeNode] = {
        r["key"]: _node(r, my_account_id=my_account_id, in_sprint=True) for r in sprint_issues
    }
    related = {r["key"]: r for r in related_issues}
    rows = {**related, **{r["key"]: r for r in sprint_issues}}
    links_by_source: dict[str, list[dict[str, Any]]] = {}
    for link in links:
        links_by_source.setdefault(link["source_key"], []).append(link)

    # Sobe a partir das tarefas da sprint, criando os pais que faltam no grafo.
    pending = list(nodes)
    while pending:
        key = pending.pop()
        node = nodes[key]
        parent_key, via, partial_link = None, None, None
        row = rows.get(key, {})
        if row.get("parent_key"):
            parent_key, via = row["parent_key"], "parent"
        else:
            for link in links_by_source.get(key, []):
                if is_hierarchy_link(link["link_type"], link.get("target_type")):
                    parent_key, via, partial_link = link["target_key"], "link", link
                    break
        if not parent_key or parent_key == key:
            continue
        node.parent_key, node.parent_via = parent_key, via
        if parent_key not in nodes:
            if parent_key in related:
                nodes[parent_key] = _node(
                    related[parent_key], my_account_id=my_account_id, in_sprint=False
                )
            elif partial_link:
                nodes[parent_key] = _partial_node(partial_link)
            else:
                nodes[parent_key] = TreeNode(
                    key=parent_key,
                    summary="",
                    issue_type="?",
                    status="?",
                    status_category="undefined",
                    story_points=None,
                    assignee_name=None,
                    is_mine=False,
                    in_sprint=False,
                    is_parent_type=False,
                    partial=True,
                )
            pending.append(parent_key)

    _break_cycles(nodes)
    for node in nodes.values():
        if node.parent_key:
            nodes[node.parent_key].children.append(node.key)
    for node in nodes.values():
        node.children.sort()

    edges: list[TreeEdge] = [
        TreeEdge(
            source=n.parent_key, target=n.key, kind="parent" if n.parent_via == "parent" else "link"
        )
        for n in nodes.values()
        if n.parent_key
    ]
    edges += _dependency_edges(nodes, links_by_source, related)

    groups = _groups(nodes)
    sprint_nodes = [n for n in nodes.values() if n.in_sprint]
    counters = {
        "tasks": len(sprint_nodes),
        "parents": sum(1 for g in groups if g.root_key),
        "blocked": sum(1 for n in sprint_nodes if n.blocked),
        "mine": sum(1 for n in sprint_nodes if n.is_mine),
        "story_points": int(sum(n.story_points or 0 for n in sprint_nodes)),
        "done": sum(1 for n in sprint_nodes if n.status_category == "done"),
    }
    return SprintTree(nodes=nodes, edges=edges, groups=groups, counters=counters)


def _break_cycles(nodes: dict[str, TreeNode]) -> None:
    """Dados do Jira podem ter ciclo via links (A relates B, B relates A)."""
    for node in nodes.values():
        seen = {node.key}
        current = node
        while current.parent_key:
            if current.parent_key in seen:
                current.parent_key, current.parent_via = None, None
                break
            seen.add(current.parent_key)
            current = nodes[current.parent_key]


def _top_ancestor(nodes: dict[str, TreeNode], key: str) -> tuple[str, int]:
    depth = 0
    current = nodes[key]
    while current.parent_key:
        current = nodes[current.parent_key]
        depth += 1
    return current.key, depth


def _groups(nodes: dict[str, TreeNode]) -> list[TreeGroup]:
    by_group: dict[str, list[str]] = {}
    for key in nodes:
        top, depth = _top_ancestor(nodes, key)
        nodes[key].depth = depth
        top_node = nodes[top]
        group = top if (top_node.is_parent_type or not top_node.in_sprint) else NO_PARENT_GROUP
        nodes[key].group = group
        by_group.setdefault(group, []).append(key)

    def order(item: tuple[str, list[str]]) -> tuple[int, int, str]:
        group, keys = item
        in_sprint = sum(1 for k in keys if nodes[k].in_sprint)
        return (1 if group == NO_PARENT_GROUP else 0, -in_sprint, group)

    return [
        TreeGroup(
            key=group,
            root_key=None if group == NO_PARENT_GROUP else group,
            issue_keys=sorted(keys, key=lambda k: (nodes[k].depth, k)),
        )
        for group, keys in sorted(by_group.items(), key=order)
    ]


def _dependency_edges(
    nodes: dict[str, TreeNode],
    links_by_source: dict[str, list[dict[str, Any]]],
    related: dict[str, dict[str, Any]],
) -> list[TreeEdge]:
    edges: dict[tuple[str, str, str], TreeEdge] = {}
    for source, source_links in links_by_source.items():
        if source not in nodes:
            continue
        for link in source_links:
            if link["link_type"] not in DEPENDENCY_LINKS:
                continue
            kind, label = DEPENDENCY_LINKS[link["link_type"]]
            target = link["target_key"]
            before, after = (source, target) if link["direction"] == "outward" else (target, source)
            if kind == "blocks":
                if after in nodes and before not in nodes[after].blocked_by:
                    if not _is_done(before, nodes, related, link):
                        nodes[after].blocked_by.append(before)
                if before in nodes and after not in nodes[before].blocks:
                    nodes[before].blocks.append(after)
            if before in nodes and after in nodes and before != after:
                if before not in nodes[after].predecessors:
                    nodes[after].predecessors.append(before)
                edges[(kind, before, after)] = TreeEdge(
                    source=before, target=after, kind=kind, label=label
                )
    # A consulta dos links não tem ordem: sem isto a resposta mudaria a cada chamada.
    for node in nodes.values():
        node.predecessors.sort()
    return list(edges.values())


def _is_done(
    key: str,
    nodes: dict[str, TreeNode],
    related: dict[str, dict[str, Any]],
    link: dict[str, Any],
) -> bool:
    if key in nodes and nodes[key].status_category != "undefined":
        return nodes[key].status_category == "done"
    if key in related:
        return related[key].get("status_category") == "done"
    # Bloqueador fora do espelho: só temos o nome do status no snapshot do link.
    status = (link.get("target_status") or "").lower()
    return status in {"concluído", "concluida", "concluída", "done", "fechado", "resolvido"}
