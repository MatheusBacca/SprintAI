"""Sincronização incremental do Jira.

Cada ciclo:
1. Boards e sprints do escopo (metadados baratos) → marca `in_scope`.
2. Lista só `key + updated` das sprints-alvo e das minhas tarefas.
3. Busca completa apenas do que é novo ou mudou (compara `updated` com o espelho).
4. Busca os pais que faltam (tarefa → épico), para a árvore ficar inteira.
5. Recalcula os membros das sprints ativas/futuras (quem saiu da sprint sai do espelho dela).

Sprints fechadas são congeladas: as tarefas delas são espelhadas uma única vez.

Com `assignee_scope = "mine"` (padrão), as listagens filtram `assignee = currentUser()`
e, ao final, o espelho é podado: sai tudo que não é meu nem pai (épico/enhancement)
de algo meu.
"""

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

import asyncpg

from core.logger import get_logger
from integrations.errors import SprintsNotSupported
from integrations.jira_client import SPRINT_STATES, JiraClient
from repositories import jira_repo
from services.activity.recorder import ActivityRecorder
from services.discovery_service import to_board
from services.hierarchy import is_hierarchy_link
from services.sync.mappers import comment_row, issue_rows, parse_dt, sprint_row
from services.sync.scope import JiraScope, sprint_in_scope

logger = get_logger(__name__)

BASE_FIELDS = (
    "summary",
    "description",
    "status",
    "issuetype",
    "priority",
    "assignee",
    "reporter",
    "parent",
    "labels",
    "components",
    "created",
    "updated",
    "resolutiondate",
    "duedate",
    "issuelinks",
    "comment",
)
FETCH_BATCH = 50
MAX_PARENT_DEPTH = 3


@dataclass
class JiraSyncStats:
    activity: dict | None = None
    boards: int = 0
    sprints_seen: int = 0
    sprints_in_scope: int = 0
    keys_listed: int = 0
    issues_fetched: int = 0
    parents_fetched: int = 0
    comments_paged: int = 0
    issues_pruned: int = 0
    kanban_boards: list[int] = field(default_factory=list)


def _jql_key_list(keys: list[str]) -> str:
    return "key in (" + ",".join(keys) + ")"


