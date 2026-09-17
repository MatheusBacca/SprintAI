"""B9 — etapas de progresso, agregação da sprint e a tela de Configurações."""

from datetime import date

import pytest

from services import progress
from services.progress.stages import DEFAULT_STAGES, ProgressStages

STAGES = ProgressStages()
SOURCES = progress.sources_for(STAGES)


def _issue(status, category, points=None, issue_type="Tarefa"):
    return {
        "status": status,
        "status_category": category,
        "story_points": points,
        "issue_type": issue_type,
    }


@pytest.mark.parametrize(
    ("status", "category", "expected", "stage"),
    [
        ("Disponivel para análise", "new", 0.0, "analise"),
        ("Em Desenvolvimento", "indeterminate", 0.4, "desenvolvimento"),
        # A categoria mente aqui: REVIEW e TESTES chegam como `new` do Jira.
        ("DISPONIVEL PARA REVIEW", "new", 0.7, "review"),
        ("Em Review", "indeterminate", 0.7, "review"),
        ("DISPONIVEL PARA TESTES", "new", 0.85, "testes"),
        # AJUSTE é código de volta na mão do dev, não review.
        ("AJUSTE", "new", 0.4, "desenvolvimento"),
        ("Concluído", "done", 1.0, "concluido"),
        # Sem acento e em caixa alta é o mesmo status.
        ("CONCLUIDO", "done", 1.0, "concluido"),
        # Status que ninguém mapeou cai pela categoria, sem etapa nomeada.
        ("Aguardando cliente", "indeterminate", 0.5, None),
        ("Status novo em folha", "new", 0.0, None),
    ],
)
def test_etapa_de_cada_status(status, category, expected, stage):
    value, found = STAGES.weight_of(status, category)
    assert value == expected
    assert (found.id if found else None) == stage


def test_progresso_ponderado_por_story_points():
    issues = [
        _issue("DISPONIVEL PARA REVIEW", "new", 5),
        _issue("Concluído", "done", 3),
        _issue("Disponivel para análise", "new"),  # sem SP conta 1
    ]
    real, _, points, done = progress.aggregate(issues, SOURCES)

    assert points == 9.0
    assert done == 1
    assert round(real, 4) == round((0.7 * 5 + 1.0 * 3) / 9, 4)


def test_sem_tarefa_o_progresso_e_zero_e_nao_estoura():
    real, by_stage, points, done = progress.aggregate([], SOURCES)
    assert (real, by_stage, points, done) == (0.0, {}, 0.0, 0)


def test_dias_uteis_ignoram_fim_de_semana():
    # Seg 14/09 a sex 18/09 = 5 dias úteis; a semana inteira até domingo também.
    assert progress.business_days(date(2026, 9, 14), date(2026, 9, 18)) == 5
    assert progress.business_days(date(2026, 9, 14), date(2026, 9, 20)) == 5
    assert progress.business_days(date(2026, 9, 18), date(2026, 9, 14)) == 0


def test_esperado_acompanha_o_tempo_util_decorrido():
    start, end = date(2026, 9, 14), date(2026, 9, 18)
    assert progress.expected_ratio(start, end, date(2026, 9, 13)) == 0.0
    assert progress.expected_ratio(start, end, date(2026, 9, 15)) == 2 / 5
    assert progress.expected_ratio(start, end, date(2026, 9, 21)) == 1.0
    assert progress.expected_ratio(None, end, date(2026, 9, 15)) is None


def test_sprint_ativa_e_vencida_tem_esperado_cheio_e_aviso():
    # Cenário real: a Sprint 73 - Growth terminou em 11/09 e continuou `active`.
    sprint = {
        "id": 3995,
        "name": "Sprint 73 - Growth",
        "state": "active",
        "start_date": date(2026, 9, 9),
        "end_date": date(2026, 9, 11),
    }
    result = progress.sprint_progress(
        sprint,
        [_issue("Em Desenvolvimento", "indeterminate", 2)],
        SOURCES,
        today=date(2026, 9, 14),
    )
    assert result.overdue_active is True
    assert result.expected == 1.0
    assert result.real == 0.4


