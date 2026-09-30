import pytest

from services.card_colors import CardColors, title_repos
from services.sync.engine import save_scope
from services.sync.scope import SyncScope

EPICO, ENHANCEMENTS, FEATURE = "#7c3aed", "#c9a227", "#15803d"


def colors(**repos):
    return CardColors.from_setting({"repos": repos})


# --- Regra ---------------------------------------------------------------------------


def test_pais_tem_cor_pelo_tipo_por_padrao():
    padrao = CardColors()

    assert padrao.tint_for("Épico", "Qualquer coisa").color == EPICO
    assert padrao.tint_for("Epic", "Qualquer coisa").color == EPICO
    assert padrao.tint_for("Enhancements", "Plano gratuito").color == ENHANCEMENTS
    assert padrao.tint_for("Feature", "Chat SDR").color == FEATURE
    assert padrao.tint_for("Feature", "Chat SDR").source == "tipo"


def test_tarefa_ganha_a_cor_do_repositorio_do_colchete_do_titulo():
    tint = colors(monitoria="#2f7cf6").tint_for("Tarefa", "[monitoria] Enviar a coleta em lotes")

    assert (tint.color, tint.source, tint.label) == ("#2f7cf6", "repositorio", "monitoria")


@pytest.mark.parametrize(
    "summary",
    [
        "[Supervisor-Web] Ajustar espaçamento",
        "[supervisor web] Ajustar espaçamento",
        "  [SUPERVISOR_WEB] Ajustar espaçamento",
    ],
)
def test_grafia_do_repositorio_no_titulo_nao_importa(summary):
    assert colors(**{"supervisor-web": "#0d9488"}).tint_for("Ajuste", summary).color == "#0d9488"


def test_colchete_com_varios_repositorios_fica_com_o_primeiro_que_tem_cor():
    config = colors(qualificai="#db2777")

    tint = config.tint_for("Ajuste", "[Supervisor-Web / QualificAI] Status no painel")

    assert (tint.color, tint.label) == ("#db2777", "qualificai")


@pytest.mark.parametrize(
    "summary",
    [
        "Analisar e fatiar a: Plano gratuito do QualificAI",
        "(organIA/monitorIA) Liberação de API",
        "Enviar ao [monitoria] no meio do título",
        "[weaction] Enviar a análise do Nôa",
        "",
        None,
    ],
)
def test_card_nao_identificavel_fica_sem_cor(summary):
    config = colors(monitoria="#2f7cf6", **{"weaction-api": "#ea580c"})

    assert config.tint_for("Tarefa", summary) is None


def test_tipo_sem_cor_cai_para_o_repositorio_do_titulo():
    config = CardColors.from_setting({"types": {"epico": None}, "repos": {"monitoria": "#2f7cf6"}})

    assert config.tint_for("Épico", "Sem colchete") is None
    assert config.tint_for("Épico", "[monitoria] Épico de um repo só").label == "monitoria"


def test_tipo_vence_o_repositorio_do_titulo():
    tint = colors(monitoria="#2f7cf6").tint_for("Épico", "[monitoria] Coleta")

    assert (tint.color, tint.source) == (EPICO, "tipo")


def test_setting_invalido_volta_ao_padrao_e_descarta_cor_de_repo_invalida():
    config = CardColors.from_setting(
        {
            "types": {"epico": "roxo", "feature": None},
            "repos": {"monitoria": "red", "qualificai": "#DB2777"},
        }
    )

    assert config.types == {"epico": EPICO, "enhancements": ENHANCEMENTS, "feature": None}
    assert config.repos == {"qualificai": "#db2777"}


def test_colchete_do_titulo_separa_os_repositorios():
    assert title_repos("[Supervisor-Web / QualificAI] X") == ["Supervisor-Web", "QualificAI"]
    assert title_repos("[monitoria] [qualificai] X") == ["monitoria"]
    assert title_repos("Sem colchete") == []


# --- API -----------------------------------------------------------------------------


@pytest.fixture
async def scope(db_pool):
    await save_scope(
        db_pool,
        SyncScope.model_validate({"bitbucket": {"repo_slugs": ["monitoria", "qualificai"]}}),
    )


async def test_padrao_lista_os_tipos_e_os_repositorios_da_sincronizacao(db_app, client, scope):
    body = (await client.get("/api/preferences/card-colors")).json()

    assert [(t["id"], t["label"], t["color"]) for t in body["types"]] == [
        ("epico", "Épico", EPICO),
        ("enhancements", "Enhancements", ENHANCEMENTS),
        ("feature", "Feature", FEATURE),
    ]
    assert body["repos"] == [
        {"slug": "monitoria", "color": None, "synced": True},
        {"slug": "qualificai", "color": None, "synced": True},
    ]
    assert body["suggestions"]


async def test_salva_cores_e_repositorio_fora_da_sincronizacao_continua_na_lista(
    db_app, client, scope
):
    response = await client.put(
        "/api/preferences/card-colors",
        json={
            "types": {"epico": "#5B21B6", "feature": None},
            "repos": {"monitoria": "#2f7cf6", "qualificai": None, "node-red4": "#0d9488"},
        },
    )

    assert response.status_code == 200
    body = (await client.get("/api/preferences/card-colors")).json()
    assert {t["id"]: t["color"] for t in body["types"]} == {
        "epico": "#5b21b6",
        "enhancements": ENHANCEMENTS,
        "feature": None,
    }
    assert body["repos"] == [
        {"slug": "monitoria", "color": "#2f7cf6", "synced": True},
        {"slug": "node-red4", "color": "#0d9488", "synced": False},
        {"slug": "qualificai", "color": None, "synced": True},
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {"repos": {"monitoria": "red"}},
        {"repos": {"monitoria": "#2f7cf6; background: url(x)"}},
        {"types": {"subtarefa": "#2f7cf6"}},
    ],
)
async def test_recusa_cor_que_nao_e_hex_e_tipo_desconhecido(db_app, client, scope, payload):
    response = await client.put("/api/preferences/card-colors", json=payload)

    assert response.status_code == 422
    assert "url(x)" not in response.text
