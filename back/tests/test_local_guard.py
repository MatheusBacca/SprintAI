import pytest

from security.local_guard import build_allowed_origins, check_request

ALLOWED = {"http://127.0.0.1:5273", "http://localhost:5273"}


def _check(headers, method="GET", path="/api/connections"):
    return check_request(method=method, path=path, headers=headers, allowed_origins=ALLOWED)


@pytest.mark.parametrize("host", ["127.0.0.1:8765", "localhost:5273", "[::1]:8765", "localhost"])
def test_aceita_hosts_loopback(host):
    assert _check({"host": host, "x-sprintai": "1"}) is None


@pytest.mark.parametrize("host", ["evil.com", "evil.com:8765", "192.168.0.10:8765", ""])
def test_recusa_host_fora_de_loopback(host):
    assert _check({"host": host, "x-sprintai": "1"}) == "Host não permitido"


def test_recusa_origem_desconhecida():
    headers = {"host": "127.0.0.1:8765", "origin": "https://evil.com", "x-sprintai": "1"}
    assert _check(headers) == "Origem não permitida"


def test_aceita_origem_do_front():
    headers = {"host": "127.0.0.1:5273", "origin": "http://localhost:5273", "x-sprintai": "1"}
    assert _check(headers) is None


@pytest.mark.parametrize("site", ["cross-site", "same-site"])
def test_recusa_sec_fetch_site_externo_sem_origin(site):
    headers = {"host": "127.0.0.1:8765", "sec-fetch-site": site, "x-sprintai": "1"}
    assert _check(headers) == "Requisição de outro site não permitida"


def test_exige_header_nas_rotas_api():
    assert _check({"host": "127.0.0.1:8765"}) == "Header X-SprintAI ausente"


def test_nao_exige_header_fora_da_api():
    assert _check({"host": "127.0.0.1:8765"}, path="/docs") is None


def test_preflight_passa_sem_header():
    headers = {"host": "127.0.0.1:8765", "origin": "http://localhost:5273"}
    assert _check(headers, method="OPTIONS") is None


async def test_api_recusa_request_sem_header(raw_client):
    response = await raw_client.get("/api/health")
    assert response.status_code == 403
    assert response.json() == {"detail": "Header X-SprintAI ausente"}


async def test_api_recusa_origem_estranha(client):
    response = await client.get("/api/connections", headers={"Origin": "https://evil.com"})
    assert response.status_code == 403


async def test_api_recusa_dns_rebinding(client):
    response = await client.get("/api/connections", headers={"Host": "attacker.example:8765"})
    assert response.status_code == 403


async def test_preflight_do_front_e_respondido_pelo_cors(raw_client):
    response = await raw_client.options(
        "/api/connections",
        headers={
            "Origin": "http://localhost:5273",
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "content-type,x-sprintai",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5273"


def test_origens_permitidas_seguem_a_porta_do_front_origin():
    origens = build_allowed_origins("http://localhost:5273", 8765)

    # Os dois nomes de loopback do front, senão abrir por 127.0.0.1 daria 403.
    assert origens == {
        "http://localhost:5273",
        "http://127.0.0.1:5273",
        "http://localhost:8765",
        "http://127.0.0.1:8765",
    }


def test_origens_permitidas_nao_carregam_a_porta_antiga():
    assert "http://localhost:5173" not in build_allowed_origins("http://localhost:5273", 8765)


def test_front_origin_sem_porta_nao_quebra():
    assert build_allowed_origins("http://localhost", 8765) == {
        "http://localhost",
        "http://localhost:8765",
        "http://127.0.0.1:8765",
    }
