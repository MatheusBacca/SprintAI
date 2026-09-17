from datetime import UTC, datetime

import httpx
import pytest
import respx

from repositories import bitbucket_repo

SITE = "https://weon.atlassian.net"
T0 = datetime(2026, 9, 12, 10, 0, tzinfo=UTC)
DESCRIPTION = {
    "type": "doc",
    "version": 1,
    "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": "Integrar com a OpenAI"}]}
    ],
}


async def _issue(pool, key, **kw):
    await pool.execute(
        """
        INSERT INTO jira_issue (key, id, project_key, issue_type, summary, description_adf,
            description_text, status, status_category, priority, assignee_account_id, assignee_name,
            reporter_name, story_points, due_date, parent_key, labels, components, created_at,
            updated_at, raw)
        VALUES ($1, $1, 'WAI', $2, $3, $4, $5, $6, $7, 'High', $8, $9, 'Maycon', $10, $11, $12,
                $13, $14, now(), now(), '{}')
        """,
        key,
        kw.get("type", "Tarefa"),
        kw.get("summary", f"Resumo {key}"),
        kw.get("description"),
        kw.get("description_text"),
        kw.get("status", "Em Desenvolvimento"),
        kw.get("category", "indeterminate"),
        kw.get("assignee", "acc-me"),
        kw.get("assignee_name", "Matheus Bacca"),
        kw.get("points"),
        kw.get("due"),
        kw.get("parent"),
        kw.get("labels", []),
        kw.get("components", []),
    )


def _link(
    id_, source, target, type_, direction, label, target_type="Tarefa", status=None, summary=None
):
    return (id_, source, target, type_, direction, label, summary, status, target_type)


@pytest.fixture
async def seeded(db_pool, credential_store):
    credential_store.set(
        "jira",
        {
            "site_url": SITE,
            "email": "d@w.com",
            "api_token": "t" * 24,
            "auth_mode": "classic",
            "account_id": "acc-me",
        },
    )
    await _issue(
        db_pool, "WAI-6900", type="Épico", summary="Integração de novos modelos", assignee=None
    )
    await _issue(
        db_pool,
        "WAI-124",
        summary="Implementar camada de integração com OpenAI",
        description=DESCRIPTION,
        description_text="Integrar com a OpenAI",
        points=8,
        parent="WAI-6900",
        labels=["backend"],
        components=["monitoria"],
        due=datetime(2026, 9, 19).date(),
    )
    await _issue(db_pool, "WAI-126", summary="Criar testes unitários", parent="WAI-6900")
    await _issue(
        db_pool,
        "WAI-130",
        type="Subtarefa",
        summary="Ajustar mock",
        parent="WAI-124",
        category="done",
        status="Concluído",
    )
    await db_pool.execute(
        "INSERT INTO jira_sprint (id, board_id, name, state, squad, in_scope) VALUES (3995, 144, 'Sprint 73 - Growth', 'active', 'Growth', true)"
    )
    await db_pool.execute("INSERT INTO jira_sprint_issue VALUES (3995, 'WAI-124')")
    await db_pool.executemany(
        """
        INSERT INTO jira_issue_link (id, source_key, target_key, link_type, direction, label,
            target_summary, target_status, target_type)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """,
        [
            _link("1", "WAI-124", "WAI-126", "Blocks", "outward", "blocks"),
            _link(
                "2",
                "WAI-124",
                "OUT-9",
                "Blocks",
                "inward",
                "is blocked by",
                status="To Do",
                summary="Liberar credencial",
            ),
            _link(
                "3",
                "WAI-124",
                "WAI-6000",
                "Relates",
                "outward",
                "relates to",
                target_type="Enhancements",
                summary="Enhancement",
            ),
            _link("4", "WAI-124", "WAI-127", "Cloners", "inward", "is cloned by", summary="Clone"),
        ],
    )
    await db_pool.execute(
        """
        INSERT INTO jira_comment (id, issue_key, author_name, body_adf, body_text, created_at)
        VALUES ('c1', 'WAI-124', 'Revisor', '{"type":"doc","content":[]}', 'Ajustar retry', now())
        """
    )
    await bitbucket_repo.upsert_pull_requests(
        db_pool,
        [
            {
                "repo_slug": "monitoria",
                "id": 412,
                "title": "WAI-124 integração",
                "description": None,
                "state": "OPEN",
                "draft": False,
                "author_name": "Matheus",
                "source_branch": "feature/WAI-124",
                "source_commit": "a",
                "destination_branch": "main",
                "participants": [
                    {"role": "REVIEWER", "approved": True, "state": "approved", "name": "Revisor"}
                ],
                "comment_count": 3,
                "task_count": 0,
                "build_status": "SUCCESSFUL",
                "issue_keys": ["WAI-124"],
                "url": "https://bitbucket.org/weonrepo/monitoria/pull-requests/412",
                "created_on": T0,
                "updated_on": T0,
            },
            {
                "repo_slug": "monitoria",
                "id": 413,
                "title": "testes",
                "description": None,
                "state": "MERGED",
                "draft": False,
                "author_name": "Matheus",
                "source_branch": "feature/WAI-126",
                "source_commit": "b",
                "destination_branch": "main",
                "participants": [],
                "comment_count": 0,
                "task_count": 0,
                "build_status": None,
                "issue_keys": ["WAI-126"],
                "url": None,
                "created_on": T0,
                "updated_on": T0,
            },
        ],
    )


