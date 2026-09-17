"""B8 — eventos de atividade: extração pura, registro durante o sync e feed."""

from datetime import UTC, datetime, timedelta

import pytest
import respx

from integrations.bitbucket_client import BitbucketClient
from integrations.jira_client import JiraClient
from realtime.bus import ACTIVITY_NEW, get_bus
from repositories import activity_repo
from services.activity import bitbucket_events, jira_events
from services.activity.recorder import ActivityRecorder
from services.sync.bitbucket_sync import BitbucketSyncer
from services.sync.jira_sync import JiraSyncer
from services.sync.scope import BitbucketScope, JiraScope
from tests.sync_fakes import SITE, FakeBitbucket, FakeIssue, FakeJira

ME = "acc-me"
NOW = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)
CATEGORIES = {
    "Disponivel para análise": "new",
    "Em Desenvolvimento": "indeterminate",
    "DISPONIVEL PARA REVIEW": "new",
}


async def _no_sleep(_):
    return None


# --- Extração pura -------------------------------------------------------------------


def _entry(cid, field, before, after, when, author=ME):
    return {
        "id": cid,
        "created": when,
        "author": {"accountId": author, "displayName": "Dev"},
        "items": [{"field": field, "fromString": before, "toString": after}],
    }


def test_changelog_com_duas_transicoes_gera_duas_de_cada():
    entries = [
        _entry(
            "1",
            "status",
            "Disponivel para análise",
            "Em Desenvolvimento",
            "2026-09-10T09:00:00.000+0000",
        ),
        _entry(
            "2",
            "status",
            "Em Desenvolvimento",
            "DISPONIVEL PARA REVIEW",
            "2026-09-12T18:00:00.000+0000",
        ),
    ]
    transitions, events = jira_events.changelog_rows(
        "WAI-1", entries, category_of=CATEGORIES, my_account_id=ME
    )

    assert [t["to_status"] for t in transitions] == ["Em Desenvolvimento", "DISPONIVEL PARA REVIEW"]
    # A categoria não vem no changelog: entra pelo mapa do espelho.
    assert transitions[1]["to_category"] == "new"
    assert [t["changelog_id"] for t in transitions] == ["1:status", "2:status"]
    assert [e["dedupe_key"] for e in events] == [
        "jira:changelog:1:status",
        "jira:changelog:2:status",
    ]
    assert all(e["actor_is_me"] for e in events)


def test_campos_sem_interesse_e_mudanca_nula_sao_ignorados():
    entries = [
        _entry("3", "description", "a", "b", "2026-09-10T09:00:00.000+0000"),
        _entry("4", "priority", "Medium", "Medium", "2026-09-10T09:00:00.000+0000"),
        _entry("5", "Story Points", "3", "5", "2026-09-10T09:00:00.000+0000"),
    ]
    transitions, events = jira_events.changelog_rows("WAI-1", entries, category_of=CATEGORIES)

    assert transitions == []
    assert [(e["kind"], e["title"]) for e in events] == [("story_points", "3 → 5")]


def test_since_corta_o_que_e_antigo_demais():
    entries = [
        _entry("6", "status", "A", "B", "2026-08-01T09:00:00.000+0000"),
        _entry("7", "status", "B", "C", "2026-09-13T09:00:00.000+0000"),
    ]
    _, events = jira_events.changelog_rows(
        "WAI-1", entries, category_of={}, since=NOW - timedelta(days=14)
    )
    assert [e["dedupe_key"] for e in events] == ["jira:changelog:7:status"]


def test_comentario_vira_evento_com_trecho_e_nunca_o_texto_inteiro():
    events = jira_events.comment_events(
        [
            {
                "id": "c1",
                "issue_key": "WAI-1",
                "author_name": "Outro",
                "author_account_id": "acc-outro",
                "body_text": "x" * 500,
                "created_at": NOW,
                "updated_at": NOW + timedelta(minutes=5),
            }
        ],
        my_account_id=ME,
    )
    assert [e["dedupe_key"] for e in events] == [
        "jira:comment:c1:created",
        "jira:comment:c1:updated",
    ]
    assert len(events[0]["title"]) == jira_events.MAX_TITLE
    assert events[0]["actor_is_me"] is False


def _pr(**kw):
    return {
        "repo_slug": "monitoria",
        "id": 7,
        "title": "WAI-1 ajusta coleta",
        "state": "OPEN",
        "draft": False,
        "author_name": "Dev",
        "author_account_id": "bb-me",
        "source_commit": "c1",
        "source_branch": "feature/WAI-1",
        "participants": [],
        "issue_keys": ["WAI-1"],
        "url": "https://bitbucket.org/weonrepo/monitoria/pull-requests/7",
        "created_on": NOW,
        "updated_on": NOW,
        **kw,
    }