class JiraSyncer:
    def __init__(
        self,
        jira: JiraClient,
        pool: asyncpg.Pool,
        scope: JiraScope,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        activity: ActivityRecorder | None = None,
    ) -> None:
        self.jira = jira
        self.pool = pool
        self.scope = scope
        self.now = now
        self.activity = activity
        self.stats = JiraSyncStats()
        self._sprint_field: str | None = None
        self._points_field: str | None = None

    async def run(self) -> JiraSyncStats:
        me = await self.jira.myself()
        my_account_id = me.get("accountId")
        field_map = await self.jira.discover_fields()
        self._sprint_field = field_map.sprint.id if field_map.sprint else None
        self._points_field = field_map.story_points.id if field_map.story_points else None

        active_future, closed_pending = await self._sync_boards_and_sprints()

        remote: dict[str, datetime] = {}
        members: dict[int, list[str]] = {}
        for sprint_id in [*active_future, *closed_pending]:
            listed = await self._list_keys(self._sprint_jql(sprint_id))
            members[sprint_id] = list(listed)
            remote.update(listed)
        remote.update(await self._list_keys(self._my_issues_jql()))
        self.stats.keys_listed = len(remote)

        local = await jira_repo.local_updated_at(self.pool, remote.keys())
        changed = sorted(k for k, updated in remote.items() if k not in local or updated > local[k])
        fetched_parents = await self._fetch_and_save(changed)
        await self._fetch_missing_parents(fetched_parents)

        async with self.pool.acquire() as conn, conn.transaction():
            for sprint_id in active_future:
                await jira_repo.replace_sprint_members(conn, sprint_id, members[sprint_id])
            await jira_repo.mark_sprint_issues_synced(conn, closed_pending)
            if self.scope.assignee_scope == "mine" and my_account_id:
                self.stats.issues_pruned = await jira_repo.prune_not_mine(conn, my_account_id)

        # Depois da poda: eventos de tarefa removida do espelho não interessam ao feed.
        if self.activity is not None:
            result = await self.activity.record(changed_keys=changed, my_account_id=my_account_id)
            self.stats.activity = asdict(result)

        return self.stats

    # --- Etapas ---------------------------------------------------------------------

    async def _sync_boards_and_sprints(self) -> tuple[list[int], list[int]]:
        in_scope: list[dict] = []
        for board_id in self.scope.board_ids:
            board = await self.jira.get_board(board_id)
            await jira_repo.upsert_board(self.pool, to_board(board).model_dump())
            self.stats.boards += 1
            try:
                sprints = [
                    sprint_row(s, board_id=board_id)
                    async for s in self.jira.iter_sprints(board_id, states=SPRINT_STATES)
                ]
            except SprintsNotSupported:
                self.stats.kanban_boards.append(board_id)
                continue
            await jira_repo.upsert_sprints(self.pool, sprints)
            self.stats.sprints_seen += len(sprints)
            in_scope += [
                s
                for s in sprints
                if s["board_id"] == board_id
                and sprint_in_scope(board_id=board_id, squad=s["squad"], scope=self.scope)
            ]

        active_future = [s["id"] for s in in_scope if s["state"] in ("active", "future")]
        closed = sorted(
            (s for s in in_scope if s["state"] == "closed"),
            key=lambda s: s["complete_date"] or s["end_date"] or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )[: self.scope.closed_sprints_limit]
        closed_ids = [s["id"] for s in closed]

        await jira_repo.set_sprints_in_scope(
            self.pool, self.scope.board_ids, [*active_future, *closed_ids]
        )
        self.stats.sprints_in_scope = len(active_future) + len(closed_ids)
        pending = await jira_repo.closed_sprints_pending(self.pool, closed_ids)
        return active_future, [sid for sid in closed_ids if sid in pending]

    def _sprint_jql(self, sprint_id: int) -> str:
        if self.scope.assignee_scope == "mine":
            return f"sprint = {sprint_id} AND assignee = currentUser()"
        return f"sprint = {sprint_id}"

    def _my_issues_jql(self) -> str:
        projects = ",".join(self.scope.project_keys)
        return (
            f"assignee = currentUser() AND project in ({projects}) AND "
            f"(statusCategory != Done OR updated >= -{self.scope.my_issues_lookback_days}d)"
        )

    async def _list_keys(self, jql: str) -> dict[str, datetime]:
        return {
            issue["key"]: parse_dt(issue["fields"]["updated"])
            async for issue in self.jira.iter_search(jql, fields=("updated",))
        }

    async def _fetch_and_save(self, keys: list[str], *, parents: bool = False) -> set[str]:
        """Busca completa em lotes. Devolve os pais (campo parent ou link de hierarquia)
        citados que ainda não estão no espelho."""
        fields = [*BASE_FIELDS, *filter(None, (self._sprint_field, self._points_field))]
        parent_keys: set[str] = set()
        for start in range(0, len(keys), FETCH_BATCH):
            batch = keys[start : start + FETCH_BATCH]
            raws = [r async for r in self.jira.iter_search(_jql_key_list(batch), fields=fields)]
            bundles = []
            for raw in raws:
                rows = issue_rows(
                    raw, sprint_field=self._sprint_field, story_points_field=self._points_field
                )
                if not rows.comments_complete:
                    key = raw["key"]
                    rows.comments = [
                        comment_row(key, c) async for c in self.jira.iter_comments(key)
                    ]
                    self.stats.comments_paged += 1
                bundles.append(rows)
                if rows.issue["parent_key"]:
                    parent_keys.add(rows.issue["parent_key"])
                parent_keys.update(
                    link["target_key"]
                    for link in rows.links
                    if is_hierarchy_link(link["link_type"], link["target_type"])
                )

            async with self.pool.acquire() as conn, conn.transaction():
                for rows in bundles:
                    await jira_repo.save_issue(conn, rows)

            if parents:
                self.stats.parents_fetched += len(bundles)
            else:
                self.stats.issues_fetched += len(bundles)

        present = await jira_repo.existing_keys(self.pool, parent_keys)
        return parent_keys - present

    async def _fetch_missing_parents(self, missing: set[str]) -> None:
        depth = 0
        while missing and depth < MAX_PARENT_DEPTH:
            missing = await self._fetch_and_save(sorted(missing), parents=True)
            depth += 1
