import pytest

from services.card_colors import CardColors, TitlePart
from services.sync.engine import save_scope
from services.sync.scope import SyncScope

EPICO, ENHANCEMENTS, FEATURE = "#7c3aed", "#c9a227", "#15803d"
AZUL, VERDE, ROSA, LARANJA = "#2f7cf6", "#0d9488", "#db2777", "#ea580c"

# Os repositórios de Sincronização do dev.
SYNCED = (
    "api-audio-transcribe",
    "api-credits",
    "churn-buster",
    "monitoria",
    "node-red4",
    "organia-configs",
    "qualificai",
    "supervisor-web",
    "weaction-api",
)


def colors(aliases=None, **repos):
    return CardColors.from_setting({"repos": repos, "aliases": aliases or {}}, SYNCED)


def tint(config, summary, issue_type="Tarefa"):
    return config.paint(issue_type, summary).tint


# --- Tipo e repositório --------------------------------------------------------------


def test_pais_tem_cor_pelo_tipo_por_padrao():
    padrao = CardColors()

    assert tint(padrao, "Qualquer coisa", "Épico").colors == (EPICO,)
    assert tint(padrao, "Qualquer coisa", "Epic").colors == (EPICO,)
    assert tint(padrao, "Plano gratuito", "Enhancements").colors == (ENHANCEMENTS,)
    assert tint(padrao, "Chat SDR", "Feature").colors == (FEATURE,)
    assert tint(padrao, "Chat SDR", "Feature").source == "tipo"


def test_tarefa_ganha_a_cor_do_repositorio_do_colchete_do_titulo():
    found = tint(colors(monitoria=AZUL), "[monitoria] Enviar a coleta em lotes")

    assert (found.colors, found.source, found.label) == ((AZUL,), "repositorio", "monitoria")


@pytest.mark.parametrize(
    "summary",
    [
        "[Supervisor-Web] Ajustar espaçamento",
        "[supervisor web] Ajustar espaçamento",
        "  [SUPERVISOR_WEB] Ajustar espaçamento",
    ],
)
def test_grafia_do_repositorio_no_titulo_nao_importa(summary):
    assert tint(colors(**{"supervisor-web": VERDE}), summary, "Ajuste").colors == (VERDE,)


@pytest.mark.parametrize(
    "summary",
    [
        "Analisar e fatiar a: Plano gratuito do QualificAI",
        "(organIA/monitorIA) Liberação de API",
        "Enviar ao [monitoria] no meio do título",
        "[api] Nome que dois repositórios começam igual",
        "",
        None,
    ],
)
def test_card_nao_identificavel_fica_sem_cor(summary):
    config = colors(monitoria=AZUL, **{"api-credits": LARANJA, "api-audio-transcribe": ROSA})

    assert config.paint("Tarefa", summary).tint is None
    assert config.paint("Tarefa", summary).title == ()


def test_tipo_sem_cor_cai_para_o_repositorio_do_titulo():
    config = CardColors.from_setting(
        {"types": {"epico": None}, "repos": {"monitoria": AZUL}}, SYNCED
    )

    assert tint(config, "Sem colchete", "Épico") is None
    assert tint(config, "[monitoria] Épico de um repo só", "Épico").label == "monitoria"


def test_tipo_vence_o_repositorio_do_titulo_no_fundo():
    found = tint(colors(monitoria=AZUL), "[monitoria] Coleta", "Épico")

    assert (found.colors, found.source) == ((EPICO,), "tipo")


# --- Apelidos ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("summary", "slug"),
    [
        ("[weaction] Enviar a análise do Nôa", "weaction-api"),
        ("[Supervisor] Botão no header", "supervisor-web"),
        ("[organia] Cadastro pela rota do MonitorIA", "organia-configs"),
        ("[api-audio] Destravar a concorrência", "api-audio-transcribe"),
    ],
)
def test_comeco_do_slug_ate_o_hifen_vale_quando_e_de_um_repositorio_so(summary, slug):
    config = colors(**{slug: AZUL})

    assert tint(config, summary).label == slug


def test_apelido_cadastrado_vale_como_o_slug():
    config = colors(aliases={"organia-configs": ["Internal"]}, **{"organia-configs": VERDE})

    assert tint(config, "[internal] Telas de templates").label == "organia-configs"


def test_apelido_repetido_em_dois_repositorios_nao_e_de_nenhum():
    config = colors(
        aliases={"monitoria": ["painel"], "supervisor-web": ["painel"]},
        monitoria=AZUL,
        **{"supervisor-web": VERDE},
    )

    assert tint(config, "[painel] Qual dos dois?") is None


def test_slug_vence_apelido_e_apelido_vence_o_comeco_do_slug():
    config = colors(
        aliases={"monitoria": ["qualificai", "weaction"]},
        monitoria=AZUL,
        qualificai=VERDE,
        **{"weaction-api": LARANJA},
    )

    assert tint(config, "[qualificai] X").label == "qualificai"
    assert tint(config, "[weaction] X").label == "monitoria"


def test_comecos_do_slug_que_valem_sozinhos_aparecem_para_a_tela():
    config = colors()

    assert config.automatic_aliases("weaction-api") == ["weaction"]
    assert config.automatic_aliases("api-audio-transcribe") == ["api-audio"]
    assert config.automatic_aliases("api-credits") == []
    assert config.automatic_aliases("monitoria") == []