def test_pr_de_aberto_a_aprovado_a_mergeado_gera_um_evento_por_passo():
    aberto = _pr()
    aprovado = _pr(
        participants=[
            {"account_id": "bb-rev", "name": "Revisor", "approved": True, "state": "approved"}
        ]
    )
    mergeado = _pr(state="MERGED", participants=aprovado["participants"])

    primeiro = bitbucket_events.pull_request_events(aberto, aprovado, now=NOW)
    segundo = bitbucket_events.pull_request_events(aprovado, mergeado, now=NOW)

    assert [e["kind"] for e in primeiro] == ["pr_approved"]
    assert [e["kind"] for e in segundo] == ["pr_merged"]
    assert primeiro[0]["dedupe_key"] == "bb:pr:monitoria:7:approved:bb-rev"
    assert segundo[0]["issue_key"] == "WAI-1"


def test_pr_novo_rascunho_publicado_commit_e_build():
    novo = bitbucket_events.pull_request_events(None, _pr(draft=True), now=NOW)
    assert [e["kind"] for e in novo] == ["pr_created"]

    publicado = bitbucket_events.pull_request_events(
        _pr(draft=True), _pr(source_commit="c2", build_status="FAILED"), now=NOW
    )
    assert [e["kind"] for e in publicado] == ["pr_ready", "pr_commit", "pr_build_failed"]


def test_build_nao_conferido_no_ciclo_nao_vira_evento():
    events = bitbucket_events.pull_request_events(
        _pr(build_status="SUCCESSFUL"), _pr(build_status=None), now=NOW
    )
    assert events == []


def test_aprovacao_ja_registrada_nao_repete_pela_chave_de_dedupe():
    aprovado = _pr(
        participants=[
            {"account_id": "bb-rev", "name": "Revisor", "approved": True, "state": "approved"}
        ]
    )
    assert bitbucket_events.pull_request_events(aprovado, aprovado, now=NOW) == []


# --- Registro durante o sync ---------------------------------------------------------


@pytest.fixture
def fake_jira():
    jira = FakeJira()
    jira.add(
        FakeIssue(
            "WAI-7001",
            "Camada de integração",
            sprints=[3995],
            assignee=ME,
            comments=["Primeiro achado"],
            changelog=[
                (
                    "1",
                    "status",
                    "Disponivel para análise",
                    "Em Desenvolvimento",
                    "2026-09-10T09:00:00.000+0000",
                    ME,
                ),
                (
                    "2",
                    "status",
                    "Em Desenvolvimento",
                    "DISPONIVEL PARA REVIEW",
                    "2026-09-12T18:00:00.000+0000",
                    "acc-outro",
                ),
            ],
        )
    )
    jira.add(FakeIssue("WAI-7002", "De outro dev", sprints=[3995], assignee="acc-outro"))
    return jira


async def _sync_jira(fake, db_pool):
    with respx.mock(assert_all_called=False) as router:
        fake.mount(router)
        async with await JiraClient.create(
            site_url=SITE, email="d@w.com", api_token="t" * 24, sleep=_no_sleep
        ) as jira:
            recorder = ActivityRecorder(jira, db_pool, now=lambda: NOW)
            return await JiraSyncer(
                jira,
                db_pool,
                JiraScope(closed_sprints_limit=0, assignee_scope="mine"),
                activity=recorder,
            ).run()


async def test_backfill_registra_transicoes_e_nao_duplica_no_ciclo_seguinte(fake_jira, db_pool):
    primeiro = await _sync_jira(fake_jira, db_pool)

    assert primeiro.activity["backfill"] is True
    assert primeiro.activity["transitions"] == 2
    rows = await db_pool.fetch(
        "SELECT to_status, to_category, author_name FROM jira_status_transition ORDER BY changed_at"
    )
    assert [r["to_status"] for r in rows] == ["Em Desenvolvimento", "DISPONIVEL PARA REVIEW"]
    # A categoria sai do espelho: status que nenhuma tarefa tem hoje fica sem categoria
    # (o progresso usa a etapa do mapa configurável, não a categoria).
    assert [r["to_category"] for r in rows] == ["indeterminate", None]

    eventos = await db_pool.fetch("SELECT kind, actor_is_me FROM activity_event ORDER BY id")
    kinds = [r["kind"] for r in eventos]
    assert kinds.count("status") == 2
    assert "comment" in kinds
    # Só o dev que mexeu é "eu".
    assert [r["actor_is_me"] for r in eventos if r["kind"] == "status"] == [True, False]

    segundo = await _sync_jira(fake_jira, db_pool)
    assert (segundo.activity["transitions"], segundo.activity["events"]) == (0, 0)
    assert await db_pool.fetchval("SELECT count(*) FROM jira_status_transition") == 2


async def test_backfill_ignora_changelog_de_quem_nao_e_meu(fake_jira, db_pool):
    await _sync_jira(fake_jira, db_pool)
    assert "WAI-7002" not in fake_jira.changelog_calls


async def test_retencao_apaga_evento_antigo(db_pool):
    await db_pool.execute(
        """
        INSERT INTO activity_event (dedupe_key, source, kind, occurred_at, title)
        VALUES ('velho', 'jira', 'status', now() - interval '120 days', 'x'),
               ('novo', 'jira', 'status', now(), 'y')
        """
    )
    apagados = await activity_repo.purge_before(db_pool, datetime.now(UTC) - timedelta(days=90))
    assert apagados == 1
    assert await db_pool.fetchval("SELECT dedupe_key FROM activity_event") == "novo"


