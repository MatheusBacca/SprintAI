"""Deixa os módulos do back importáveis pelo nome (`from config import ...`).

A API roda com `back/` como raiz; o pytest põe `back/tests` no `sys.path`.
Feito aqui para funcionar chamando o pytest de `back/` ou da raiz do repo.
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

_BACK = Path(__file__).resolve().parent.parent
if str(_BACK) not in sys.path:
    sys.path.insert(0, str(_BACK))

TEST_DB_NAME = "sprintai_test"
os.environ["SYNC_AUTOSTART"] = "false"

import asyncpg  # noqa: E402

from config import Settings  # noqa: E402
from database.pool import create_pool, get_pool  # noqa: E402
from security.credential_store import InMemoryCredentialStore, get_credential_store  # noqa: E402

MIRROR_TABLES = (
    "app_setting, jira_board, jira_sprint, jira_issue, jira_sprint_issue, jira_issue_link, "
    "jira_comment, bb_repository, bb_pull_request, bb_pr_comment, bb_branch, sync_state, "
    "sync_run, "
    "note, note_issue_link, task_context, context_relation, search_document, "
    "jira_status_transition, activity_event, issue_seen"
)


@pytest.fixture
def credential_store():
    return InMemoryCredentialStore()


@pytest.fixture
def app(credential_store):
    from main import create_app

    app = create_app()
    # Nunca tocar no Cofre do Windows real durante os testes.
    app.dependency_overrides[get_credential_store] = lambda: credential_store
    return app


@pytest.fixture
async def raw_client(app):
    """Cliente sem o header X-SprintAI (para testar a guarda)."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://127.0.0.1:8765"
    ) as ac:
        yield ac


@pytest.fixture
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://127.0.0.1:8765",
        headers={"X-SprintAI": "1"},
    ) as ac:
        yield ac


# --- Banco de teste --------------------------------------------------------------------


@pytest.fixture(scope="session")
def test_database_dsn() -> str:
    """Recria `sprintai_test` no Postgres do docker-compose e aplica as migrations.

    Testes que dependem do banco são pulados se o Postgres não estiver no ar.
    """
    settings = Settings()
    admin_dsn = settings.asyncpg_dsn
    test_dsn = admin_dsn.rsplit("/", 1)[0] + f"/{TEST_DB_NAME}"

    async def recreate() -> None:
        conn = await asyncpg.connect(admin_dsn, timeout=3)
        try:
            await conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB_NAME} WITH (FORCE)")
            await conn.execute(f"CREATE DATABASE {TEST_DB_NAME}")
        finally:
            await conn.close()

    try:
        asyncio.run(recreate())
    except (OSError, asyncpg.PostgresError, TimeoutError) as exc:
        pytest.skip(f"Postgres local indisponível ({type(exc).__name__}); suba o docker compose")

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=_BACK,
        env={**os.environ, "DB_NAME": TEST_DB_NAME},
        check=True,
        capture_output=True,
    )
    return test_dsn


@pytest.fixture
async def db_pool(test_database_dsn):
    pool = await create_pool(test_database_dsn, min_size=1, max_size=4)
    await pool.execute(f"TRUNCATE {MIRROR_TABLES} RESTART IDENTITY CASCADE")
    yield pool
    await pool.close()


@pytest.fixture
def db_app(app, db_pool):
    async def pool_override():
        return db_pool

    app.dependency_overrides[get_pool] = pool_override
    return app
