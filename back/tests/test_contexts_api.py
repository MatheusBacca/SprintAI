import pytest

SITE = "https://weon.atlassian.net"


async def _issue(pool, key, parent=None, summary=None):
    await pool.execute(
        """
        INSERT INTO jira_issue (key, id, project_key, issue_type, summary, status, status_category,
                                parent_key, created_at, updated_at, raw)
        VALUES ($1, $1, 'WAI', 'Tarefa', $2, 'Em Desenvolvimento', 'indeterminate', $3,
                now(), now(), '{}')
        """,
        key,
        summary or f"Resumo {key}",
        parent,
    )


@pytest.fixture
async def api(db_app, client, credential_store, db_pool):
    credential_store.set("jira", {"site_url": SITE, "email": "d@w.com", "api_token": "t" * 24})
    await _issue(db_pool, "WAI-100", summary="Épico de integrações")
    await _issue(db_pool, "WAI-1", parent="WAI-100", summary="Retry no client")
    await _issue(db_pool, "WAI-2", parent="WAI-100", summary="Fila de reprocessamento")
    await _issue(db_pool, "WAI-3", summary="Outra tarefa")
    await db_pool.execute(
        """
        INSERT INTO jira_issue_link (id, source_key, target_key, link_type, direction, label)
        VALUES ('l1', 'WAI-3', 'WAI-1', 'Relates', 'outward', 'relates to')
        """
    )
    return client


