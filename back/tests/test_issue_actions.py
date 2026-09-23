"""Ações no Jira pelo SprintAI: linha de fluxo, transição de status e Story Points."""

from datetime import UTC, datetime

import httpx
import pytest
import respx

from integrations.jira_client import JiraField, JiraFieldMap
from realtime.bus import ISSUE_CHANGED, get_bus
from services.issue_actions import (
    build_flow,
    editable_points_field,
    jira_number,
    requires_fields,
    workflow_statuses,
)
from services.progress.stages import ProgressStages

SITE = "https://weon.atlassian.net"
UPDATED = datetime(2026, 9, 12, 10, 0, tzinfo=UTC)
STAGES = ProgressStages()


def status(name, category="indeterminate", sid=None):
    return {"id": sid or name, "name": name, "statusCategory": {"key": category}}


def transition(tid, target, category="indeterminate", fields=None, name=None):
    return {
        "id": str(tid),
        "name": name or f"Ir para {target}",
        "to": status(target, category),
        "fields": fields or {},
    }


WORKFLOW = [
    status("Concluído", "done"),
    status("Em Review"),
    status("Disponivel para análise", "new"),
    status("DISPONIVEL PARA REVIEW", "new"),
    status("Em Desenvolvimento"),
    status("DISPONIVEL PARA TESTES", "new"),
]


# --- Linha de fluxo --------------------------------------------------------------------


def test_linha_segue_as_etapas_do_progresso_e_marca_o_atual():
    steps = build_flow(
        current=status("Em Review"),
        transitions=[
            transition(31, "DISPONIVEL PARA TESTES", "new"),
            transition(11, "Em Desenvolvimento"),
        ],
        statuses=WORKFLOW,
        stages=STAGES,
    )

    assert [s.status for s in steps] == [
        "Disponivel para análise",
        "Em Desenvolvimento",
        "DISPONIVEL PARA REVIEW",
        "Em Review",
        "DISPONIVEL PARA TESTES",
        "Concluído",
    ]
    by_name = {s.status: s for s in steps}
    assert by_name["Em Review"].current and by_name["Em Review"].transition_id is None
    assert by_name["DISPONIVEL PARA TESTES"].transition_id == "31"
    assert by_name["Em Desenvolvimento"].stage.id == "desenvolvimento"
    # Sem transição a partir do atual: aparece, mas não dá para ir.
    assert by_name["Concluído"].transition_id is None and not by_name["Concluído"].current


def test_sem_workflow_do_tipo_a_linha_fica_com_atual_e_transicoes():
    steps = build_flow(
        current=status("Em Review"),
        transitions=[transition(31, "DISPONIVEL PARA TESTES", "new")],
        statuses=[],
        stages=STAGES,
    )

    assert [s.status for s in steps] == ["Em Review", "DISPONIVEL PARA TESTES"]


def test_transicao_para_o_proprio_status_e_repetida_nao_viram_passo():
    steps = build_flow(
        current=status("Em Review"),
        transitions=[
            transition(5, "Em Review", name="Reenviar"),
            transition(31, "DISPONIVEL PARA TESTES", "new", name="Aprovar"),
            transition(32, "DISPONIVEL PARA TESTES", "new", name="Aprovar de novo"),
        ],
        statuses=[],
        stages=STAGES,
    )

    assert [(s.status, s.transition_id) for s in steps] == [
        ("Em Review", None),
        ("DISPONIVEL PARA TESTES", "31"),
    ]


def test_status_sem_etapa_ficam_nas_pontas_pela_categoria():
    steps = build_flow(
        current=status("Em Desenvolvimento"),
        transitions=[
            transition(1, "Cancelado", "done"),
            transition(2, "Triagem", "new"),
            transition(3, "Bloqueado"),
        ],
        statuses=[],
        stages=STAGES,
    )

    assert [s.status for s in steps] == ["Triagem", "Em Desenvolvimento", "Bloqueado", "Cancelado"]


def test_transicao_com_campo_obrigatorio_sem_padrao_fica_para_o_jira():
    comment = {"comment": {"required": True, "hasDefaultValue": False, "name": "Comentário"}}
    resolution = {"resolution": {"required": True, "hasDefaultValue": True}}

    assert requires_fields(transition(1, "Concluído", "done", fields=comment))
    assert not requires_fields(transition(2, "Concluído", "done", fields=resolution))
    assert not requires_fields(transition(3, "Concluído", "done"))


def test_workflow_do_tipo_casa_sem_caixa_nem_acento():
    project = [
        {"name": "Épico", "statuses": [status("A fazer", "new")]},
        {"name": "Tarefa", "statuses": WORKFLOW},
    ]

    assert workflow_statuses(project, "TAREFA") == WORKFLOW
    assert workflow_statuses(project, "Subtarefa") == []
    assert workflow_statuses(project, None) == []


