"""Sincronização incremental do Bitbucket, só dos repositórios escolhidos pelo dev.

Por repositório, a cada ciclo:
- PRs com `updated_on` depois do cursor (todos os estados);
- a cada `full_sweep_minutes`, todos os PRs abertos (aprovação e pedido de ajuste
  nem sempre mexem no `updated_on` do repositório);
- status de build só dos PRs abertos cujo commit mudou;
- comentários só dos PRs cujo `comment_count` mudou (ele vem de graça na listagem);
- branches com a chave do projeto só quando houve push (repo `updated_on` mudou),
  lidas da mais recente para a mais antiga até o cursor.

Com `pr_scope = "mine"` (padrão), só entram PRs em que o dev é autor ou participante,
ou ligados a tarefas dele no espelho do Jira; branches só de tarefas dele.
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg

from core.logger import get_logger
from integrations.bitbucket_client import BitbucketClient
from integrations.errors import IntegrationError, RateLimited
from realtime import bus
from repositories import activity_repo, bitbucket_repo, sync_repo
from services.activity import bitbucket_events
from services.sync.mappers import (
    branch_row,
    build_status,
    parse_dt,
    pr_comment_row,
    pull_request_row,
    repository_row,
)
from services.sync.scope import BitbucketScope

logger = get_logger(__name__)

CURSOR_OVERLAP = timedelta(minutes=2)
REPO_CONCURRENCY = 4


@dataclass
class BitbucketSyncStats:
    repositories: int = 0
    pull_requests: int = 0
    open_pull_requests_refreshed: int = 0
    build_statuses: int = 0
    pr_comments: int = 0
    branches: int = 0
    events: int = 0
    skipped_not_mine: int = 0
    pruned_pull_requests: int = 0
    pruned_branches: int = 0
    missing_repositories: list[str] = field(default_factory=list)
    repo_errors: list[dict[str, str]] = field(default_factory=list)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class BitbucketSyncer:
    def __init__(
        self,
        bitbucket: BitbucketClient,
        pool: asyncpg.Pool,
        scope: BitbucketScope,
        *,
        project_keys: list[str],
        my_issue_keys: list[str] | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.bb = bitbucket
        self.pool = pool
        self.scope = scope
        self.project_keys = project_keys
        self.now = now
        self.stats = BitbucketSyncStats()
        self._rate_limited = asyncio.Event()
        self.my_issue_keys = set(my_issue_keys or [])
        self._my_identities: set[str] | None = None

    async def run(self) -> BitbucketSyncStats:
        if not self.scope.repo_slugs:
            return self.stats

        if self.scope.pr_scope == "mine":
            me = await self.bb.current_user()
            self._my_identities = {i for i in (me.get("account_id"), me.get("uuid")) if i}

        repos = [
            repository_row(r) async for r in self.bb.iter_repositories(slugs=self.scope.repo_slugs)
        ]
        await bitbucket_repo.upsert_repositories(self.pool, repos)
        found = {r["slug"] for r in repos}
        self.stats.missing_repositories = [s for s in self.scope.repo_slugs if s not in found]
        self.stats.repositories = len(repos)

        semaphore = asyncio.Semaphore(REPO_CONCURRENCY)

        async def guarded(repo: dict[str, Any]) -> None:
            async with semaphore:
                if self._rate_limited.is_set():
                    return
                try:
                    await self._sync_repository(repo)
                except RateLimited as exc:
                    self._rate_limited.set()
                    self.stats.repo_errors.append({"repo": repo["slug"], "message": exc.message})
                except IntegrationError as exc:
                    self.stats.repo_errors.append({"repo": repo["slug"], "message": exc.message})

        await asyncio.gather(*(guarded(r) for r in repos))

        identities = sorted(self._my_identities) if self._my_identities is not None else None
        removed = await bitbucket_repo.prune(
            self.pool,
            repo_slugs=self.scope.repo_slugs,
            my_identities=identities,
            my_issue_keys=sorted(self.my_issue_keys),
        )
        self.stats.pruned_pull_requests = removed["pull_requests"]
        self.stats.pruned_branches = removed["branches"]
        if self._rate_limited.is_set():
            raise RateLimited(
                "Bitbucket",
                "Bitbucket: limite de requisições atingido; o restante fica para o próximo ciclo.",
            )
        return self.stats

    async def _sync_repository(self, repo: dict[str, Any]) -> None:
        slug = repo["slug"]
        resource = f"bitbucket:repo:{slug}"
        started = self.now()
        state = await sync_repo.get_state(self.pool, resource)
        cursor = dict(state["cursor"] or {})
        initial = started - timedelta(days=self.scope.initial_lookback_days)

        prs_since = parse_dt(cursor.get("prs_since")) or initial
        changed = [
            pull_request_row(slug, raw, project_keys=self.project_keys)
            async for raw in self.bb.iter_pull_requests(
                slug, updated_since=prs_since - CURSOR_OVERLAP
            )
        ]

        last_sweep = parse_dt(cursor.get("full_sweep_at"))
        sweep_due = last_sweep is None or started - last_sweep >= timedelta(
            minutes=self.scope.full_sweep_minutes
        )
        if sweep_due:
            seen = {pr["id"] for pr in changed}
            open_prs = [
                pull_request_row(slug, raw, project_keys=self.project_keys)
                async for raw in self.bb.iter_pull_requests(slug, states=("OPEN",))
            ]
            changed += [pr for pr in open_prs if pr["id"] not in seen]
            self.stats.open_pull_requests_refreshed += len(open_prs)

        if self._my_identities is not None:
            mine = [pr for pr in changed if self._is_mine(pr)]
            self.stats.skipped_not_mine += len(changed) - len(mine)
            changed = mine

        previous = await bitbucket_repo.previous_pull_requests(
            self.pool, slug, [pr["id"] for pr in changed]
        )
        for pr in changed:
            before = previous.get(pr["id"])
            if pr["state"] == "OPEN" and (before or {}).get("source_commit") != pr["source_commit"]:
                statuses = [s async for s in self.bb.iter_pull_request_statuses(slug, pr["id"])]
                pr["build_status"] = build_status(statuses)
                self.stats.build_statuses += 1

        # B8: o diff tem de sair antes do upsert, que sobrescreve a linha anterior.
        # Na primeira carga do repositório não há "antes": tudo viraria evento de uma vez.
        first_load = state["last_success_at"] is None
        if not first_load:
            await self._record_events(changed, previous, at=started)

        await bitbucket_repo.upsert_pull_requests(self.pool, changed)
        self.stats.pull_requests += len(changed)

        # Depois do upsert do PR: a chave estrangeira do comentário aponta para ele.
        await self._sync_comments(changed, previous, at=started, with_events=not first_load)

        repo_updated = repo["updated_on"]
        if _iso(repo_updated) != cursor.get("repo_updated_on"):
            branches_since = parse_dt(cursor.get("branches_since")) or initial
            branches = []
            for project in self.project_keys:
                async for raw in self.bb.iter_branches(slug, name_contains=f"{project}-"):
                    row = branch_row(slug, raw, project_keys=self.project_keys)
                    if row["target_date"] and row["target_date"] < branches_since - CURSOR_OVERLAP:
                        break  # ordenado por data do último commit, do mais recente
                    if row["issue_keys"] and self._branch_wanted(row):
                        branches.append(row)
            await bitbucket_repo.upsert_branches(self.pool, branches)
            self.stats.branches += len(branches)
            cursor["branches_since"] = _iso(started)
            cursor["repo_updated_on"] = _iso(repo_updated)

        cursor["prs_since"] = _iso(started)
        if sweep_due:
            cursor["full_sweep_at"] = _iso(started)
        await sync_repo.set_state(self.pool, resource, cursor=cursor, success_at=started)

    async def _record_events(
        self,
        changed: list[dict[str, Any]],
        previous: dict[int, dict[str, Any]],
        *,
        at: datetime,
    ) -> None:
        events: list[dict[str, Any]] = []
        for pr in changed:
            events += bitbucket_events.pull_request_events(
                previous.get(pr["id"]),
                pr,
                my_identities=self._my_identities,
                now=at,
            )
        await self._insert_events(events)

    async def _sync_comments(
        self,
        changed: list[dict[str, Any]],
        previous: dict[int, dict[str, Any]],
        *,
        at: datetime,
        with_events: bool,
    ) -> None:
        """Baixa os comentários dos PRs cuja contagem mudou — ou que nunca foram baixados.

        O `comment_count` já vem na listagem, de graça, e é ele que decide a requisição
        extra: sem esse filtro cada sweep dos PRs abertos viraria uma chamada por PR só
        para redescobrir a mesma review. O segundo caso é o backfill — um PR que já tinha
        review quando esta tabela nasceu tem contagem estável, e sem ele a review nunca
        apareceria.
        """
        if not changed:
            return
        repo = changed[0]["repo_slug"]
        mirrored = await bitbucket_repo.pr_ids_with_comments(
            self.pool, repo, [pr["id"] for pr in changed if (pr.get("comment_count") or 0) > 0]
        )

        for pr in changed:
            count = pr.get("comment_count")
            before_count = (previous.get(pr["id"]) or {}).get("comment_count")
            if count is None:
                continue
            if count == 0 and not before_count:
                continue
            if count == before_count and pr["id"] in mirrored:
                continue

            slug, pr_id = pr["repo_slug"], pr["id"]
            comments = [
                pr_comment_row(slug, pr_id, raw)
                async for raw in self.bb.iter_pull_request_comments(slug, pr_id)
            ]
            if not comments:
                continue

            # Lido antes do upsert: é contra ele que sai o "comentário novo".
            known = await bitbucket_repo.known_pr_comment_ids(self.pool, slug, pr_id)
            self.stats.pr_comments += await bitbucket_repo.upsert_pr_comments(self.pool, comments)
            if with_events:
                await self._insert_events(
                    bitbucket_events.pull_request_comment_events(
                        pr, comments, known, my_identities=self._my_identities, now=at
                    )
                )

    async def _insert_events(self, events: list[dict[str, Any]]) -> None:
        if not events:
            return
        inserted = await activity_repo.insert_events(self.pool, events)
        self.stats.events += inserted
        if inserted:
            bus.publish(bus.ACTIVITY_NEW, {"source": "bitbucket", "count": inserted})

    def _is_mine(self, pr: dict[str, Any]) -> bool:
        ids = self._my_identities or set()
        if pr.get("author_account_id") in ids:
            return True
        if any(p.get("account_id") in ids for p in pr["participants"]):
            return True
        return bool(self.my_issue_keys.intersection(pr["issue_keys"]))

    def _branch_wanted(self, row: dict[str, Any]) -> bool:
        if self._my_identities is None:
            return True
        return bool(self.my_issue_keys.intersection(row["issue_keys"]))
