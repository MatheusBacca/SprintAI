from datetime import UTC, datetime

import pytest

from repositories import bitbucket_repo

T0 = datetime(2026, 9, 12, 10, 0, tzinfo=UTC)


async def _issue(
    pool, key, *, type_="Tarefa", parent=None, assignee="acc-me", category="indeterminate"
):
    await pool.execute(
        """
        INSERT INTO jira_issue (key, id, project_key, issue_type, summary, status, status_category,
                                assignee_account_id, assignee_name, parent_key, story_points,
                                created_at, updated_at, raw)
        VALUES ($1, $1, 'WAI', $2, 'Resumo ' || $1, 'Em Desenvolvimento', $3, $4, 'Dev', $5, 3,
                now(), now(), '{}')
        """,
        key,
        type_,
        category,
        assignee,
        parent,
    )


@pytest.fixture
async def seeded(db_pool, credential_store):
    credential_store.set(
        "jira",
        {
            "site_url": "https://weon.atlassian.net",
            "email": "d@w.com",
            "api_token": "t" * 24,
            "account_id": "acc-me",
        },
    )
    await db_pool.execute(
        """
        INSERT INTO jira_sprint (id, board_id, name, state, squad, in_scope, start_date, end_date) VALUES
            (3995, 144, 'Sprint 73 - Growth', 'active', 'Growth', true, '2026-09-09', '2026-09-11'),
            (3997, 144, 'Sprint 74 - Growth', 'future', 'Growth', true, '2026-09-14', '2026-09-19'),
            (3961, 144, 'Sprint 72 - Growth', 'closed', 'Growth', true, '2026-09-01', '2026-09-05'),
            (3994, 144, 'Sprint 73 - Core', 'active', 'Core', false, '2026-09-09', '2026-09-11')
        """
    )
    await _issue(db_pool, "WAI-6900", type_="Épico", assignee=None)
    await _issue(db_pool, "WAI-7001", parent="WAI-6900")
    await _issue(db_pool, "WAI-7002", parent="WAI-6900", assignee="acc-outro", category="done")
    await _issue(db_pool, "WAI-7003")
    await db_pool.execute(
        "INSERT INTO jira_sprint_issue VALUES (3995, 'WAI-7001'), (3995, 'WAI-7002'), (3995, 'WAI-7003')"
    )
    await db_pool.execute(
        """
        INSERT INTO jira_issue_link (id, source_key, target_key, link_type, direction, label, target_type)
        VALUES ('1', 'WAI-7001', 'WAI-7003', 'Blocks', 'outward', 'blocks', 'Tarefa')
        """
    )
    await bitbucket_repo.upsert_pull_requests(
        db_pool,
        [
            {
                "repo_slug": "monitoria",
                "id": 412,
                "title": "PR",
                "description": None,
                "state": "OPEN",
                "draft": False,
                "author_name": "Dev",
                "source_branch": "feature/WAI-7001",
                "source_commit": "a",
                "destination_branch": "main",
                "participants": [],
                "comment_count": 0,
                "task_count": 0,
                "build_status": None,
                "issue_keys": ["WAI-7001"],
                "url": None,
                "created_on": T0,
                "updated_on": T0,
            }
        ],
    )


async def test_lista_sprints_do_escopo_com_contagens(db_app, client, seeded):
    response = await client.get("/api/sprints")

    body = response.json()
    assert [(s["id"], s["state"]) for s in body] == [
        (3995, "active"),
        (3997, "future"),
        (3961, "closed"),
    ]
    assert (body[0]["issue_count"], body[0]["mine_count"], body[0]["done_count"]) == (3, 2, 1)


async def test_arvore_da_sprint(db_app, client, seeded):
    response = await client.get("/api/sprints/3995/tree")

    assert response.status_code == 200
    body = response.json()
    assert body["sprint"]["name"] == "Sprint 73 - Growth"
    assert body["counters"]["tasks"] == 3
    assert body["counters"]["blocked"] == 1
    assert [(g["key"], g["issue_keys"]) for g in body["groups"]] == [
        ("WAI-6900", ["WAI-6900", "WAI-7001", "WAI-7002"]),
        ("__sem_pai__", ["WAI-7003"]),
    ]
    nodes = {n["key"]: n for n in body["nodes"]}
    assert nodes["WAI-6900"]["in_sprint"] is False and nodes["WAI-6900"]["pr"] is None
    assert nodes["WAI-7001"]["pr"]["status"] == "pr_aberta"
    assert nodes["WAI-7003"]["pr"]["status"] == "sem_pr"
    assert nodes["WAI-7003"]["blocked_by"] == ["WAI-7001"]
    assert nodes["WAI-7001"]["url"] == "https://weon.atlassian.net/browse/WAI-7001"
    assert nodes["WAI-7001"]["is_mine"] is True
    kinds = sorted((e["source"], e["target"], e["kind"]) for e in body["edges"])
    assert kinds == [
        ("WAI-6900", "WAI-7001", "parent"),
        ("WAI-6900", "WAI-7002", "parent"),
        ("WAI-7001", "WAI-7003", "blocks"),
    ]


async def test_arvore_so_minhas(db_app, client, seeded):
    body = (await client.get("/api/sprints/3995/tree", params={"only_mine": "true"})).json()

    assert sorted(n["key"] for n in body["nodes"]) == ["WAI-6900", "WAI-7001", "WAI-7003"]
    assert body["only_mine"] is True


async def test_sprint_inexistente_da_404(db_app, client, seeded):
    response = await client.get("/api/sprints/1/tree")
    assert response.status_code == 404


