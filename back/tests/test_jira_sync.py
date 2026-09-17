import pytest
import respx

from integrations.jira_client import JiraClient
from services.sync.jira_sync import JiraSyncer
from services.sync.scope import JiraScope
from tests.sync_fakes import SITE, FakeIssue, FakeJira


async def _no_sleep(_):
    return None


@pytest.fixture
def fake():
    jira = FakeJira()
    jira.add(FakeIssue("WAI-6900", "Épico de integração", issue_type="Epic"))
    jira.add(
        FakeIssue(
            "WAI-7001",
            "Camada de integração",
            sprints=[3995],
            parent="WAI-6900",
            assignee="acc-me",
            comments=["Primeiro achado"],
            links=[("Blocks", "WAI-7003")],
        )
    )
    jira.add(
        FakeIssue(
            "WAI-7002", "Áudio (outro dev)", sprints=[3995], parent="WAI-6900", assignee="acc-outro"
        )
    )
    jira.add(FakeIssue("WAI-7003", "Bug no suporte", sprints=[2404]))
    jira.add(FakeIssue("WAI-5000", "Tarefa da Core", sprints=[3994]))
    jira.add(FakeIssue("WAI-6100", "Tarefa da sprint 72", sprints=[3961]))
    jira.add(FakeIssue("WAI-5900", "Tarefa da sprint 69", sprints=[3954]))
    jira.add(FakeIssue("WAI-7100", "Minha tarefa solta", assignee="acc-me"))
    return jira


async def _run(fake, db_pool, **scope):
    with respx.mock(assert_all_called=False) as router:
        fake.mount(router)
        async with await JiraClient.create(
            site_url=SITE, email="dev@weon.com.br", api_token="t" * 24, sleep=_no_sleep
        ) as jira:
            return await JiraSyncer(
                jira,
                db_pool,
                JiraScope(**{"closed_sprints_limit": 1, "assignee_scope": "all", **scope}),
            ).run()


async def test_primeira_carga_respeita_escopo_growth_mais_baldes(fake, db_pool):
    stats = await _run(fake, db_pool)

    in_scope = await db_pool.fetch("SELECT id FROM jira_sprint WHERE in_scope ORDER BY id")
    # Growth ativa 3995, balde 2404 e só a fechada mais recente (limite 1): 3961. Core e 3954 fora.
    assert [r["id"] for r in in_scope] == [2404, 3961, 3995]

    keys = {r["key"] for r in await db_pool.fetch("SELECT key FROM jira_issue")}
    assert keys == {"WAI-6900", "WAI-7001", "WAI-7002", "WAI-7003", "WAI-6100", "WAI-7100"}
    assert "WAI-5000" not in keys  # sprint Core
    assert stats.parents_fetched == 1  # épico WAI-6900 veio por ser pai

    members = await db_pool.fetch(
        "SELECT issue_key FROM jira_sprint_issue WHERE sprint_id = 3995 ORDER BY issue_key"
    )
    assert [r["issue_key"] for r in members] == ["WAI-7001", "WAI-7002"]

    link = await db_pool.fetchrow("SELECT * FROM jira_issue_link WHERE source_key = 'WAI-7001'")
    assert (link["target_key"], link["label"]) == ("WAI-7003", "blocks")
    comment = await db_pool.fetchrow(
        "SELECT body_text FROM jira_comment WHERE issue_key = 'WAI-7001'"
    )
    assert comment["body_text"] == "Primeiro achado"

    closed = await db_pool.fetchval("SELECT issues_synced_at FROM jira_sprint WHERE id = 3961")
    assert closed is not None


async def test_segundo_ciclo_so_busca_o_que_mudou(fake, db_pool):
    await _run(fake, db_pool)
    fake.full_fetches.clear()
    fake.listings.clear()
    fake.issues["WAI-7002"].updated = "2026-09-13T09:00:00.000+0000"
    fake.issues["WAI-7002"].summary = "Áudio — ajustado"

    stats = await _run(fake, db_pool)

    assert fake.full_fetches == [["WAI-7002"]]
    assert stats.issues_fetched == 1
    # sprint fechada não é relistada
    assert "sprint = 3961" not in fake.listings
    summary = await db_pool.fetchval("SELECT summary FROM jira_issue WHERE key = 'WAI-7002'")
    assert summary == "Áudio — ajustado"


