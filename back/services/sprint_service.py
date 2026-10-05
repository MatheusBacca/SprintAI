import asyncpg

from repositories import notes_repo, sprint_repo
from schemas.sprint_schemas import (
    CardTintOut,
    SprintSummaryOut,
    SprintTreeOut,
    TitlePartOut,
    TreeEdgeOut,
    TreeGroupOut,
    TreeNodeOut,
)
from security.credential_store import CredentialStore
from services import card_colors, card_updates, conclude_settings, pr_status_service
from services.blocking import blockers_without_pr
from services.hierarchy import is_hierarchy_link
from services.progress.service import load_stages, stage_ref
from services.sprint_tree import SprintTree, build_tree

MAX_ANCESTOR_DEPTH = 4


class SprintNotFound(Exception):
    pass


def jira_identity(store: CredentialStore) -> tuple[str | None, str | None]:
    """(accountId do dev, URL do site) a partir da conexão salva — sem chamar o Jira."""
    data = store.get("jira") or {}
    return data.get("account_id"), data.get("site_url")


async def list_sprints(pool: asyncpg.Pool, store: CredentialStore) -> list[SprintSummaryOut]:
    account_id, _ = jira_identity(store)
    return [SprintSummaryOut(**row) for row in await sprint_repo.scope_sprints(pool, account_id)]


def _tint_out(tint: card_colors.Tint | None) -> CardTintOut | None:
    if tint is None:
        return None
    return CardTintOut(colors=list(tint.colors), source=tint.source, label=tint.label)


async def sprint_tree(
    pool: asyncpg.Pool, store: CredentialStore, sprint_id: int, *, only_mine: bool
) -> SprintTreeOut:
    sprint = await sprint_repo.sprint(pool, sprint_id)
    if sprint is None:
        raise SprintNotFound(sprint_id)
    account_id, site_url = jira_identity(store)

    sprint_issues = await sprint_repo.sprint_issues(pool, sprint_id)
    related, links = await climb_ancestors(pool, sprint_issues)

    tree = build_tree(
        sprint_issues=sprint_issues,
        related_issues=list(related.values()),
        links=links,
        my_account_id=account_id,
        only_mine=only_mine,
    )

    counts = {
        "issue_count": len(sprint_issues),
        "mine_count": sum(
            1 for r in sprint_issues if account_id and r["assignee_account_id"] == account_id
        ),
        "done_count": sum(1 for r in sprint_issues if r["status_category"] == "done"),
    }
    return SprintTreeOut(
        sprint=SprintSummaryOut(**sprint, **counts),
        only_mine=only_mine,
        counters=tree.counters,
        nodes=await render_nodes(pool, tree, site_url),
        edges=[TreeEdgeOut(**vars(e)) for e in tree.edges],
        groups=[TreeGroupOut(**vars(g)) for g in tree.groups],
    )


async def climb_ancestors(
    pool: asyncpg.Pool, issues: list[dict]
) -> tuple[dict[str, dict], list[dict]]:
    """Sobe os ancestrais (parent e links de hierarquia) que estão no espelho, até
    `MAX_ANCESTOR_DEPTH` níveis. Devolve as issues achadas e os links de todo o caminho."""
    known = {r["key"]: r for r in issues}
    related: dict[str, dict] = {}
    links: list[dict] = []
    frontier = set(known)
    for _ in range(MAX_ANCESTOR_DEPTH):
        if not frontier:
            break
        new_links = await sprint_repo.links_from(pool, frontier)
        links += new_links
        wanted = {
            r["parent_key"]
            for r in (known.get(k) or related.get(k) or {} for k in frontier)
            if r and r.get("parent_key")
        }
        wanted |= {
            link["target_key"]
            for link in new_links
            if is_hierarchy_link(link["link_type"], link.get("target_type"))
        }
        wanted -= set(known) | set(related)
        found = await sprint_repo.issues_by_keys(pool, wanted)
        related.update({r["key"]: r for r in found})
        frontier = {r["key"] for r in found}
    return related, links


async def render_nodes(
    pool: asyncpg.Pool, tree: SprintTree, site_url: str | None
) -> list[TreeNodeOut]:
    """Os nós da árvore como o canvas desenha: selo de PR (só de quem está na moldura),
    etapa, cor do card, mudanças não vistas e lembretes. Serve a Sprint e o Workspace."""
    sprint_keys = [k for k, n in tree.nodes.items() if n.in_sprint]
    summaries = await pr_status_service.summaries(pool, sprint_keys) if sprint_keys else {}
    # Bloqueador pode estar fora da sprint (e fora do espelho): ganha resumo só para
    # isto, sem virar badge de PR no card dele.
    blocker_keys = {b for n in tree.nodes.values() for b in n.blocked_by} - set(summaries)
    blocker_summaries = {
        **summaries,
        **(await pr_status_service.summaries(pool, blocker_keys) if blocker_keys else {}),
    }
    base_url = f"{site_url.rstrip('/')}/browse/" if site_url else None
    stages = await load_stages(pool)
    colors = await card_colors.load_colors(pool)
    paints = {n.key: colors.paint(n.issue_type, n.summary) for n in tree.nodes.values()}

    # Card parcial é só o resumo de um link: não tem o que comparar.
    changes = await card_updates.unseen_changes(
        pool,
        {
            n.key: card_updates.snapshot(
                status=n.status,
                story_points=n.story_points,
                assignee_name=n.assignee_name,
                pr_status=summaries[n.key].status if n.key in summaries else None,
                pr_review=summaries[n.key].review if n.key in summaries else None,
                with_pr=n.in_sprint,
            )
            for n in tree.nodes.values()
            if not n.partial
        },
    )

    note_counts = await notes_repo.active_counts(pool, list(tree.nodes))
    concludes = await conclude_settings.with_conclusion(
        pool,
        [
            conclude_settings.ConcludeTask(n.key, n.summary, n.status, n.status_category)
            for n in tree.nodes.values()
            if n.in_sprint and not n.partial
        ],
        summaries,
    )

    return [
        TreeNodeOut(
            key=n.key,
            summary=n.summary,
            issue_type=n.issue_type,
            status=n.status,
            status_category=n.status_category,
            story_points=n.story_points,
            assignee_name=n.assignee_name,
            is_mine=n.is_mine,
            in_sprint=n.in_sprint,
            is_parent_type=n.is_parent_type,
            partial=n.partial,
            parent_key=n.parent_key,
            parent_via=n.parent_via,
            group=n.group,
            depth=n.depth,
            blocked=n.blocked,
            blocked_by=n.blocked_by,
            blockers_without_pr=blockers_without_pr(n.blocked_by, blocker_summaries),
            blocks=n.blocks,
            predecessors=n.predecessors,
            children=n.children,
            co_parents=n.co_parents,
            co_children=n.co_children,
            url=f"{base_url}{n.key}" if base_url else None,
            pr=pr_status_service.to_badge(summaries[n.key]) if n.key in summaries else None,
            stage=stage_ref(stages.stage_of(n.status)),
            tint=_tint_out(paints[n.key].tint),
            title_parts=[TitlePartOut(**vars(p)) for p in paints[n.key].title],
            conclude=n.key in concludes,
            unseen_changes=changes.get(n.key, []),
            note_count=note_counts.get(n.key, 0),
        )
        for n in tree.nodes.values()
    ]