async def test_detalhe_completo_da_tarefa(db_app, client, seeded):
    response = await client.get("/api/issues/WAI-124")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == "Implementar camada de integração com OpenAI"
    assert body["url"] == f"{SITE}/browse/WAI-124"
    assert body["description_adf"] == DESCRIPTION
    assert (body["story_points"], body["due_date"], body["priority"]) == (8.0, "2026-09-19", "High")
    assert (body["labels"], body["components"]) == (["backend"], ["monitoria"])
    assert body["is_mine"] is True
    assert body["parent"]["key"] == "WAI-6900" and body["parent"]["issue_type"] == "Épico"
    assert [c["key"] for c in body["children"]] == ["WAI-130"]
    assert body["sprints"] == [
        {"id": 3995, "name": "Sprint 73 - Growth", "state": "active", "squad": "Growth"}
    ]
    assert body["comments"][0]["body_text"] == "Ajustar retry"

    assert body["pull_requests"]["status"] == "aprovada"
    assert body["pull_requests"]["repos"][0]["pull_requests"][0]["id"] == 412


async def test_dependencias_agrupadas_com_status_de_pr(db_app, client, seeded):
    body = (await client.get("/api/issues/WAI-124")).json()

    assert [
        (g["kind"], g["label"], [i["key"] for i in g["items"]]) for g in body["dependencies"]
    ] == [
        ("blocked_by", "É bloqueada por", ["OUT-9"]),
        ("blocks", "Bloqueia", ["WAI-126"]),
        ("hierarchy", "relates to", ["WAI-6000"]),
        ("other", "is cloned by", ["WAI-127"]),
    ]
    blocks = body["blocks"][0]
    assert blocks["in_mirror"] is True
    assert blocks["summary"] == "Criar testes unitários"  # veio do espelho, não do snapshot
    assert blocks["pr"]["status"] == "mergeada"
    blocker = body["blocked_by"][0]
    assert (blocker["in_mirror"], blocker["status"], blocker["pr"]) == (False, "To Do", None)
    assert blocker["url"] == f"{SITE}/browse/OUT-9"


async def test_tarefa_fora_do_espelho_da_404(db_app, client, seeded):
    response = await client.get("/api/issues/WAI-1")

    assert response.status_code == 404
    assert "não está no espelho" in response.json()["detail"]


@respx.mock
async def test_historico_ao_vivo_do_jira(app, client, credential_store):
    credential_store.set(
        "jira",
        {"site_url": SITE, "email": "d@w.com", "api_token": "t" * 24, "auth_mode": "classic"},
    )
    respx.get(f"{SITE}/rest/api/3/issue/WAI-124/changelog").mock(
        return_value=httpx.Response(
            200,
            json={
                "startAt": 0,
                "total": 2,
                "isLast": True,
                "values": [
                    {
                        "id": "100",
                        "author": {"displayName": "Matheus Bacca"},
                        "created": "2026-09-10T10:00:00.000-0300",
                        "items": [
                            {
                                "field": "status",
                                "fromString": "Disponivel para análise",
                                "toString": "Em Desenvolvimento",
                            }
                        ],
                    },
                    {
                        "id": "101",
                        "author": {"displayName": "Maycon"},
                        "created": "2026-09-11T09:00:00.000-0300",
                        "items": [
                            {
                                "field": "description",
                                "fromString": "texto antigo enorme",
                                "toString": "texto novo",
                            },
                            {"field": "Story Points", "fromString": "5", "toString": "8"},
                            {"field": "summary", "fromString": None, "toString": "x" * 400},
                        ],
                    },
                ],
            },
        )
    )

    response = await client.get("/api/issues/WAI-124/changelog")

    assert response.status_code == 200
    body = response.json()
    assert [e["id"] for e in body["entries"]] == ["101", "100"]  # mais recente primeiro
    items = body["entries"][0]["items"]
    assert items[0] == {"field": "description", "from_value": None, "to_value": "(texto alterado)"}
    assert items[1] == {"field": "Story Points", "from_value": "5", "to_value": "8"}
    assert len(items[2]["to_value"]) == 280 and items[2]["to_value"].endswith("…")
    assert body["truncated"] is False


