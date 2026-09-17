import httpx
import pytest
import respx

JIRA_SITE = "https://weon.atlassian.net"
JIRA_TOKEN = "ATATT3xFfGF0-token-jira-123456"
BB_TOKEN = "ATATT3xFfGF0-token-bitbucket-7890"
CLOUD_ID = "07911ac9-c9e9-4118-937c-8938f42a30b7"


def jira_payload(**overrides):
    return {
        "site_url": JIRA_SITE,
        "email": "Matheus.Bacca@weon.com.br",
        "api_token": JIRA_TOKEN,
        "auth_mode": "classic",
        **overrides,
    }


def bitbucket_payload(**overrides):
    return {
        "email": "matheus.bacca@weon.com.br",
        "api_token": BB_TOKEN,
        "workspace": "weonrepo",
        **overrides,
    }


def mock_jira_myself(status=200):
    return respx.get(f"{JIRA_SITE}/rest/api/3/myself").mock(
        return_value=httpx.Response(
            status, json={"displayName": "Matheus Bacca", "accountId": "abc"}
        )
    )


def mock_bitbucket(user_status=200, repos_status=200):
    respx.get("https://api.bitbucket.org/2.0/user").mock(
        return_value=httpx.Response(
            user_status, json={"display_name": "Matheus Bacca", "uuid": "{u}"}
        )
    )
    return respx.get("https://api.bitbucket.org/2.0/repositories/weonrepo").mock(
        return_value=httpx.Response(repos_status, json={"size": 42, "values": []})
    )


async def test_lista_conexoes_nao_configuradas(client):
    response = await client.get("/api/connections")

    assert response.status_code == 200
    assert [(c["provider"], c["configured"]) for c in response.json()] == [
        ("jira", False),
        ("bitbucket", False),
    ]


@respx.mock
async def test_salva_jira_depois_de_testar_e_nao_devolve_token(client, credential_store):
    route = mock_jira_myself()

    response = await client.put("/api/connections/jira", json=jira_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert body["account_name"] == "Matheus Bacca"
    assert body["settings"] == {
        "site_url": JIRA_SITE,
        "email": "matheus.bacca@weon.com.br",
        "auth_mode": "classic",
    }
    assert JIRA_TOKEN not in response.text
    # Basic auth com e-mail + token no request ao Jira
    assert route.calls.last.request.headers["authorization"].startswith("Basic ")
    assert credential_store.get("jira")["api_token"] == JIRA_TOKEN


@respx.mock
async def test_jira_rejeitado_nao_grava_nada(client, credential_store):
    mock_jira_myself(status=401)

    response = await client.put("/api/connections/jira", json=jira_payload())

    assert response.status_code == 422
    assert "credenciais inválidas" in response.json()["detail"]
    assert JIRA_TOKEN not in response.text
    assert credential_store.get("jira") is None


@respx.mock
async def test_jira_scoped_descobre_cloud_id_e_usa_gateway(client, credential_store):
    respx.get(f"{JIRA_SITE}/_edge/tenant_info").mock(
        return_value=httpx.Response(200, json={"cloudId": CLOUD_ID})
    )
    gateway = respx.get(f"https://api.atlassian.com/ex/jira/{CLOUD_ID}/rest/api/3/myself").mock(
        return_value=httpx.Response(200, json={"displayName": "Matheus Bacca", "accountId": "abc"})
    )

    response = await client.put("/api/connections/jira", json=jira_payload(auth_mode="scoped"))

    assert response.status_code == 200
    assert gateway.called
    assert response.json()["settings"]["cloud_id"] == CLOUD_ID


@respx.mock
async def test_atualizar_sem_token_mantem_o_salvo(client, credential_store):
    mock_jira_myself()
    await client.put("/api/connections/jira", json=jira_payload())

    response = await client.put(
        "/api/connections/jira", json=jira_payload(api_token="", email="outro@weon.com.br")
    )

    assert response.status_code == 200
    saved = credential_store.get("jira")
    assert saved["api_token"] == JIRA_TOKEN
    assert saved["email"] == "outro@weon.com.br"


async def test_primeiro_cadastro_sem_token_e_recusado(client):
    response = await client.put("/api/connections/jira", json=jira_payload(api_token=None))

    assert response.status_code == 422
    assert response.json()["detail"] == "Informe o token de API."


@pytest.mark.parametrize(
    "site", ["https://evil.com", "http://weon.atlassian.net", "https://weon.atlassian.net.evil.com"]
)
async def test_site_fora_do_atlassian_cloud_e_recusado(client, site):
    response = await client.put("/api/connections/jira", json=jira_payload(site_url=site))

    assert response.status_code == 422
    assert JIRA_TOKEN not in response.text


@respx.mock
async def test_salva_bitbucket_validando_workspace(client, credential_store):
    repos = mock_bitbucket()

    response = await client.put("/api/connections/bitbucket", json=bitbucket_payload())

    assert response.status_code == 200
    assert repos.called
    assert response.json()["settings"]["workspace"] == "weonrepo"
    assert BB_TOKEN not in response.text


@respx.mock
async def test_bitbucket_sem_acesso_ao_workspace(client, credential_store):
    mock_bitbucket(repos_status=403)

    response = await client.put("/api/connections/bitbucket", json=bitbucket_payload())

    assert response.status_code == 422
    assert "weonrepo" in response.json()["detail"]
    assert credential_store.get("bitbucket") is None


@respx.mock
async def test_testar_conexao_salva_registra_erro_sem_apagar(client, credential_store):
    route = mock_jira_myself()
    await client.put("/api/connections/jira", json=jira_payload())
    route.mock(return_value=httpx.Response(401))

    response = await client.post("/api/connections/jira/test")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["status"]["last_error"].startswith("Jira: credenciais inválidas")
    assert body["status"]["validated_at"] is not None  # última validação boa continua
    assert credential_store.get("jira")["api_token"] == JIRA_TOKEN


@respx.mock
async def test_falha_de_rede_vira_mensagem_amigavel(client):
    respx.get(f"{JIRA_SITE}/rest/api/3/myself").mock(side_effect=httpx.ConnectError("boom"))

    response = await client.put("/api/connections/jira", json=jira_payload())

    assert response.status_code == 422
    assert response.json()["detail"] == "Jira: não foi possível conectar ao site informado."


async def test_testar_nao_configurada_da_404(client):
    response = await client.post("/api/connections/bitbucket/test")
    assert response.status_code == 404


@respx.mock
async def test_remover_conexao(client, credential_store):
    mock_bitbucket()
    await client.put("/api/connections/bitbucket", json=bitbucket_payload())

    response = await client.delete("/api/connections/bitbucket")

    assert response.status_code == 204
    assert credential_store.get("bitbucket") is None


async def test_provider_desconhecido_da_422(client):
    response = await client.post("/api/connections/openai/test")
    assert response.status_code == 422


async def test_cofre_indisponivel_da_503(app, client):
    from security.credential_store import CredentialStoreError, get_credential_store

    class Broken:
        def get(self, provider):
            raise CredentialStoreError("Cofre de credenciais indisponível.")

    app.dependency_overrides[get_credential_store] = lambda: Broken()

    response = await client.get("/api/connections")

    assert response.status_code == 503


async def test_token_malformado_nao_e_ecoado_no_erro(client):
    secret = "ATATT com espaco no meio do token"

    response = await client.put("/api/connections/jira", json=jira_payload(api_token=secret))

    assert response.status_code == 422
    assert secret not in response.text
    assert "Token inválido" in response.text
