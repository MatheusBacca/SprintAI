import json

import httpx
import pytest
import respx

from integrations.errors import SprintsNotSupported
from integrations.jira_client import JiraClient
from tests.fixtures import load

SITE = "https://weon.atlassian.net"
CLOUD_ID = "07911ac9-c9e9-4118-937c-8938f42a30b7"
GATEWAY = f"https://api.atlassian.com/ex/jira/{CLOUD_ID}"


async def _no_sleep(_):
    return None


@pytest.fixture
async def jira():
    client = await JiraClient.create(
        site_url=SITE, email="dev@weon.com.br", api_token="t" * 24, sleep=_no_sleep
    )
    yield client
    await client.aclose()


@respx.mock
async def test_search_pagina_por_next_page_token(jira):
    route = respx.post(f"{SITE}/rest/api/3/search/jql").mock(
        side_effect=[
            httpx.Response(200, json=load("jira/search_page_1.json")),
            httpx.Response(200, json=load("jira/search_page_2.json")),
        ]
    )

    issues = await jira.search(
        "sprint = 3995", fields=("summary", "status", "customfield_10026"), expand=("changelog",)
    )

    assert [i["key"] for i in issues] == ["WAI-7001", "WAI-7002", "WAI-7003"]
    first, second = (json.loads(c.request.content) for c in route.calls)
    assert first == {
        "jql": "sprint = 3995",
        "fields": ["summary", "status", "customfield_10026"],
        "maxResults": 100,
        "expand": "changelog",
    }
    assert "nextPageToken" not in first
    assert second["nextPageToken"] == "Ch0jU3RyaW5nJlYwRkpUQT09JUludCZNakF4"


@respx.mock
async def test_boards_paginam_por_offset(jira):
    route = respx.get(f"{SITE}/rest/agile/1.0/board").mock(
        side_effect=[
            httpx.Response(200, json=load("jira/boards_page_1.json")),
            httpx.Response(200, json=load("jira/boards_page_2.json")),
        ]
    )

    boards = [b async for b in jira.iter_boards(project_key="WAI", page_size=2)]

    assert [b["id"] for b in boards] == [144, 610, 51]
    assert [dict(c.request.url.params) for c in route.calls] == [
        {"projectKeyOrId": "WAI", "startAt": "0", "maxResults": "2"},
        {"projectKeyOrId": "WAI", "startAt": "2", "maxResults": "2"},
    ]


@respx.mock
async def test_sprints_filtra_por_estado(jira):
    route = respx.get(f"{SITE}/rest/agile/1.0/board/144/sprint").mock(
        return_value=httpx.Response(200, json=load("jira/sprints_board_144.json"))
    )

    sprints = [s async for s in jira.iter_sprints(144, states=("active", "future"))]

    assert len(sprints) == 4
    assert route.calls.last.request.url.params["state"] == "active,future"


@respx.mock
async def test_board_kanban_sem_sprints(jira):
    respx.get(f"{SITE}/rest/agile/1.0/board/610/sprint").mock(
        return_value=httpx.Response(
            400, json={"errorMessages": ["The board does not support sprints"]}
        )
    )

    with pytest.raises(SprintsNotSupported, match="kanban"):
        [s async for s in jira.iter_sprints(610)]


@respx.mock
async def test_comentarios_paginam_ate_o_total(jira):
    respx.get(f"{SITE}/rest/api/3/issue/WAI-7001/comment").mock(
        side_effect=[
            httpx.Response(200, json=load("jira/comments_page_1.json")),
            httpx.Response(200, json=load("jira/comments_page_2.json")),
        ]
    )

    comments = [c async for c in jira.iter_comments("WAI-7001", page_size=1)]

    assert [c["id"] for c in comments] == ["20001", "20002"]


@respx.mock
async def test_descobre_sprint_e_story_points_numerico(jira):
    respx.get(f"{SITE}/rest/api/3/field").mock(
        return_value=httpx.Response(200, json=load("jira/fields.json"))
    )

    field_map = await jira.discover_fields()

    assert field_map.sprint.id == "customfield_10020"
    # "Story Points" numérico ganha de "Story point estimate"; o de texto é ignorado.
    assert field_map.story_points.id == "customfield_10026"
    assert [f.id for f in field_map.story_point_candidates] == [
        "customfield_10026",
        "customfield_10016",
    ]


@respx.mock
async def test_token_com_escopos_usa_gateway_com_cloud_id_salvo():
    route = respx.get(f"{GATEWAY}/rest/api/3/myself").mock(
        return_value=httpx.Response(200, json={"displayName": "Matheus"})
    )
    tenant = respx.get(f"{SITE}/_edge/tenant_info")

    async with await JiraClient.create(
        site_url=SITE,
        email="dev@weon.com.br",
        api_token="t" * 24,
        auth_mode="scoped",
        cloud_id=CLOUD_ID,
    ) as jira:
        await jira.myself()
        assert jira.cloud_id == CLOUD_ID

    assert route.called
    assert not tenant.called


@respx.mock
async def test_token_com_escopos_descobre_cloud_id_quando_falta():
    respx.get(f"{SITE}/_edge/tenant_info").mock(
        return_value=httpx.Response(200, json={"cloudId": CLOUD_ID})
    )
    route = respx.get(f"{GATEWAY}/rest/agile/1.0/board/144").mock(
        return_value=httpx.Response(200, json={"id": 144})
    )

    async with await JiraClient.create(
        site_url=SITE, email="dev@weon.com.br", api_token="t" * 24, auth_mode="scoped"
    ) as jira:
        await jira.get_board(144)

    assert route.called
