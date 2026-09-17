from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from integrations.bitbucket_client import BitbucketClient
from integrations.errors import IntegrationError
from tests.fixtures import load

API = "https://api.bitbucket.org/2.0"


@pytest.fixture
async def bitbucket():
    client = BitbucketClient.create(
        email="dev@weon.com.br", api_token="t" * 24, workspace="weonrepo"
    )
    yield client
    await client.aclose()


@respx.mock
async def test_repositorios_seguem_link_next(bitbucket):
    route = respx.get(f"{API}/repositories/weonrepo").mock(
        side_effect=[
            httpx.Response(200, json=load("bitbucket/repositories_page_1.json")),
            httpx.Response(200, json=load("bitbucket/repositories_page_2.json")),
        ]
    )
    since = datetime(2026, 9, 1, 9, 0, tzinfo=timezone(timedelta(hours=-3)))

    repos = [r async for r in bitbucket.iter_repositories(updated_since=since)]

    assert [r["slug"] for r in repos] == ["monitoria", "organia-configs", "supervisor-web"]
    first, second = (c.request.url.params for c in route.calls)
    assert first["q"] == "updated_on > 2026-09-01T12:00:00+00:00"
    assert second["page"] == "2"  # veio do link `next`


@respx.mock
async def test_pull_requests_pedem_todos_os_estados_e_participantes(bitbucket):
    route = respx.get(f"{API}/repositories/weonrepo/monitoria/pullrequests").mock(
        return_value=httpx.Response(200, json=load("bitbucket/pullrequests.json"))
    )

    prs = [pr async for pr in bitbucket.iter_pull_requests("monitoria")]

    assert prs[0]["participants"][0]["state"] == "changes_requested"
    params = route.calls.last.request.url.params
    assert params.get_list("state") == ["OPEN", "MERGED", "DECLINED", "SUPERSEDED"]
    assert params["fields"] == "+values.participants,+values.draft"


@respx.mock
async def test_branches_filtram_por_nome_com_aspas_escapadas(bitbucket):
    route = respx.get(f"{API}/repositories/weonrepo/monitoria/refs/branches").mock(
        return_value=httpx.Response(200, json={"values": [{"name": "WAI-7001-x"}]})
    )

    branches = [b async for b in bitbucket.iter_branches("monitoria", name_contains='WAI-"7001')]

    assert branches == [{"name": "WAI-7001-x"}]
    assert route.calls.last.request.url.params["q"] == 'name ~ "WAI-\\"7001"'


@respx.mock
async def test_next_para_outro_host_e_recusado_sem_enviar_credencial(bitbucket):
    respx.get(f"{API}/repositories/weonrepo").mock(
        return_value=httpx.Response(
            200, json={"values": [{"slug": "a"}], "next": "https://evil.example/steal?page=2"}
        )
    )
    foreign = respx.get("https://evil.example/steal").mock(return_value=httpx.Response(200))

    with pytest.raises(IntegrationError, match="fora do host"):
        [r async for r in bitbucket.iter_repositories()]

    assert not foreign.called


@respx.mock
async def test_repository_count_le_o_size(bitbucket):
    respx.get(f"{API}/repositories/weonrepo").mock(
        return_value=httpx.Response(200, json={"size": 57, "values": []})
    )

    assert await bitbucket.repository_count() == 57
