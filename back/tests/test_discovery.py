import httpx
import pytest
import respx

from services.discovery_service import squad_from_sprint_name
from tests.fixtures import load

SITE = "https://weon.atlassian.net"


@pytest.fixture
def jira_configured(credential_store):
    credential_store.set(
        "jira",
        {
            "site_url": SITE,
            "email": "dev@weon.com.br",
            "api_token": "ATATT3xFfGF0-token-discovery",
            "auth_mode": "classic",
        },
    )


@pytest.fixture
def bitbucket_configured(credential_store):
    credential_store.set(
        "bitbucket",
        {"email": "dev@weon.com.br", "api_token": "ATATT3xFfGF0-token-bb", "workspace": "weonrepo"},
    )


@pytest.mark.parametrize(
    ("name", "squad"),
    [
        ("Sprint 73 - Growth", "Growth"),
        ("Sprint 74 - Core", "Core"),
        ("sprint 12 -  Squad Azul ", "Squad Azul"),
        ("Sprint 12", None),
        ("🛠️BUG-SUPORT", None),
        ("Sprint 5 - 25", None),
    ],
)
def test_squad_pelo_sufixo_do_nome(name, squad):
    assert squad_from_sprint_name(name) == squad


async def test_sem_conexao_jira_da_409(client):
    response = await client.get("/api/jira/boards")

    assert response.status_code == 409
    assert response.json()["code"] == "integration_not_configured"


@respx.mock
async def test_lista_boards_do_projeto(client, jira_configured):
    respx.get(f"{SITE}/rest/agile/1.0/board").mock(
        side_effect=[
            httpx.Response(200, json=load("jira/boards_page_1.json")),
            httpx.Response(200, json=load("jira/boards_page_2.json")),
        ]
    )

    response = await client.get("/api/jira/boards", params={"project_key": "WAI"})

    assert response.status_code == 200
    assert response.json()[0] == {
        "id": 144,
        "name": "Engenharia",
        "type": "scrum",
        "project_key": "WAI",
        "project_name": "WeON Atendimentos Incriveis",
    }


async def test_project_key_invalido_da_422(client, jira_configured):
    response = await client.get("/api/jira/boards", params={"project_key": "wai; drop"})
    assert response.status_code == 422


@respx.mock
async def test_sprints_do_board_trazem_squad(client, jira_configured):
    route = respx.get(f"{SITE}/rest/agile/1.0/board/144/sprint").mock(
        return_value=httpx.Response(200, json=load("jira/sprints_board_144.json"))
    )

    response = await client.get(
        "/api/jira/boards/144/sprints", params={"state": "active,future,xpto"}
    )

    body = response.json()
    assert body["supports_sprints"] is True
    assert [(s["name"], s["squad"]) for s in body["sprints"]] == [
        ("Sprint 73 - Core", "Core"),
        ("Sprint 73 - Growth", "Growth"),
        ("🛠️BUG-SUPORT", None),
        ("Sprint 74 - Growth", "Growth"),
    ]
    assert body["sprints"][1]["goal"] == "Integração de novos modelos"
    assert body["sprints"][0]["goal"] is None
    assert route.calls.last.request.url.params["state"] == "active,future"


@respx.mock
async def test_board_kanban_responde_sem_sprints(client, jira_configured):
    respx.get(f"{SITE}/rest/agile/1.0/board/610/sprint").mock(
        return_value=httpx.Response(
            400, json={"errorMessages": ["The board does not support sprints"]}
        )
    )

    response = await client.get("/api/jira/boards/610/sprints")

    assert response.status_code == 200
    assert response.json() == {"board_id": 610, "supports_sprints": False, "sprints": []}


@respx.mock
async def test_token_revogado_vira_502_com_mensagem(client, jira_configured):
    respx.get(f"{SITE}/rest/api/3/field").mock(return_value=httpx.Response(401))

    response = await client.get("/api/jira/fields")

    assert response.status_code == 502
    assert response.json() == {
        "detail": "Jira: credenciais inválidas (e-mail ou token).",
        "code": "authentication_failed",
    }


@respx.mock
async def test_campos_descobertos(client, jira_configured):
    respx.get(f"{SITE}/rest/api/3/field").mock(
        return_value=httpx.Response(200, json=load("jira/fields.json"))
    )

    response = await client.get("/api/jira/fields")

    assert response.json()["sprint"] == {"id": "customfield_10020", "name": "Sprint"}
    assert response.json()["story_points"] == {"id": "customfield_10026", "name": "Story Points"}


@respx.mock
async def test_repositorios_bitbucket_respeitam_limite(client, bitbucket_configured):
    respx.get("https://api.bitbucket.org/2.0/repositories/weonrepo").mock(
        return_value=httpx.Response(200, json=load("bitbucket/repositories_page_1.json"))
    )

    response = await client.get("/api/bitbucket/repositories", params={"limit": 1})

    assert response.status_code == 200
    assert response.json() == [
        {
            "slug": "monitoria",
            "name": "monitoria",
            "updated_on": "2026-09-12T18:20:11.123456Z",
            "is_private": True,
            "main_branch": "main",
            "project_key": None,
            "project_name": None,
        }
    ]


async def test_cofre_indisponivel_na_descoberta_da_503(app, client):
    from security.credential_store import CredentialStoreError, get_credential_store

    class Broken:
        def get(self, provider):
            raise CredentialStoreError("Cofre de credenciais indisponível.")

    app.dependency_overrides[get_credential_store] = lambda: Broken()

    response = await client.get("/api/jira/boards")

    assert response.status_code == 503
    assert response.json()["code"] == "credential_store_unavailable"