def test_epico_nao_entra_na_conta_da_sprint():
    sprint = {"id": 1, "name": "Sprint 74", "state": "active", "start_date": None, "end_date": None}
    result = progress.sprint_progress(
        sprint,
        [
            _issue("Concluído", "done", 8, issue_type="Épico"),
            _issue("Disponivel para análise", "new", 2),
        ],
        SOURCES,
        today=date(2026, 9, 14),
    )
    assert (result.issue_count, result.real, result.expected) == (1, 0.0, None)


# --- Configuração salva --------------------------------------------------------------


def test_mapa_salvo_vence_o_padrao():
    salvo = {
        "stages": [
            {"id": s.id, "label": s.label, "order": s.order, "weight": s.weight, "color": s.color}
            for s in DEFAULT_STAGES
        ],
        "statuses": {"AJUSTE": "review"},
    }
    stages = ProgressStages.from_setting(salvo)
    assert stages.weight_of("AJUSTE", "new")[0] == 0.7
    # Status fora do mapa salvo passa a cair pela categoria.
    assert stages.weight_of("Em Desenvolvimento", "indeterminate")[0] == 0.5


def test_status_apontando_para_etapa_inexistente_e_descartado():
    stages = ProgressStages(stages=DEFAULT_STAGES, statuses={"X": "etapa-que-nao-existe"})
    assert stages.stage_of("X") is None
    assert "X" not in stages.statuses


def test_setting_invalido_volta_ao_padrao():
    assert ProgressStages.from_setting(None).statuses == ProgressStages().statuses
    assert ProgressStages.from_setting({"stages": []}).stages == DEFAULT_STAGES


# --- API -----------------------------------------------------------------------------


@pytest.fixture
async def api(db_app, client, db_pool):
    await db_pool.executemany(
        """
        INSERT INTO jira_issue (key, id, project_key, issue_type, summary, status, status_category,
                                created_at, updated_at, raw)
        VALUES ($1, $1, 'WAI', 'Tarefa', 'x', $2, $3, now(), now(), '{}')
        """,
        [
            ("WAI-1", "Em Desenvolvimento", "indeterminate"),
            ("WAI-2", "DISPONIVEL PARA REVIEW", "new"),
            ("WAI-3", "DISPONIVEL PARA REVIEW", "new"),
            ("WAI-4", "Status exótico", "new"),
        ],
    )
    return client


async def test_configuracoes_lista_status_do_espelho_com_a_etapa(api):
    response = await api.get("/api/progress/stages")
    assert response.status_code == 200, response.text
    data = response.json()

    assert [s["id"] for s in data["stages"]] == [s.id for s in DEFAULT_STAGES]
    by_status = {s["status"]: s for s in data["statuses"]}
    assert by_status["DISPONIVEL PARA REVIEW"]["issue_count"] == 2
    assert by_status["DISPONIVEL PARA REVIEW"]["stage_id"] == "review"
    assert by_status["Status exótico"]["stage_id"] is None


async def test_salvar_pesos_muda_o_que_a_proxima_leitura_devolve(api):
    payload = {
        "stages": [
            {"id": "analise", "label": "Análise", "order": 0, "weight": 0.0, "color": "#94a3b8"},
            {"id": "feito", "label": "Feito", "order": 1, "weight": 1.0, "color": "#10b981"},
        ],
        "statuses": {"Status exótico": "feito", "Em Desenvolvimento": "analise"},
    }
    saved = await api.put("/api/progress/stages", json=payload)
    assert saved.status_code == 200, saved.text

    data = (await api.get("/api/progress/stages")).json()
    assert [s["id"] for s in data["stages"]] == ["analise", "feito"]
    by_status = {s["status"]: s["stage_id"] for s in data["statuses"]}
    assert by_status["Status exótico"] == "feito"
    # A etapa "review" sumiu: o status que apontava para ela volta para a categoria.
    assert by_status["DISPONIVEL PARA REVIEW"] is None
