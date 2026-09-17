"""Registro dos eventos do Jira durante o sync (B8).

Roda dentro do `JiraSyncer`, depois que as tarefas já foram salvas:

- **primeira execução** — backfill de `backfill_days` (14) dias, só das minhas tarefas
  atualizadas nessa janela. Sem isso o feed nasceria vazio ou com anos de história;
- **execuções seguintes** — só as minhas tarefas cujo `updated_at` mudou neste ciclo,
  e só o que aconteceu desde a última passagem (com folga de 2 minutos).

Comentários saem do próprio espelho (já vieram no sync da tarefa), sem chamada extra.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import asyncpg

from core.logger import get_logger
from integrations.jira_client import JiraClient
from realtime import bus
from repositories import activity_repo, jira_repo, sync_repo
from services.activity import jira_events

logger = get_logger(__name__)

RESOURCE = "jira:activity"
CURSOR_OVERLAP = timedelta(minutes=2)
# Issue com histórico gigante não pode travar o ciclo.
CHANGELOG_SCAN_LIMIT = 2000


@dataclass
class ActivityStats:
    issues_scanned: int = 0
    transitions: int = 0
    events: int = 0
    purged: int = 0
    backfill: bool = False


class ActivityRecorder:
    def __init__(
        self,
        jira: JiraClient,
        pool: asyncpg.Pool,
        *,
        backfill_days: int = 14,
        retention_days: int = 90,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.jira = jira
        self.pool = pool
        self.backfill_days = backfill_days
        self.retention_days = retention_days
        self.now = now

    async def record(self, *, changed_keys: list[str], my_account_id: str | None) -> ActivityStats:
        stats = ActivityStats()
        started = self.now()
        state = await sync_repo.get_state(self.pool, RESOURCE)
        last_success = state["last_success_at"]
        stats.backfill = last_success is None

        if stats.backfill:
            since = started - timedelta(days=self.backfill_days)
            keys = await activity_repo.mine_updated_since(self.pool, my_account_id, since)
        else:
            since = last_success - CURSOR_OVERLAP
            mine = set(await jira_repo.my_issue_keys(self.pool, my_account_id))
            keys = [k for k in changed_keys if not my_account_id or k in mine]

        category_of = await activity_repo.status_categories(self.pool)
        transitions: list[dict] = []
        events: list[dict] = []

        for key in keys:
            entries = await self._changelog(key)
            if entries is None:
                continue
            stats.issues_scanned += 1
            new_transitions, new_events = jira_events.changelog_rows(
                key,
                entries,
                category_of=category_of,
                my_account_id=my_account_id,
                since=since,
            )
            transitions += new_transitions
            events += new_events

        if keys:
            events += jira_events.comment_events(
                await activity_repo.comments_of(self.pool, keys, since=since),
                my_account_id=my_account_id,
                since=since,
            )

        async with self.pool.acquire() as conn, conn.transaction():
            stats.transitions = await activity_repo.insert_transitions(conn, transitions)
            stats.events = await activity_repo.insert_events(conn, events)
            stats.purged = await activity_repo.purge_before(
                conn, started - timedelta(days=self.retention_days)
            )

        await sync_repo.set_state(self.pool, RESOURCE, cursor={}, success_at=started)
        if stats.events:
            bus.publish(bus.ACTIVITY_NEW, {"source": "jira", "count": stats.events})
        if stats.transitions:
            bus.publish(bus.PROGRESS_CHANGED, {"transitions": stats.transitions})
        return stats

    async def _changelog(self, key: str) -> list[dict] | None:
        entries: list[dict] = []
        try:
            async for entry in self.jira.iter_changelog(key):
                entries.append(entry)
                if len(entries) >= CHANGELOG_SCAN_LIMIT:
                    break
        except Exception:
            # Uma tarefa sem changelog acessível não pode derrubar o ciclo inteiro.
            logger.warning("Changelog de %s não pôde ser lido", key)
            return None
        return entries
