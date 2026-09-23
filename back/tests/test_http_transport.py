import httpx
import pytest
import respx

from integrations.errors import (
    AuthenticationFailed,
    IntegrationError,
    IntegrationUnavailable,
    RateLimited,
)
from integrations.http import ApiTransport

BASE = "https://weon.atlassian.net"
TOKEN = "ATATT3xFfGF0-segredo-do-transporte"


class SleepSpy:
    def __init__(self):
        self.calls = []

    async def __call__(self, seconds):
        self.calls.append(seconds)


@pytest.fixture
def sleep():
    return SleepSpy()


@pytest.fixture
async def transport(sleep):
    t = ApiTransport(service="Jira", base_url=BASE, auth=("dev@weon.com.br", TOKEN), sleep=sleep)
    yield t
    await t.aclose()


@respx.mock
async def test_repete_429_respeitando_retry_after(transport, sleep):
    route = respx.get(f"{BASE}/rest/api/3/myself").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "2"}),
            httpx.Response(200, json={"displayName": "Matheus"}),
        ]
    )

    body = await transport.get("/rest/api/3/myself")

    assert body == {"displayName": "Matheus"}
    assert route.call_count == 2
    assert sleep.calls == [2.0]


@respx.mock
async def test_429_persistente_vira_rate_limited(transport, sleep):
    respx.get(f"{BASE}/x").mock(return_value=httpx.Response(429))

    with pytest.raises(RateLimited):
        await transport.get("/x")

    assert sleep.calls == [1.0, 2.0, 4.0]  # backoff exponencial, 3 novas tentativas


@respx.mock
async def test_503_persistente_vira_indisponivel(transport, sleep):
    respx.get(f"{BASE}/x").mock(return_value=httpx.Response(503))

    with pytest.raises(IntegrationUnavailable):
        await transport.get("/x")


@respx.mock
async def test_falha_de_rede_repete_e_depois_desiste(transport, sleep):
    route = respx.get(f"{BASE}/x").mock(side_effect=httpx.ConnectError("boom"))

    with pytest.raises(IntegrationUnavailable, match="não foi possível conectar"):
        await transport.get("/x")

    assert route.call_count == 4


@respx.mock
async def test_401_nao_repete_e_nao_vaza_token(transport, sleep):
    route = respx.get(f"{BASE}/x").mock(return_value=httpx.Response(401, text=f"bad {TOKEN}"))

    with pytest.raises(AuthenticationFailed) as info:
        await transport.get("/x")

    assert route.call_count == 1
    assert sleep.calls == []
    assert TOKEN not in str(info.value)


@respx.mock
async def test_envia_basic_auth_e_accept_json(transport):
    route = respx.get(f"{BASE}/x").mock(return_value=httpx.Response(200, json={}))

    await transport.get("/x")

    request = route.calls.last.request
    assert request.headers["authorization"].startswith("Basic ")
    assert request.headers["accept"] == "application/json"


@pytest.mark.parametrize(
    "url", ["https://evil.example/rest/api/3/myself", "http://weon.atlassian.net/rest/api/3/myself"]
)
@respx.mock
async def test_recusa_url_absoluta_fora_do_host_ou_sem_https(transport, url):
    foreign = respx.get(url).mock(return_value=httpx.Response(200, json={}))

    with pytest.raises(IntegrationError, match="fora do host"):
        await transport.get(url)

    assert not foreign.called


@respx.mock
async def test_resposta_vazia_devolve_none(transport):
    respx.post(f"{BASE}/x").mock(return_value=httpx.Response(204))

    assert await transport.post("/x") is None


@respx.mock
async def test_escrita_nao_idempotente_nao_repete_5xx(transport, sleep):
    # A transição pode ter entrado antes do 503: repetir andaria mais um passo no workflow.
    route = respx.post(f"{BASE}/rest/api/3/issue/WAI-1/transitions").mock(
        return_value=httpx.Response(503)
    )

    with pytest.raises(IntegrationUnavailable):
        await transport.post("/rest/api/3/issue/WAI-1/transitions", json={}, idempotent=False)

    assert route.call_count == 1
    assert sleep.calls == []


@respx.mock
async def test_escrita_nao_idempotente_repete_429(transport, sleep):
    route = respx.post(f"{BASE}/rest/api/3/issue/WAI-1/transitions").mock(
        side_effect=[httpx.Response(429), httpx.Response(204)]
    )

    body = await transport.post(
        "/rest/api/3/issue/WAI-1/transitions", json={}, idempotent=False
    )

    assert body is None
    assert route.call_count == 2


@respx.mock
async def test_escrita_nao_idempotente_sem_resposta_pede_conferir_no_jira(transport, sleep):
    respx.post(f"{BASE}/rest/api/3/issue/WAI-1/transitions").mock(
        side_effect=httpx.ReadTimeout("lento")
    )

    with pytest.raises(IntegrationUnavailable) as caught:
        await transport.post("/rest/api/3/issue/WAI-1/transitions", json={}, idempotent=False)

    assert "confira no Jira" in caught.value.message
    assert sleep.calls == []


@respx.mock
async def test_put_usa_o_mesmo_transporte(transport):
    route = respx.put(f"{BASE}/rest/api/3/issue/WAI-1").mock(return_value=httpx.Response(204))

    assert await transport.put("/rest/api/3/issue/WAI-1", json={"fields": {}}) is None
    assert route.calls.last.request.headers["authorization"].startswith("Basic ")