async def test_card_tem_etapa_do_mapa_de_progresso(db_app, client, seeded):
    body = (await client.get("/api/sprints/3995/tree")).json()

    stage = {n["key"]: n["stage"] for n in body["nodes"]}["WAI-7001"]
    assert (stage["id"], stage["label"]) == ("desenvolvimento", "Desenvolvimento")


async def test_primeira_abertura_do_canvas_nao_acende_nenhum_card(db_app, client, seeded):
    body = (await client.get("/api/sprints/3995/tree")).json()

    assert all(n["unseen_changes"] == [] for n in body["nodes"])


async def test_mudanca_depois_da_primeira_visita_acende_o_card_ate_o_clique(
    db_app, client, db_pool, seeded
):
    await client.get("/api/sprints/3995/tree")
    await db_pool.execute(
        "UPDATE jira_issue SET status = 'DISPONIVEL PARA REVIEW', story_points = 5 "
        "WHERE key = 'WAI-7001'"
    )

    nodes = {n["key"]: n for n in (await client.get("/api/sprints/3995/tree")).json()["nodes"]}
    assert nodes["WAI-7001"]["unseen_changes"] == ["status", "story_points"]
    assert nodes["WAI-7003"]["unseen_changes"] == []

    assert (await client.post("/api/issues/WAI-7001/seen")).status_code == 204

    nodes = {n["key"]: n for n in (await client.get("/api/sprints/3995/tree")).json()["nodes"]}
    assert nodes["WAI-7001"]["unseen_changes"] == []


async def test_mudanca_de_etapa_do_pr_acende_o_card(db_app, client, db_pool, seeded):
    await client.get("/api/sprints/3995/tree")
    await db_pool.execute(
        "UPDATE bb_pull_request SET state = 'MERGED' WHERE repo_slug = 'monitoria' AND id = 412"
    )

    nodes = {n["key"]: n for n in (await client.get("/api/sprints/3995/tree")).json()["nodes"]}
    assert nodes["WAI-7001"]["unseen_changes"] == ["pr"]


async def test_marcar_visto_tarefa_fora_do_espelho_da_404(db_app, client, seeded):
    assert (await client.post("/api/issues/WAI-9999/seen")).status_code == 404


async def test_bloqueio_libera_o_icone_quando_o_bloqueador_abre_pr(db_app, client, db_pool, seeded):
    nodes = {n["key"]: n for n in (await client.get("/api/sprints/3995/tree")).json()["nodes"]}
    # WAI-7001 (bloqueador) já tem PR aberta no seed.
    assert nodes["WAI-7003"]["blocked_by"] == ["WAI-7001"]
    assert nodes["WAI-7003"]["blockers_without_pr"] == []

    await db_pool.execute(
        "UPDATE bb_pull_request SET draft = true WHERE repo_slug = 'monitoria' AND id = 412"
    )
    nodes = {n["key"]: n for n in (await client.get("/api/sprints/3995/tree")).json()["nodes"]}
    assert nodes["WAI-7003"]["blocked"] is True
    assert nodes["WAI-7003"]["blockers_without_pr"] == ["WAI-7001"]


async def test_bloqueador_concluido_mantem_a_ordem_da_onda(db_app, client, db_pool, seeded):
    await db_pool.execute(
        "UPDATE jira_issue SET status = 'Concluído', status_category = 'done' "
        "WHERE key = 'WAI-7001'"
    )

    body = (await client.get("/api/sprints/3995/tree")).json()

    nodes = {n["key"]: n for n in body["nodes"]}
    assert (nodes["WAI-7003"]["blocked"], nodes["WAI-7003"]["blocked_by"]) == (False, [])
    assert nodes["WAI-7003"]["predecessors"] == ["WAI-7001"]
    assert body["counters"]["blocked"] == 0


async def test_tarefa_originada_por_outra_vem_depois_dela(db_app, client, db_pool, seeded):
    await _issue(db_pool, "WAI-7004", type_="Ajuste")
    await db_pool.execute("INSERT INTO jira_sprint_issue VALUES (3995, 'WAI-7004')")
    await db_pool.execute(
        """
        INSERT INTO jira_issue_link (id, source_key, target_key, link_type, direction, label, target_type)
        VALUES ('2', 'WAI-7004', 'WAI-7002', 'Problem/Incident', 'inward', 'is caused by', 'Tarefa')
        """
    )

    body = (await client.get("/api/sprints/3995/tree")).json()

    nodes = {n["key"]: n for n in body["nodes"]}
    assert nodes["WAI-7004"]["predecessors"] == ["WAI-7002"]
    assert nodes["WAI-7004"]["blocked"] is False
    edges = {(e["source"], e["target"], e["kind"]): e["label"] for e in body["edges"]}
    assert edges[("WAI-7002", "WAI-7004", "causes")] == "origina"


async def test_card_conta_so_lembretes_nao_arquivados(db_app, client, seeded):
    for title, archived in (("Ver retry", False), ("Revisar log", False), ("Antigo", True)):
        note = (
            await client.post("/api/notes", json={"title": title, "issue_keys": ["WAI-7001"]})
        ).json()
        if archived:
            await client.patch(f"/api/notes/{note['id']}", json={"archived": True})

    nodes = {n["key"]: n for n in (await client.get("/api/sprints/3995/tree")).json()["nodes"]}
    assert nodes["WAI-7001"]["note_count"] == 2
    assert nodes["WAI-7003"]["note_count"] == 0
