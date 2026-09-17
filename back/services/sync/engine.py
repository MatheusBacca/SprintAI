"""Motor de sincronização: uma execução por vez, registro em `sync_run`, agendador.

O agendador é um laço asyncio dentro da própria API (processo local de um dev só).
Jira e Bitbucket rodam em sequência na mesma execução; a falha de um não impede
o outro — a execução termina como `partial`.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

import asyncpg

from core.logger import get_logger
from database.pool import DatabaseUnavailable, get_pool
from integrations import factory
from integrations.errors import IntegrationError, IntegrationNotConfigured
from realtime import bus
from repositories import bitbucket_repo, jira_repo, settings_repo, sync_repo
from security.credential_store import CredentialStore, CredentialStoreError, get_credential_store
from services.activity.recorder import ActivityRecorder
from services.sync.bitbucket_sync import BitbucketSyncer
from services.sync.jira_sync import JiraSyncer
from services.sync.scope import SyncScope

logger = get_logger(__name__)

SCOPE_KEY = "sync_scope"


class SyncAlreadyRunning(Exception):
    pass


async def load_scope(pool: asyncpg.Pool) -> SyncScope:
    value = await settings_repo.get_setting(pool, SCOPE_KEY)
    return SyncScope.model_validate(value) if value else SyncScope()


async def save_scope(pool: asyncpg.Pool, scope: SyncScope) -> None:
    previous = await load_scope(pool)
    async with pool.acquire() as conn, conn.transaction():
        await settings_repo.set_setting(conn, SCOPE_KEY, scope.model_dump(mode="json"))
        # Ampliar o filtro exige recarregar o que foi pulado antes.
        if previous.jira.assignee_scope != scope.jira.assignee_scope:
            await jira_repo.reset_closed_sprints(conn)
        if previous.bitbucket.pr_scope != scope.bitbucket.pr_scope:
            await bitbucket_repo.reset_repo_cursors(conn)


class SyncEngine:
    def __init__(
        self,
        *,
        pool_provider: Callable[[], Awaitable[asyncpg.Pool]] = get_pool,
        store_provider: Callable[[], CredentialStore] = get_credential_store,
    ) -> None:
        self._pool_provider = pool_provider
        self._store_provider = store_provider
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._scheduler: asyncio.Task | None = None
        self._wake = asyncio.Event()
        self.current_run_id: int | None = None
        self.current_stage: str | None = None

    @property
    def running(self) -> bool:
        return self._lock.locked()

    # --- Disparo ----------------------------------------------------------------------

    async def _begin(self, trigger: str, pool: asyncpg.Pool | None) -> tuple[asyncpg.Pool, int]:
        pool = pool or await self._pool_provider()
        if self._lock.locked():
            raise SyncAlreadyRunning()
        await self._lock.acquire()  # livre: não suspende, então não há corrida com o check
        try:
            run_id = await sync_repo.start_run(pool, trigger)
        except BaseException:
            self._lock.release()
            raise
        self.current_run_id = run_id
        return pool, run_id

    async def trigger(self, trigger: str = "manual") -> int:
        """Registra a execução e roda em segundo plano; devolve o id."""
        pool, run_id = await self._begin(trigger, None)
        self._task = asyncio.create_task(self._execute(pool, run_id))
        return run_id

    async def run_once(self, trigger: str, *, pool: asyncpg.Pool | None = None) -> dict[str, Any]:
        pool, run_id = await self._begin(trigger, pool)
        return await self._execute(pool, run_id)

    async def _execute(self, pool: asyncpg.Pool, run_id: int) -> dict[str, Any]:
        stats: dict[str, Any] = {}
        errors: list[dict[str, str]] = []
        status = "failed"
        try:
            scope = await load_scope(pool)
            store = self._store_provider()
            await self._run_jira(pool, store, scope, stats, errors)
            await self._run_bitbucket(pool, store, scope, stats, errors)
            status = self._final_status(stats, errors)
        except asyncio.CancelledError:
            errors.append(
                {"stage": "engine", "message": "Sincronização interrompida (API reiniciada)."}
            )
            raise
        except Exception as exc:  # nunca deixar a execução "running" para trás
            logger.exception("Sync falhou")
            errors.append({"stage": "engine", "message": str(exc) or type(exc).__name__})
        finally:
            try:
                await sync_repo.finish_run(pool, run_id, status=status, stats=stats, errors=errors)
                bus.publish(bus.SYNC_FINISHED, {"id": run_id, "status": status})
            finally:
                self.current_run_id = None
                self.current_stage = None
                self._lock.release()
        return {"id": run_id, "status": status, "stats": stats, "errors": errors}

    @staticmethod
    def _final_status(stats: dict[str, Any], errors: list[dict[str, str]]) -> str:
        if not errors:
            return "success"
        ran = {k for k, v in stats.items() if isinstance(v, dict) and not v.get("skipped")}
        return "partial" if ran else "failed"

    async def _run_jira(self, pool, store, scope, stats, errors) -> None:
        self.current_stage = "jira"
        started = datetime.now(UTC)
        try:
            async with await factory.jira_client(store) as jira:
                recorder = ActivityRecorder(jira, pool)
                result = await JiraSyncer(jira, pool, scope.jira, activity=recorder).run()
            stats["jira"] = asdict(result)
            await sync_repo.set_state(pool, "jira", cursor={}, success_at=started)
        except IntegrationNotConfigured as exc:
            stats["jira"] = {"skipped": True}
            errors.append({"stage": "jira", "message": exc.message})
        except IntegrationError as exc:
            errors.append({"stage": "jira", "message": exc.message})
        except CredentialStoreError as exc:
            errors.append({"stage": "jira", "message": str(exc)})

    async def _run_bitbucket(self, pool, store, scope, stats, errors) -> None:
        self.current_stage = "bitbucket"
        if not scope.bitbucket.repo_slugs:
            stats["bitbucket"] = {"skipped": True, "reason": "nenhum repositório escolhido"}
            return
        started = datetime.now(UTC)
        syncer: BitbucketSyncer | None = None
        try:
            async with factory.bitbucket_client(store) as bitbucket:
                jira_me = (store.get("jira") or {}).get("account_id")
                my_keys = await jira_repo.my_issue_keys(pool, jira_me) if jira_me else []
                syncer = BitbucketSyncer(
                    bitbucket,
                    pool,
                    scope.bitbucket,
                    project_keys=scope.jira.project_keys,
                    my_issue_keys=my_keys,
                )
                await syncer.run()
            await sync_repo.set_state(pool, "bitbucket", cursor={}, success_at=started)
        except IntegrationNotConfigured as exc:
            stats["bitbucket"] = {"skipped": True}
            errors.append({"stage": "bitbucket", "message": exc.message})
        except IntegrationError as exc:
            errors.append({"stage": "bitbucket", "message": exc.message})
        except CredentialStoreError as exc:
            errors.append({"stage": "bitbucket", "message": str(exc)})
        finally:
            if syncer is not None:
                result = syncer.stats
                stats["bitbucket"] = asdict(result)
                errors.extend(
                    {"stage": f"bitbucket:{e['repo']}", "message": e["message"]}
                    for e in result.repo_errors
                )
                if result.missing_repositories:
                    missing = ", ".join(result.missing_repositories)
                    errors.append(
                        {
                            "stage": "bitbucket",
                            "message": f"Repositórios não encontrados: {missing}",
                        }
                    )

    # --- Agendador ----------------------------------------------------------------------

    def start_scheduler(self) -> None:
        if self._scheduler is None:
            self._scheduler = asyncio.create_task(self._scheduler_loop())

    async def stop(self) -> None:
        for task in (self._scheduler, self._task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
        self._scheduler = None

    def reschedule(self) -> None:
        """Acorda o agendador (escopo/intervalo mudou)."""
        self._wake.set()

    async def _scheduler_loop(self) -> None:
        first = True
        while True:
            interval = 5
            try:
                pool = await self._pool_provider()
                if first:
                    await sync_repo.abandon_running(pool)
                    first = False
                scope = await load_scope(pool)
                interval = scope.interval_minutes
                if scope.enabled and not self.running and await self._due(pool, interval):
                    await self.run_once("scheduled", pool=pool)
            except DatabaseUnavailable:
                pass  # tenta de novo no próximo ciclo
            except SyncAlreadyRunning:
                pass
            except Exception:
                logger.exception("Agendador de sync falhou")

            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=60)
            except TimeoutError:
                pass

    @staticmethod
    async def _due(pool: asyncpg.Pool, interval_minutes: int) -> bool:
        last = await sync_repo.latest_run(pool)
        if last is None:
            return True
        reference = last["finished_at"] or last["started_at"]
        return (datetime.now(UTC) - reference).total_seconds() >= interval_minutes * 60


_engine: SyncEngine | None = None


def get_sync_engine() -> SyncEngine:
    global _engine
    if _engine is None:
        _engine = SyncEngine()
    return _engine