# --- Colchete com vários repositórios ------------------------------------------------


def test_cada_repositorio_do_colchete_entra_no_fundo_na_ordem_do_titulo():
    config = colors(qualificai=ROSA, **{"supervisor-web": VERDE})

    found = tint(config, "[supervisor/qualificai] Status no painel", "Ajuste")

    assert found.colors == (VERDE, ROSA)
    assert found.label == "supervisor-web, qualificai"


def test_repositorio_sem_cor_no_colchete_e_pulado_e_repetido_conta_uma_vez():
    config = colors(qualificai=ROSA)

    assert tint(config, "[Supervisor-Web / QualificAI] X").colors == (ROSA,)
    assert tint(config, "[qualificai/QualificAI] X").colors == (ROSA,)


def test_fundo_vai_ate_tres_cores():
    config = colors(
        monitoria=AZUL, qualificai=ROSA, **{"supervisor-web": VERDE, "weaction-api": LARANJA}
    )

    found = tint(config, "[monitoria/qualificai/supervisor/weaction] X")

    assert found.colors == (AZUL, ROSA, VERDE)
    assert found.label == "monitoria, qualificai, supervisor-web, weaction-api"


def test_titulo_pinta_so_o_nome_de_dentro_do_colchete():
    config = colors(qualificai=ROSA, **{"supervisor-web": VERDE})

    title = config.paint("Ajuste", "[Supervisor-Web / QualificAI] Ajustar o painel").title

    assert title == (
        TitlePart("["),
        TitlePart("Supervisor-Web", VERDE),
        TitlePart(" / "),
        TitlePart("QualificAI", ROSA),
        TitlePart("] Ajustar o painel"),
    )


def test_titulo_do_pai_tambem_pinta_o_nome_do_repositorio():
    title = colors(monitoria=AZUL).paint("Épico", "[monitoria] Coleta").title

    assert title == (TitlePart("["), TitlePart("monitoria", AZUL), TitlePart("] Coleta"))


# --- Persistência --------------------------------------------------------------------


def test_setting_invalido_volta_ao_padrao_e_descarta_o_que_nao_serve():
    config = CardColors.from_setting(
        {
            "types": {"epico": "roxo", "feature": None},
            "repos": {"monitoria": "red", "qualificai": "#DB2777"},
            "aliases": {"monitoria": ["MonitorIA", "  painel ", "", 3, "Painel"]},
        }
    )

    assert config.types == {"epico": EPICO, "enhancements": ENHANCEMENTS, "feature": None}
    assert config.repos == {"qualificai": "#db2777"}
    assert config.aliases == {"monitoria": ("painel",)}


# --- API -----------------------------------------------------------------------------


@pytest.fixture
async def scope(db_pool):
    await save_scope(
        db_pool,
        SyncScope.model_validate(
            {"bitbucket": {"repo_slugs": ["monitoria", "qualificai", "weaction-api"]}}
        ),
    )


async def test_padrao_lista_os_tipos_e_os_repositorios_da_sincronizacao(db_app, client, scope):
    body = (await client.get("/api/preferences/card-colors")).json()

    assert [(t["id"], t["label"], t["color"]) for t in body["types"]] == [
        ("epico", "Épico", EPICO),
        ("enhancements", "Enhancements", ENHANCEMENTS),
        ("feature", "Feature", FEATURE),
    ]
    assert [(r["slug"], r["color"], r["synced"]) for r in body["repos"]] == [
        ("monitoria", None, True),
        ("qualificai", None, True),
        ("weaction-api", None, True),
    ]
    assert body["repos"][2]["automatic_aliases"] == ["weaction"]
    assert body["suggestions"]


async def test_salva_cores_e_apelidos_e_repositorio_fora_da_sincronizacao_continua_na_lista(
    db_app, client, scope
):
    response = await client.put(
        "/api/preferences/card-colors",
        json={
            "types": {"epico": "#5B21B6", "feature": None},
            "repos": {"monitoria": AZUL, "qualificai": None, "node-red4": VERDE},
            "aliases": {"monitoria": ["MonitorIA Voz"], "organia-configs": ["Internal"]},
        },
    )

    assert response.status_code == 200
    body = (await client.get("/api/preferences/card-colors")).json()
    assert {t["id"]: t["color"] for t in body["types"]} == {
        "epico": "#5b21b6",
        "enhancements": ENHANCEMENTS,
        "feature": None,
    }
    assert [(r["slug"], r["color"], r["synced"], r["aliases"]) for r in body["repos"]] == [
        ("monitoria", AZUL, True, ["MonitorIA Voz"]),
        ("node-red4", VERDE, False, []),
        ("organia-configs", None, False, ["Internal"]),
        ("qualificai", None, True, []),
        ("weaction-api", None, True, []),
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {"repos": {"monitoria": "red"}},
        {"repos": {"monitoria": "#2f7cf6; background: url(x)"}},
        {"types": {"subtarefa": "#2f7cf6"}},
        {"aliases": {"monitoria": ["url(x)"], "qualificai": ["URL (x)"]}},
        {"aliases": {"monitoria": ["qualificai"], "qualificai": []}},
    ],
)
async def test_recusa_cor_que_nao_e_hex_tipo_desconhecido_e_apelido_de_dois(
    db_app, client, scope, payload
):
    response = await client.put("/api/preferences/card-colors", json=payload)

    assert response.status_code == 422
    assert "url(x)" not in response.text
