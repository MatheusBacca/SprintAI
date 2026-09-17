import asyncio

import pytest
import respx

from services.sync.engine import SyncAlreadyRunning, SyncEngine, get_sync_engine, save_scope
from services.sync.scope import SyncScope
from tests.sync_fakes import SITE, FakeBitbucket, FakeIssue, FakeJira


def configure(store):
    store.set(
        "jira",
        {
            "site_url": SITE,
            "email": "dev@weon.com.br",
            "api_token": "t" * 24,
            "auth_mode": "classic",
        },
    )
    store.set(
        "bitbucket", {"email": "dev@weon.com.br", "api_token": "t" * 24, "workspace": "weonrepo"}
    )


@pytest.fixture
def engine(db_pool, credential_store):
    async def pool_provider():
        return db_pool

    return SyncEngine(pool_provider=pool_provider, store_provider=lambda: credential_store)


async def test_sem_conexoes_termina_como_failed_com_motivo(engine, db_pool):
    result = await engine.run_once("manual")

    assert result["status"] == "failed"
    assert result["errors"][0]["message"].startswith("Jira: conexão não configurada")
    assert result["stats"]["bitbucket"]["skipped"] is True
    row = await db_pool.fetchrow(
        "SELECT status, finished_at FROM sync_run WHERE id = $1", result["id"]
    )
    assert row["status"] == "failed" and row["finished_at"] is not None


async def test_execucao_completa_jira_e_bitbucket(engine, db_pool, credential_store):
    configure(credential_store)
    await save_scope(
        db_pool, SyncScope.model_validate({"bitbucket": {"repo_slugs": ["monitoria"]}})
    )
    credential_store.set("jira", {**credential_store.get("jira"), "account_id": "acc-me"})
    jira, bb = FakeJira(), FakeBitbucket()
    jira.add(FakeIssue("WAI-7001", "Camada", sprints=[3995], assignee="acc-me"))
    bb.pr("monitoria", 412, "feature/WAI-7001")

    with respx.mock(assert_all_called=False) as router:
        jira.mount(router)
        bb.mount(router)
        result = await engine.run_once("manual")

    assert result["status"] == "success", result["errors"]
    assert result["stats"]["jira"]["issues_fetched"] == 1
    assert result["stats"]["bitbucket"]["pull_requests"] == 1
    states = {r["resource"] for r in await db_pool.fetch("SELECT resource FROM sync_state")}
    assert {"jira", "bitbucket", "bitbucket:repo:monitoria"} <= states


async def test_falha_no_jira_nao_impede_bitbucket(engine, db_pool, credential_store):
    configure(credential_store)
    await save_scope(
        db_pool, SyncScope.model_validate({"bitbucket": {"repo_slugs": ["monitoria"]}})
    )
    bb = FakeBitbucket()

    with respx.mock(assert_all_called=False) as router:
        router.get(f"{SITE}/rest/api/3/myself").respond(401)
        bb.mount(router)
        result = await engine.run_once("manual")

    assert result["status"] == "partial"
    assert result["errors"] == [
        {"stage": "jira", "message": "Jira: credenciais inválidas (e-mail ou token)."}
    ]


async def test_nao_roda_duas_ao_mesmo_tempo(engine, db_pool, credential_store):
    configure(credential_store)
    gate = asyncio.Event()

    with respx.mock(assert_all_called=False) as router:

        async def slow_fields(request):
            await gate.wait()
            return __import__("httpx").Response(401)

        router.get(f"{SITE}/rest/api/3/field").mock(side_effect=slow_fields)
        run_id = await engine.trigger("manual")
        assert engine.running

        with pytest.raises(SyncAlreadyRunning):
            await engine.trigger("manual")

        gate.set()
        await engine._task

    assert not engine.running
    status = await db_pool.fetchval("SELECT status FROM sync_run WHERE id = $1", run_id)
    assert status == "failed"


# --- Rotas ---------------------------------------------------------------------------------


@pytest.fixture
async def sync_client(db_app, engine, client):
    db_app.dependency_overrides[get_sync_engine] = lambda: engine
    return client