# --- Bitbucket dentro do sync --------------------------------------------------------


async def _sync_bitbucket(fake, db_pool, *, now=NOW):
    with respx.mock(assert_all_called=False) as router:
        fake.mount(router)
        client = BitbucketClient.create(
            email="dev@weon.com.br",
            api_token="t" * 24,
            workspace="weonrepo",
            sleep=_no_sleep,
            max_retries=0,
        )
        async with client as bb:
            syncer = BitbucketSyncer(
                bb,
                db_pool,
                BitbucketScope(repo_slugs=["monitoria"], pr_scope="all"),
                project_keys=["WAI"],
                now=lambda: now,
            )
            return await syncer.run()


async def test_primeira_carga_do_repo_nao_dispara_enxurrada_de_eventos(db_pool):
    fake = FakeBitbucket()
    fake.pr("monitoria", 7, "feature/WAI-1")
    stats = await _sync_bitbucket(fake, db_pool)

    assert stats.events == 0
    assert await db_pool.fetchval("SELECT count(*) FROM activity_event") == 0


async def test_segundo_ciclo_registra_aprovacao_e_avisa_o_stream(db_pool):
    fake = FakeBitbucket()
    fake.pr("monitoria", 7, "feature/WAI-1")
    await _sync_bitbucket(fake, db_pool)

    fake.pr(
        "monitoria",
        7,
        "feature/WAI-1",
        updated="2026-09-14T11:00:00+00:00",
        participants=[
            {
                "user": {"account_id": "bb-rev", "display_name": "Revisor"},
                "approved": True,
                "state": "approved",
                "role": "REVIEWER",
            }
        ],
    )
    async with get_bus().subscribe() as queue:
        stats = await _sync_bitbucket(fake, db_pool, now=NOW + timedelta(minutes=30))
        assert stats.events == 1
        assert queue.get_nowait().kind == ACTIVITY_NEW

    row = await db_pool.fetchrow("SELECT kind, issue_key, repo_slug, pr_id FROM activity_event")
    assert (row["kind"], row["issue_key"], row["repo_slug"], row["pr_id"]) == (
        "pr_approved",
        "WAI-1",
        "monitoria",
        7,
    )


# --- Feed ----------------------------------------------------------------------------


@pytest.fixture
async def feed_api(db_app, client, credential_store, db_pool):
    credential_store.set(
        "jira", {"site_url": SITE, "email": "d@w.com", "api_token": "t" * 24, "account_id": ME}
    )
    await db_pool.execute(
        """
        INSERT INTO jira_issue (key, id, project_key, issue_type, summary, status, status_category,
                                created_at, updated_at, raw)
        VALUES ('WAI-1', '1', 'WAI', 'Tarefa', 'Coleta', 'Em Desenvolvimento', 'indeterminate',
                now(), now(), '{}')
        """
    )
    await db_pool.executemany(
        """
        INSERT INTO activity_event (dedupe_key, source, kind, issue_key, actor_is_me, occurred_at,
                                    title)
        VALUES ($1, $2, $3, 'WAI-1', $4, $5, $6)
        """,
        [
            ("a", "jira", "status", True, datetime(2026, 9, 10, tzinfo=UTC), "Em Desenvolvimento"),
            ("b", "bitbucket", "pr_approved", False, datetime(2026, 9, 12, tzinfo=UTC), "PR 7"),
            ("c", "jira", "comment", False, datetime(2026, 9, 13, tzinfo=UTC), "Olha isso"),
        ],
    )
    return client


async def test_feed_vem_do_mais_novo_para_o_mais_antigo(feed_api):
    response = await feed_api.get("/api/activity")
    assert response.status_code == 200, response.text
    data = response.json()

    assert [e["kind"] for e in data["events"]] == ["comment", "pr_approved", "status"]
    assert data["next_cursor"] is None
    assert data["events"][0]["issue_summary"] == "Coleta"
    assert data["events"][0]["issue_url"] == f"{SITE}/browse/WAI-1"


async def test_feed_pagina_por_cursor_sem_repetir(feed_api):
    primeira = (await feed_api.get("/api/activity", params={"limit": 2})).json()
    assert [e["kind"] for e in primeira["events"]] == ["comment", "pr_approved"]
    assert primeira["next_cursor"]

    segunda = (
        await feed_api.get("/api/activity", params={"cursor": primeira["next_cursor"]})
    ).json()
    assert [e["kind"] for e in segunda["events"]] == ["status"]
    assert segunda["next_cursor"] is None


async def test_feed_filtra_por_fonte_e_por_so_de_outros(feed_api):
    jira = (await feed_api.get("/api/activity", params={"source": "jira"})).json()
    assert [e["kind"] for e in jira["events"]] == ["comment", "status"]

    outros = (await feed_api.get("/api/activity", params={"only_others": "true"})).json()
    assert [e["kind"] for e in outros["events"]] == ["comment", "pr_approved"]


async def test_cursor_invalido_e_recusado(feed_api):
    response = await feed_api.get("/api/activity", params={"cursor": "não-é-cursor"})
    assert response.status_code == 422