def test_story_points_usa_o_primeiro_campo_que_a_tela_aceita():
    classic = JiraField("customfield_10026", "Story Points")
    estimate = JiraField("customfield_10016", "Story point estimate")
    fields = JiraFieldMap(
        sprint=None, story_points=classic, story_point_candidates=(classic, estimate)
    )

    assert editable_points_field(fields, {"fields": {"customfield_10016": {}}}) == estimate
    assert editable_points_field(fields, {"fields": {"customfield_10026": {}}}) == classic
    assert editable_points_field(fields, {"fields": {"summary": {}}}) is None


def test_numero_inteiro_vai_sem_casa_decimal():
    assert jira_number(5.0) == 5 and isinstance(jira_number(5.0), int)
    assert jira_number(0.5) == 0.5
    assert jira_number(None) is None


# --- API -------------------------------------------------------------------------------


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
    await db_pool.execute(
        """
        INSERT INTO jira_issue (key, id, project_key, issue_type, summary, status,
            status_category, assignee_account_id, assignee_name, story_points, created_at,
            updated_at, raw)
        VALUES ('WAI-124', '10124', 'WAI', 'Tarefa', 'Integrar OpenAI', 'Em Review',
            'indeterminate', 'acc-me', 'Matheus Bacca', 3, $1, $1, '{}')
        """,
        UPDATED,
    )
    # Foto do card: o responsável mudou e o dev ainda não viu.
    await db_pool.execute(
        """
        INSERT INTO issue_seen (issue_key, snapshot)
        VALUES ('WAI-124', '{"status": "Em Review", "story_points": 3.0, "assignee": "Outro"}')
        """
    )
    return db_pool


def _mock_flow(current="Em Review", transitions=None):
    respx.get(f"{SITE}/rest/api/3/issue/WAI-124").mock(
        return_value=httpx.Response(
            200,
            json={
                "key": "WAI-124",
                "fields": {"status": status(current), "issuetype": {"name": "Tarefa"}},
            },
        )
    )
    return respx.get(f"{SITE}/rest/api/3/issue/WAI-124/transitions").mock(
        return_value=httpx.Response(
            200,
            json={
                "transitions": transitions
                if transitions is not None
                else [
                    transition(31, "DISPONIVEL PARA TESTES", "new"),
                    transition(11, "Em Desenvolvimento"),
                ]
            },
        )
    )


@respx.mock
async def test_fluxo_traz_a_linha_do_workflow_com_o_status_do_jira(db_app, client, seeded):
    _mock_flow(current="DISPONIVEL PARA REVIEW")
    respx.get(f"{SITE}/rest/api/3/project/WAI/statuses").mock(
        return_value=httpx.Response(200, json=[{"name": "Tarefa", "statuses": WORKFLOW}])
    )

    response = await client.get("/api/issues/WAI-124/transitions")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "DISPONIVEL PARA REVIEW"
    # O espelho ainda não sabia: a tela avisa.
    assert body["mirror_status"] == "Em Review"
    assert body["url"] == f"{SITE}/browse/WAI-124"
    assert [s["status"] for s in body["steps"]][:3] == [
        "Disponivel para análise",
        "Em Desenvolvimento",
        "DISPONIVEL PARA REVIEW",
    ]
    current = next(s for s in body["steps"] if s["current"])
    assert current["status"] == "DISPONIVEL PARA REVIEW"
    assert current["stage"]["id"] == "review"


@respx.mock
async def test_fluxo_sem_os_status_do_projeto_ainda_mostra_as_transicoes(
    db_app, client, seeded
):
    _mock_flow()
    respx.get(f"{SITE}/rest/api/3/project/WAI/statuses").mock(return_value=httpx.Response(403))

    body = (await client.get("/api/issues/WAI-124/transitions")).json()

    assert body["mirror_status"] is None
    assert [s["status"] for s in body["steps"]] == [
        "Em Desenvolvimento",
        "Em Review",
        "DISPONIVEL PARA TESTES",
    ]


async def test_fluxo_de_tarefa_fora_do_espelho_da_404(db_app, client, seeded):
    response = await client.get("/api/issues/WAI-999/transitions")

    assert response.status_code == 404


@respx.mock
async def test_transicao_move_no_jira_e_grava_no_espelho(db_app, client, seeded):
    _mock_flow()
    move = respx.post(f"{SITE}/rest/api/3/issue/WAI-124/transitions").mock(
        return_value=httpx.Response(204)
    )

    async with get_bus().subscribe() as queue:
        response = await client.post(
            "/api/issues/WAI-124/transitions", json={"transition_id": "31"}
        )
        event = queue.get_nowait()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "DISPONIVEL PARA TESTES"
    assert body["status_category"] == "new"
    assert body["stage"]["id"] == "testes"
    assert move.calls.last.request.read() == b'{"transition":{"id":"31"}}'
    assert event.kind == ISSUE_CHANGED
    assert event.payload == {"key": "WAI-124", "field": "status", "write_id": body["write_id"]}

    row = await seeded.fetchrow(
        "SELECT status, status_category, updated_at FROM jira_issue WHERE key = 'WAI-124'"
    )
    assert (row["status"], row["status_category"]) == ("DISPONIVEL PARA TESTES", "new")
    # `updated_at` antigo: é o que faz o próximo sync ler o changelog e gravar a história.
    assert row["updated_at"] == UPDATED

    snapshot = await seeded.fetchval("SELECT snapshot FROM issue_seen WHERE issue_key = 'WAI-124'")
    # A mudança do próprio dev não acende a bolinha; a do responsável continua pendente.
    assert snapshot == {"status": "DISPONIVEL PARA TESTES", "story_points": 3.0, "assignee": "Outro"}