async def test_escopo_padrao_e_atualizacao(sync_client):
    response = await sync_client.get("/api/sync/scope")
    assert response.json()["jira"]["board_ids"] == [144]
    assert response.json()["jira"]["squads"] == ["Growth"]
    assert response.json()["bitbucket"]["repo_slugs"] == []

    body = response.json()
    body["bitbucket"]["repo_slugs"] = ["Monitoria", "organia-configs"]
    body["interval_minutes"] = 10
    saved = await sync_client.put("/api/sync/scope", json=body)

    assert saved.status_code == 200
    again = await sync_client.get("/api/sync/scope")
    assert again.json()["bitbucket"]["repo_slugs"] == ["monitoria", "organia-configs"]
    assert again.json()["interval_minutes"] == 10


async def test_sprints_do_escopo_com_contagem(sync_client, db_pool):
    await db_pool.execute(
        """
        INSERT INTO jira_sprint (id, board_id, name, state, squad, in_scope) VALUES
            (1, 144, 'Sprint 73 - Growth', 'active', 'Growth', true),
            (2, 144, '🚨BUGS-ANALISADOS', 'future', NULL, true),
            (3, 144, 'Sprint 73 - Core', 'active', 'Core', false)
        """
    )
    await db_pool.execute(
        """
        INSERT INTO jira_issue (key, id, project_key, issue_type, summary, status, status_category,
                                created_at, updated_at, raw)
        SELECT 'WAI-' || n, n::text, 'WAI', 'Bug', 'x', 'To Do', 'new', now(), now(), '{}'
        FROM generate_series(1, 3) n
        """
    )
    await db_pool.execute(
        "INSERT INTO jira_sprint_issue VALUES (1, 'WAI-1'), (2, 'WAI-2'), (2, 'WAI-3')"
    )

    response = await sync_client.get("/api/sync/sprints")

    assert [(s["name"], s["issue_count"]) for s in response.json()] == [
        ("Sprint 73 - Growth", 1),
        ("🚨BUGS-ANALISADOS", 2),
    ]


async def test_escopo_invalido_da_422(sync_client):
    response = await sync_client.put("/api/sync/scope", json={"interval_minutes": 0})
    assert response.status_code == 422


async def test_status_e_disparo_manual(sync_client, engine):
    status = await sync_client.get("/api/sync/status")
    assert status.json()["running"] is False
    assert status.json()["last_run"] is None
    assert status.json()["counts"]["issues"] == 0

    triggered = await sync_client.post("/api/sync")
    assert triggered.status_code == 202
    await engine._task

    after = (await sync_client.get("/api/sync/status")).json()
    assert after["last_run"]["id"] == triggered.json()["run_id"]
    assert after["last_run"]["status"] == "failed"  # sem conexões configuradas


async def test_banco_fora_do_ar_da_503(app, client):
    from database.pool import DatabaseUnavailable, get_pool

    async def down():
        raise DatabaseUnavailable(
            "Banco local indisponível — suba o Docker (docker compose up -d db)."
        )

    app.dependency_overrides[get_pool] = down

    response = await client.get("/api/sync/status")

    assert response.status_code == 503
    assert response.json()["code"] == "database_unavailable"


async def test_padrao_do_escopo_e_so_o_que_e_meu(sync_client):
    body = (await sync_client.get("/api/sync/scope")).json()

    assert body["jira"]["assignee_scope"] == "mine"
    assert body["bitbucket"]["pr_scope"] == "mine"


async def test_ampliar_filtro_recarrega_sprints_fechadas_e_cursores(sync_client, db_pool):
    await db_pool.execute(
        "INSERT INTO jira_sprint (id, name, state, issues_synced_at) "
        "VALUES (1, 's', 'closed', now())"
    )
    await db_pool.execute(
        "INSERT INTO sync_state (resource, cursor) VALUES ('bitbucket:repo:monitoria', '{}')"
    )
    body = (await sync_client.get("/api/sync/scope")).json()
    body["jira"]["assignee_scope"] = "all"
    body["bitbucket"]["pr_scope"] = "all"

    await sync_client.put("/api/sync/scope", json=body)

    assert await db_pool.fetchval("SELECT issues_synced_at FROM jira_sprint WHERE id = 1") is None
    assert await db_pool.fetchval("SELECT count(*) FROM sync_state") == 0
