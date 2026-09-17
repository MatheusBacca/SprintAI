from datetime import UTC, datetime, timedelta

import pytest

SITE = "https://weon.atlassian.net"


@pytest.fixture
async def api(db_app, client, credential_store, db_pool):
    credential_store.set("jira", {"site_url": SITE, "email": "d@w.com", "api_token": "t" * 24})
    await db_pool.execute(
        """
        INSERT INTO jira_issue (key, id, project_key, issue_type, summary, status, status_category,
                                created_at, updated_at, raw)
        VALUES ('WAI-8295', '1', 'WAI', 'Tarefa', 'Console do QualificAI', 'Concluído', 'done',
                now(), now(), '{}')
        """
    )
    return client


async def create(client, **body):
    response = await client.post("/api/notes", json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def test_cria_lembrete_normalizando_tags_e_chaves(api):
    note = await create(
        api,
        title="  Integração OpenAI  ",
        body="Lembrar do retry exponencial",
        color="blue",
        tags=["#Backend", "retry", "backend", "boas praticas"],
        issue_keys=["wai-8295", "WAI-9999", "WAI-8295"],
    )

    assert note["title"] == "Integração OpenAI"
    assert note["tags"] == ["backend", "retry", "boas-praticas"]
    assert [(i["key"], i["in_mirror"]) for i in note["issues"]] == [
        ("WAI-8295", True),
        ("WAI-9999", False),
    ]
    assert note["issues"][0]["summary"] == "Console do QualificAI"
    assert note["issues"][0]["url"] == f"{SITE}/browse/WAI-8295"
    assert (note["pinned"], note["archived"], note["reminder_due"]) == (False, False, False)


@pytest.mark.parametrize(
    ("body", "fragment"),
    [
        ({"title": "", "body": "   "}, "título ou um texto"),
        ({"title": "x", "color": "orange"}, "color"),
        ({"title": "x", "issue_keys": ["nao-e-chave"]}, "Chave de tarefa inválida"),
        ({"title": "x", "remind_at": "2026-09-15T09:00:00"}, "fuso"),
        ({"title": "x", "tags": [f"t{i}" for i in range(16)]}, "15 tags"),
    ],
)
async def test_validacoes(api, body, fragment):
    response = await api.post("/api/notes", json=body)

    assert response.status_code == 422
    assert fragment in response.text


async def test_busca_sem_acento_por_trecho_por_tag_e_por_chave(api):
    a = await create(
        api, title="Integração OpenAI", body="retry exponencial no cliente", tags=["backend"]
    )
    b = await create(
        api, title="Reunião de planejamento", body="levar números da sprint", tags=["rituais"]
    )
    c = await create(api, title="Anotação solta", body="ver isso depois", issue_keys=["WAI-8295"])

    async def ids(**params):
        response = await api.get("/api/notes", params=params)
        return [n["id"] for n in response.json()["items"]]

    assert await ids(q="integracao") == [a["id"]]  # sem acento
    assert await ids(q="exponen") == [a["id"]]  # trecho parcial
    assert await ids(q="REUNIAO") == [b["id"]]
    assert await ids(q="rituais") == [b["id"]]  # tag
    assert await ids(q="wai-8295") == [c["id"]]  # chave vinculada
    assert await ids(tag="backend") == [a["id"]]
    assert await ids(issue_key="WAI-8295") == [c["id"]]
    assert await ids(q="100%_nada") == []  # curingas do LIKE escapados


async def test_titulo_casando_vem_antes_de_corpo_e_fixados_primeiro(api):
    corpo = await create(api, title="Outro assunto", body="falar sobre deploy")
    titulo = await create(api, title="Deploy de terça", body="checklist")
    fixado = await create(api, title="Fixado qualquer", body="sem relação", pinned=True)

    items = (await api.get("/api/notes", params={"q": "deploy"})).json()["items"]
    assert [n["id"] for n in items] == [titulo["id"], corpo["id"]]

    all_items = (await api.get("/api/notes")).json()["items"]
    assert all_items[0]["id"] == fixado["id"]


async def test_atualizacao_parcial_troca_vinculos_e_arquiva(api):
    note = await create(api, title="Rascunho", issue_keys=["WAI-1", "WAI-2"])

    response = await api.patch(
        f"/api/notes/{note['id']}", json={"color": "pink", "issue_keys": ["WAI-2", "WAI-3"]}
    )

    body = response.json()
    assert body["title"] == "Rascunho"  # não enviado, não muda
    assert body["color"] == "pink"
    assert [i["key"] for i in body["issues"]] == ["WAI-2", "WAI-3"]

    await api.patch(f"/api/notes/{note['id']}", json={"archived": True})
    assert (await api.get("/api/notes")).json()["total"] == 0
    assert (await api.get("/api/notes", params={"archived": "true"})).json()["total"] == 1
    assert (await api.get("/api/notes", params={"include_archived": "true"})).json()["total"] == 1


async def test_nao_deixa_esvaziar_titulo_e_texto(api):
    note = await create(api, title="Só título")

    response = await api.patch(f"/api/notes/{note['id']}", json={"title": ""})

    assert response.status_code == 422
    assert (await api.get(f"/api/notes/{note['id']}")).json()["title"] == "Só título"


async def test_lembrete_vencido_aparece_e_some_depois_de_visto(api):
    past = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    vencido = await create(api, title="Revisar PR do Rafael", remind_at=past)
    await create(api, title="Amanhã", remind_at=future)

    due = (await api.get("/api/notes/reminders/due")).json()
    assert [n["id"] for n in due] == [vencido["id"]]
    assert due[0]["reminder_due"] is True

    acked = (await api.post(f"/api/notes/{vencido['id']}/reminder/ack")).json()
    assert acked["reminded_at"] is not None and acked["reminder_due"] is False
    assert (await api.get("/api/notes/reminders/due")).json() == []

    upcoming = (await api.get("/api/notes", params={"due": "upcoming"})).json()["items"]
    assert [n["title"] for n in upcoming] == ["Amanhã"]


async def test_adiar_e_remarcar_rearmam_a_notificacao(api):
    past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    note = await create(api, title="Daily", remind_at=past)
    await api.post(f"/api/notes/{note['id']}/reminder/ack")

    snoozed = (
        await api.post(f"/api/notes/{note['id']}/reminder/snooze", json={"minutes": 10})
    ).json()
    assert snoozed["reminded_at"] is None
    assert datetime.fromisoformat(snoozed["remind_at"]) > datetime.now(UTC) + timedelta(minutes=9)

    await api.post(f"/api/notes/{note['id']}/reminder/ack")
    moved = (await api.patch(f"/api/notes/{note['id']}", json={"remind_at": past})).json()
    assert moved["reminder_due"] is True


async def test_tags_com_contagem_e_exclusao(api):
    a = await create(api, title="a", tags=["backend", "retry"])
    await create(api, title="b", tags=["backend"])

    assert (await api.get("/api/notes/tags")).json() == [
        {"tag": "backend", "count": 2},
        {"tag": "retry", "count": 1},
    ]

    assert (await api.delete(f"/api/notes/{a['id']}")).status_code == 204
    assert (await api.get(f"/api/notes/{a['id']}")).status_code == 404
    assert (await api.delete(f"/api/notes/{a['id']}")).status_code == 404


async def test_lembrete_guarda_repositorios_citados_e_busca_por_eles(api):
    note = await create(api, title="Deploy", repos=["@Organia-Configs", "monitoria", "monitoria"])
    assert note["repos"] == ["organia-configs", "monitoria"]

    found = (await api.get("/api/notes", params={"q": "organia-conf"})).json()
    assert [n["id"] for n in found["items"]] == [note["id"]]

    patched = await api.patch(f"/api/notes/{note['id']}", json={"repos": []})
    assert patched.json()["repos"] == []


async def test_repositorio_invalido_e_recusado(api):
    response = await api.post("/api/notes", json={"title": "x", "repos": ["não vale"]})
    assert response.status_code == 422