async def test_historico_sem_conexao_jira_da_409(client):
    response = await client.get("/api/issues/WAI-124/changelog")

    assert response.status_code == 409


@respx.mock
async def test_historico_longo_mantem_os_mais_recentes(client, credential_store, monkeypatch):
    from services import issue_service

    monkeypatch.setattr(issue_service, "CHANGELOG_LIMIT", 2)
    credential_store.set(
        "jira",
        {"site_url": SITE, "email": "d@w.com", "api_token": "t" * 24, "auth_mode": "classic"},
    )
    values = [
        {"id": str(i), "author": {}, "created": f"2026-09-0{i}T10:00:00.000+0000", "items": []}
        for i in range(1, 5)
    ]
    respx.get(f"{SITE}/rest/api/3/issue/WAI-1/changelog").mock(
        return_value=httpx.Response(200, json={"isLast": True, "total": 4, "values": values})
    )

    body = (await client.get("/api/issues/WAI-1/changelog")).json()

    assert [e["id"] for e in body["entries"]] == ["4", "3"]
    assert body["truncated"] is True


async def test_painel_segue_a_regra_de_bloqueio_do_card(db_app, client, db_pool, seeded):
    # OUT-9 está fora do espelho e sem PR: ainda segura a WAI-124.
    body = (await client.get("/api/issues/WAI-124")).json()
    assert body["blockers_without_pr"] == ["OUT-9"]

    # A WAI-124 (bloqueadora da WAI-126) já tem PR aprovada: não segura mais.
    await db_pool.execute(
        "INSERT INTO jira_issue_link (id, source_key, target_key, link_type, direction, label) "
        "VALUES ('9', 'WAI-126', 'WAI-124', 'Blocks', 'inward', 'is blocked by')"
    )
    body = (await client.get("/api/issues/WAI-126")).json()
    assert [b["key"] for b in body["blocked_by"]] == ["WAI-124"]
    assert body["blockers_without_pr"] == []


async def test_bloqueador_concluido_nao_segura_o_painel(db_app, client, db_pool, seeded):
    await db_pool.execute(
        "UPDATE jira_issue_link SET target_status = 'Concluído' WHERE target_key = 'OUT-9'"
    )
    await db_pool.execute(
        "INSERT INTO jira_issue (key, id, project_key, issue_type, summary, status, "
        "status_category, created_at, updated_at, raw) VALUES ('OUT-9', 'OUT-9', 'OUT', "
        "'Tarefa', 'Liberar credencial', 'Concluído', 'done', now(), now(), '{}')"
    )

    body = (await client.get("/api/issues/WAI-124")).json()
    assert body["blockers_without_pr"] == []


async def test_painel_traz_a_etapa_do_status(db_app, client, seeded):
    body = (await client.get("/api/issues/WAI-124")).json()

    assert body["stage"]["id"] == "desenvolvimento"


async def test_lista_de_tarefas_para_vincular_casa_qualquer_campo(db_app, client, seeded):
    async def keys(q):
        response = await client.get("/api/issues", params={"q": q})
        assert response.status_code == 200
        return [i["key"] for i in response.json()]

    assert await keys("integracao openai") == ["WAI-124"]  # sem acento, termos soltos
    assert await keys("WAI-126") == ["WAI-126"]
    assert await keys("monitoria") == ["WAI-124"]  # componente
    assert await keys("subtarefa") == ["WAI-130"]  # tipo
    assert await keys("integração 124") == ["WAI-124"]  # título e número juntos
    assert await keys("50%") == []  # curinga do LIKE é texto


async def test_lista_sem_termo_traz_concluidas_por_ultimo(db_app, client, seeded):
    body = (await client.get("/api/issues")).json()

    assert body[-1]["key"] == "WAI-130"
    assert {"key", "summary", "status", "issue_type", "is_mine"} <= set(body[0])


async def test_lista_so_minhas_para_mencao(db_app, client, seeded):
    body = (await client.get("/api/issues", params={"mine": "true"})).json()

    assert "WAI-6900" not in [i["key"] for i in body]  # épico sem responsável
    assert all(i["is_mine"] for i in body)