async def create(client, **body):
    response = await client.post("/api/contexts", json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def test_cria_com_relacoes_normalizadas_e_hidrata_tarefas(api):
    ctx = await create(
        api,
        issue_key="wai-1",
        kind="finding",
        title="  Retry sem jitter  ",
        body="O client repete sem jitter e derruba o provedor",
        tags=["Backend", "retry"],
        relations=[
            {"issue_key": "WAI-2"},
            {"issue_key": "wai-2", "relation": "continues"},
            {"issue_key": "WAI-1"},  # a própria tarefa é ignorada
            {"issue_key": "WAI-9999"},
        ],
    )

    assert ctx["title"] == "Retry sem jitter"
    assert ctx["issue"]["key"] == "WAI-1"
    assert ctx["issue"]["summary"] == "Retry no client"
    assert ctx["issue"]["url"] == f"{SITE}/browse/WAI-1"
    assert ctx["tags"] == ["backend", "retry"]
    assert [(r["key"], r["relation"], r["in_mirror"]) for r in ctx["relations"]] == [
        ("WAI-2", "continues", True),
        ("WAI-9999", "relates", False),
    ]
    assert (ctx["status"], ctx["source"], ctx["resolved_in"]) == ("open", "manual", None)


@pytest.mark.parametrize(
    ("body", "fragment"),
    [
        ({"issue_key": "WAI-1", "kind": "finding", "title": " ", "body": ""}, "título ou um texto"),
        ({"issue_key": "nao-e-chave", "kind": "finding", "title": "x"}, "Chave de tarefa"),
        ({"issue_key": "WAI-1", "kind": "bug", "title": "x"}, "kind"),
        (
            {
                "issue_key": "WAI-1",
                "kind": "fix",
                "title": "x",
                "tags": [f"t{i}" for i in range(16)],
            },
            "15 tags por contexto",
        ),
    ],
)
async def test_validacoes(api, body, fragment):
    response = await api.post("/api/contexts", json=body)
    assert response.status_code == 422
    assert fragment in response.text


async def test_resolve_ponto_em_aberto_numa_tarefa_futura_e_reabre(api):
    point = await create(
        api, issue_key="WAI-1", kind="open_point", title="Definir limite de retries"
    )

    response = await api.post(
        f"/api/contexts/{point['id']}/resolve",
        json={"issue_key": "wai-2", "resolution": "  Limite de 5 com backoff  "},
    )
    assert response.status_code == 200, response.text
    resolved = response.json()
    assert resolved["status"] == "resolved"
    assert resolved["resolved_in"]["key"] == "WAI-2"
    assert resolved["resolution"] == "Limite de 5 com backoff"
    assert resolved["resolved_at"]
    assert [(r["key"], r["relation"]) for r in resolved["relations"]] == [("WAI-2", "resolves")]

    # Editar relações manuais não apaga a relação da resolução.
    response = await api.patch(
        f"/api/contexts/{point['id']}", json={"relations": [{"issue_key": "WAI-3"}]}
    )
    assert sorted((r["key"], r["relation"]) for r in response.json()["relations"]) == [
        ("WAI-2", "resolves"),
        ("WAI-3", "relates"),
    ]

    # Mudar o tipo de um ponto resolvido exige reabrir antes.
    response = await api.patch(f"/api/contexts/{point['id']}", json={"kind": "decision"})
    assert response.status_code == 422
    assert "Reabra" in response.text

    reopened = (await api.post(f"/api/contexts/{point['id']}/reopen")).json()
    assert (reopened["status"], reopened["resolved_in"], reopened["resolution"]) == (
        "open",
        None,
        "",
    )
    assert [r["key"] for r in reopened["relations"]] == ["WAI-3"]


async def test_so_ponto_em_aberto_e_resolvido(api):
    finding = await create(api, issue_key="WAI-1", kind="finding", title="Achado")
    response = await api.post(f"/api/contexts/{finding['id']}/resolve", json={"issue_key": "WAI-2"})
    assert response.status_code == 422
    assert "Só pontos em aberto" in response.text
    assert (await api.post("/api/contexts/999/reopen")).status_code == 404


async def test_aba_da_tarefa_proprios_citados_e_pontos_vizinhos(api):
    own = await create(api, issue_key="WAI-1", kind="decision", title="Usar backoff exponencial")
    sibling_open = await create(api, issue_key="WAI-2", kind="open_point", title="Métrica de fila")
    linked_open = await create(api, issue_key="WAI-3", kind="open_point", title="Alerta no Slack")
    citing = await create(
        api,
        issue_key="WAI-3",
        kind="finding",
        title="Mesmo erro visto aqui",
        relations=[{"issue_key": "WAI-1"}],
    )
    await create(api, issue_key="WAI-2", kind="finding", title="Achado do irmão, não é ponto")
    resolved_here = await create(api, issue_key="WAI-2", kind="open_point", title="Resolvido no 1")
    await api.post(f"/api/contexts/{resolved_here['id']}/resolve", json={"issue_key": "WAI-1"})

    data = (await api.get("/api/issues/WAI-1/contexts")).json()

    assert [c["id"] for c in data["own"]] == [own["id"]]
    assert {c["id"] for c in data["linked"]} == {citing["id"], resolved_here["id"]}
    # Irmão (mesmo pai) e tarefa com link do Jira; o resolvido e o que já cita ficam fora.
    assert {c["id"] for c in data["nearby_open"]} == {sibling_open["id"], linked_open["id"]}


async def test_busca_filtros_ordem_e_contagem(api):
    await create(api, issue_key="WAI-1", kind="finding", title="Integração OpenAI", body="timeout")
    point = await create(
        api, issue_key="WAI-2", kind="open_point", title="Ponto", body="integração"
    )
    await create(api, issue_key="WAI-3", kind="fix", title="Corrigido", tags=["infra"])

    items = (await api.get("/api/contexts")).json()["items"]
    assert items[0]["id"] == point["id"]  # ponto em aberto primeiro

    found = (await api.get("/api/contexts", params={"q": "integracao"})).json()
    assert [c["title"] for c in found["items"]] == ["Integração OpenAI", "Ponto"]  # título pesa
    assert (await api.get("/api/contexts", params={"q": "WAI-3"})).json()["total"] == 1
    assert (await api.get("/api/contexts", params={"q": "exponen"})).json()["total"] == 0
    assert (await api.get("/api/contexts", params={"q": "timeo"})).json()["total"] == 1

    only = await api.get(
        "/api/contexts", params=[("kind", "open_point"), ("kind", "fix"), ("status", "open")]
    )
    assert only.json()["total"] == 2
    assert (await api.get("/api/contexts", params={"tag": "INFRA"})).json()["total"] == 1

    counts = (await api.get("/api/contexts/counts")).json()
    assert counts == {"open_points": 1, "by_kind": {"finding": 1, "open_point": 1, "fix": 1}}


async def test_edita_e_exclui(api):
    ctx = await create(api, issue_key="WAI-1", kind="finding", title="Antes")
    response = await api.patch(
        f"/api/contexts/{ctx['id']}", json={"title": "Depois", "issue_key": "WAI-2", "kind": "fix"}
    )
    assert response.status_code == 200
    assert (response.json()["title"], response.json()["issue"]["key"]) == ("Depois", "WAI-2")

    response = await api.patch(f"/api/contexts/{ctx['id']}", json={"title": "", "body": ""})
    assert response.status_code == 422

    assert (await api.delete(f"/api/contexts/{ctx['id']}")).status_code == 204
    assert (await api.get(f"/api/contexts/{ctx['id']}")).status_code == 404
    assert (await api.delete(f"/api/contexts/{ctx['id']}")).status_code == 404