async def test_tarefa_que_sai_da_sprint_ativa_sai_do_espelho_da_sprint(fake, db_pool):
    await _run(fake, db_pool)
    fake.issues["WAI-7002"].sprints = []
    fake.issues["WAI-7002"].updated = "2026-09-13T09:00:00.000+0000"

    await _run(fake, db_pool)

    members = await db_pool.fetch("SELECT issue_key FROM jira_sprint_issue WHERE sprint_id = 3995")
    assert [r["issue_key"] for r in members] == ["WAI-7001"]
    # a issue continua no espelho (histórico), só não pertence mais à sprint
    assert await db_pool.fetchval("SELECT count(*) FROM jira_issue WHERE key = 'WAI-7002'") == 1


async def test_escopo_com_todas_as_squads_inclui_core(fake, db_pool):
    await _run(fake, db_pool, squads=[])

    assert await db_pool.fetchval("SELECT count(*) FROM jira_issue WHERE key = 'WAI-5000'") == 1


async def test_comentarios_alem_da_primeira_pagina_sao_paginados(fake, db_pool):
    issue = fake.issues["WAI-7001"]
    original_full = fake._full

    def truncated(i):
        payload = original_full(i)
        if i.key == "WAI-7001":
            payload["fields"]["comment"]["total"] = 2
        return payload

    fake._full = truncated
    with respx.mock(assert_all_called=False) as router:
        fake.mount(router)
        router.get(f"{SITE}/rest/api/3/issue/WAI-7001/comment").respond(
            200,
            json={
                "startAt": 0,
                "total": 2,
                "comments": [
                    {
                        "id": "c-a",
                        "author": {"displayName": "A"},
                        "body": "um",
                        "created": "2026-09-02T10:00:00.000+0000",
                    },
                    {
                        "id": "c-b",
                        "author": {"displayName": "B"},
                        "body": "dois",
                        "created": "2026-09-03T10:00:00.000+0000",
                    },
                ],
            },
        )
        async with await JiraClient.create(
            site_url=SITE, email="dev@weon.com.br", api_token="t" * 24, sleep=_no_sleep
        ) as jira:
            stats = await JiraSyncer(
                jira, db_pool, JiraScope(closed_sprints_limit=1, assignee_scope="all")
            ).run()

    assert stats.comments_paged == 1
    texts = await db_pool.fetch(
        "SELECT body_text FROM jira_comment WHERE issue_key = $1 ORDER BY created_at", issue.key
    )
    assert [r["body_text"] for r in texts] == ["um", "dois"]


# --- Escopo "só as minhas" (padrão) ------------------------------------------------------------


async def test_padrao_so_minhas_tarefas_mais_os_pais(fake, db_pool):
    fake.add(FakeIssue("WAI-6000", "Enhancement do fatiamento", issue_type="Enhancements"))
    fake.issues["WAI-7100"].links = [("Relates", "WAI-6000")]
    fake.issues["WAI-7100"].sprints = [3995]

    stats = await _run(fake, db_pool, assignee_scope="mine")

    keys = {r["key"] for r in await db_pool.fetch("SELECT key FROM jira_issue")}
    # minhas: WAI-7001 (sprint) e WAI-7100 (solta, agora na sprint); pais: épico e enhancement
    assert keys == {"WAI-7001", "WAI-7100", "WAI-6900", "WAI-6000"}
    assert "sprint = 3995 AND assignee = currentUser()" in fake.listings
    members = await db_pool.fetch("SELECT issue_key FROM jira_sprint_issue WHERE sprint_id = 3995")
    assert {r["issue_key"] for r in members} == {"WAI-7001", "WAI-7100"}
    assert stats.parents_fetched == 2


async def test_trocar_de_tudo_para_minhas_poda_o_espelho(fake, db_pool):
    await _run(fake, db_pool, assignee_scope="all")
    assert await db_pool.fetchval("SELECT count(*) FROM jira_issue") == 6

    stats = await _run(fake, db_pool, assignee_scope="mine")

    keys = {r["key"] for r in await db_pool.fetch("SELECT key FROM jira_issue")}
    assert keys == {"WAI-7001", "WAI-7100", "WAI-6900"}
    assert stats.issues_pruned == 3
    # sprint fechada congelada também perde as tarefas de outros
    assert (
        await db_pool.fetchval("SELECT count(*) FROM jira_sprint_issue WHERE sprint_id = 3961") == 0
    )