@respx.mock
async def test_transicao_que_o_jira_nao_oferece_mais_da_409_sem_escrever(db_app, client, seeded):
    _mock_flow()
    move = respx.post(f"{SITE}/rest/api/3/issue/WAI-124/transitions")

    response = await client.post("/api/issues/WAI-124/transitions", json={"transition_id": "99"})

    assert response.status_code == 409
    assert "não oferece mais" in response.json()["detail"]
    assert not move.called
    assert await seeded.fetchval("SELECT status FROM jira_issue WHERE key = 'WAI-124'") == (
        "Em Review"
    )


@respx.mock
async def test_transicao_com_campo_obrigatorio_da_409(db_app, client, seeded):
    required = {"comment": {"required": True, "hasDefaultValue": False}}
    _mock_flow(transitions=[transition(41, "Concluído", "done", fields=required, name="Fechar")])
    move = respx.post(f"{SITE}/rest/api/3/issue/WAI-124/transitions")

    response = await client.post("/api/issues/WAI-124/transitions", json={"transition_id": "41"})

    assert response.status_code == 409
    assert "pede campos no Jira" in response.json()["detail"]
    assert not move.called


@respx.mock
async def test_transicao_sem_permissao_explica_o_escopo(db_app, client, seeded):
    _mock_flow()
    respx.post(f"{SITE}/rest/api/3/issue/WAI-124/transitions").mock(
        return_value=httpx.Response(403)
    )

    response = await client.post("/api/issues/WAI-124/transitions", json={"transition_id": "31"})

    assert response.status_code == 502
    assert "write:jira-work" in response.json()["detail"]
    assert await seeded.fetchval("SELECT status FROM jira_issue WHERE key = 'WAI-124'") == (
        "Em Review"
    )


async def test_transicao_com_id_invalido_da_422(db_app, client, seeded):
    response = await client.post(
        "/api/issues/WAI-124/transitions", json={"transition_id": "31; DROP"}
    )

    assert response.status_code == 422
    assert "DROP" not in response.text


def _mock_points_meta(editable=("customfield_10026",)):
    respx.get(f"{SITE}/rest/api/3/field").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "customfield_10026",
                    "name": "Story Points",
                    "custom": True,
                    "schema": {"type": "number"},
                }
            ],
        )
    )
    respx.get(f"{SITE}/rest/api/3/issue/WAI-124/editmeta").mock(
        return_value=httpx.Response(200, json={"fields": {fid: {} for fid in editable}})
    )


@respx.mock
async def test_story_points_gravam_no_jira_e_no_espelho(db_app, client, seeded):
    _mock_points_meta()
    edit = respx.put(f"{SITE}/rest/api/3/issue/WAI-124").mock(return_value=httpx.Response(204))

    response = await client.put("/api/issues/WAI-124/story-points", json={"story_points": 5})

    assert response.status_code == 200
    assert response.json()["story_points"] == 5
    assert edit.calls.last.request.read() == b'{"fields":{"customfield_10026":5}}'
    assert await seeded.fetchval("SELECT story_points FROM jira_issue WHERE key = 'WAI-124'") == 5
    snapshot = await seeded.fetchval("SELECT snapshot FROM issue_seen WHERE issue_key = 'WAI-124'")
    assert snapshot["story_points"] == 5.0 and snapshot["assignee"] == "Outro"


@respx.mock
async def test_story_points_nulos_apagam_o_valor(db_app, client, seeded):
    _mock_points_meta()
    edit = respx.put(f"{SITE}/rest/api/3/issue/WAI-124").mock(return_value=httpx.Response(204))

    response = await client.put("/api/issues/WAI-124/story-points", json={"story_points": None})

    assert response.status_code == 200
    assert response.json()["story_points"] is None
    assert edit.calls.last.request.read() == b'{"fields":{"customfield_10026":null}}'


@respx.mock
async def test_story_points_fora_da_tela_de_edicao_da_409(db_app, client, seeded):
    _mock_points_meta(editable=("summary",))
    edit = respx.put(f"{SITE}/rest/api/3/issue/WAI-124")

    response = await client.put("/api/issues/WAI-124/story-points", json={"story_points": 5})

    assert response.status_code == 409
    assert "tela de edição" in response.json()["detail"]
    assert not edit.called


async def test_story_points_negativos_da_422_sem_ecoar(db_app, client, seeded):
    response = await client.put("/api/issues/WAI-124/story-points", json={"story_points": -3})

    assert response.status_code == 422
    assert "-3" not in response.text


async def test_escrever_sem_o_header_da_guarda_e_recusado(db_app, raw_client, seeded):
    response = await raw_client.put("/api/issues/WAI-124/story-points", json={"story_points": 5})

    assert response.status_code == 403
