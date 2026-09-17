"""Cliente somente-leitura do Jira Cloud (REST v3 + Agile 1.0).

- Busca de issues pelo endpoint novo `POST /rest/api/3/search/jql` (paginação por
  `nextPageToken`); o `/rest/api/3/search` antigo foi descontinuado pela Atlassian.
- Token clássico fala direto com o site; token com escopos passa pelo gateway
  `api.atlassian.com/ex/jira/{cloudId}`.
"""

from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from typing import Any

import httpx

from integrations.errors import BadRequest, IntegrationError, SprintsNotSupported
from integrations.http import ApiTransport

SERVICE = "Jira"
JIRA_GATEWAY = "https://api.atlassian.com/ex/jira"

SPRINT_FIELD_TYPE = "com.pyxis.greenhopper.jira:gh-sprint"
STORY_POINT_NAMES = ("story points", "story point estimate", "pontos de história")
SPRINT_STATES = ("active", "future", "closed")


@dataclass(frozen=True)
class JiraField:
    id: str
    name: str


@dataclass(frozen=True)
class JiraFieldMap:
    """Campos customizados que variam de instância para instância."""

    sprint: JiraField | None
    story_points: JiraField | None
    story_point_candidates: tuple[JiraField, ...] = ()


async def discover_cloud_id(site_url: str, client: httpx.AsyncClient | None = None) -> str:
    own = client is None
    client = client or httpx.AsyncClient(timeout=10.0)
    try:
        response = await client.get(f"{site_url.rstrip('/')}/_edge/tenant_info")
        response.raise_for_status()
        return response.json()["cloudId"]
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise IntegrationError(
            SERVICE, "Jira: não foi possível descobrir o cloudId do site."
        ) from exc
    finally:
        if own:
            await client.aclose()


class JiraClient:
    def __init__(self, transport: ApiTransport, cloud_id: str | None = None) -> None:
        self._http = transport
        self.cloud_id = cloud_id

    @classmethod
    async def create(
        cls,
        *,
        site_url: str,
        email: str,
        api_token: str,
        auth_mode: str = "classic",
        cloud_id: str | None = None,
        client: httpx.AsyncClient | None = None,
        **transport_kwargs: Any,
    ) -> "JiraClient":
        if auth_mode == "scoped":
            cloud_id = cloud_id or await discover_cloud_id(site_url, client)
            base_url = f"{JIRA_GATEWAY}/{cloud_id}"
        else:
            base_url = site_url
        transport = ApiTransport(
            service=SERVICE,
            base_url=base_url,
            auth=(email, api_token),
            client=client,
            **transport_kwargs,
        )
        return cls(transport, cloud_id if auth_mode == "scoped" else None)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "JiraClient":
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.aclose()

    # --- Identidade e metadados -------------------------------------------------

    async def myself(self) -> dict[str, Any]:
        return await self._http.get("/rest/api/3/myself")

    async def fields(self) -> list[dict[str, Any]]:
        return await self._http.get("/rest/api/3/field")

    async def discover_fields(self) -> JiraFieldMap:
        fields = await self.fields()
        sprint = next(
            (f for f in fields if (f.get("schema") or {}).get("custom") == SPRINT_FIELD_TYPE),
            None,
        )
        candidates = [
            f
            for f in fields
            if f.get("custom")
            and (f.get("name") or "").strip().lower() in STORY_POINT_NAMES
            and (f.get("schema") or {}).get("type") == "number"
        ]
        # "Story Points" (clássico) tem prioridade sobre "Story point estimate" (team-managed).
        candidates.sort(key=lambda f: STORY_POINT_NAMES.index(f["name"].strip().lower()))
        as_field = lambda f: JiraField(id=f["id"], name=f["name"])  # noqa: E731
        return JiraFieldMap(
            sprint=as_field(sprint) if sprint else None,
            story_points=as_field(candidates[0]) if candidates else None,
            story_point_candidates=tuple(as_field(f) for f in candidates),
        )

    # --- Issues -----------------------------------------------------------------

    async def iter_search(
        self,
        jql: str,
        *,
        fields: Iterable[str] = ("*navigable",),
        expand: Iterable[str] = (),
        page_size: int = 100,
    ) -> AsyncIterator[dict[str, Any]]:
        body: dict[str, Any] = {"jql": jql, "fields": list(fields), "maxResults": page_size}
        if expand:
            body["expand"] = ",".join(expand)
        while True:
            page = await self._http.post("/rest/api/3/search/jql", json=body)
            for issue in page.get("issues", []):
                yield issue
            token = page.get("nextPageToken")
            if page.get("isLast", token is None) or not token:
                return
            body = {**body, "nextPageToken": token}

    async def search(self, jql: str, **kwargs: Any) -> list[dict[str, Any]]:
        return [issue async for issue in self.iter_search(jql, **kwargs)]

    async def get_issue(
        self, key: str, *, fields: Iterable[str] = ("*all",), expand: Iterable[str] = ()
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"fields": ",".join(fields)}
        if expand:
            params["expand"] = ",".join(expand)
        return await self._http.get(f"/rest/api/3/issue/{key}", params=params)

    async def iter_comments(self, key: str, page_size: int = 100) -> AsyncIterator[dict[str, Any]]:
        async for comment in self._iter_offset(
            f"/rest/api/3/issue/{key}/comment",
            items_key="comments",
            params={"orderBy": "created"},
            page_size=page_size,
        ):
            yield comment

    async def iter_changelog(self, key: str, page_size: int = 100) -> AsyncIterator[dict[str, Any]]:
        async for entry in self._iter_offset(
            f"/rest/api/3/issue/{key}/changelog", items_key="values", page_size=page_size
        ):
            yield entry

    # --- Agile: boards e sprints ------------------------------------------------

    async def iter_boards(
        self, *, name: str | None = None, project_key: str | None = None, page_size: int = 50
    ) -> AsyncIterator[dict[str, Any]]:
        params: dict[str, Any] = {}
        if name:
            params["name"] = name
        if project_key:
            params["projectKeyOrId"] = project_key
        async for board in self._iter_offset(
            "/rest/agile/1.0/board", items_key="values", params=params, page_size=page_size
        ):
            yield board

    async def get_board(self, board_id: int) -> dict[str, Any]:
        return await self._http.get(f"/rest/agile/1.0/board/{board_id}")

    async def iter_sprints(
        self, board_id: int, *, states: Iterable[str] = SPRINT_STATES, page_size: int = 50
    ) -> AsyncIterator[dict[str, Any]]:
        try:
            async for sprint in self._iter_offset(
                f"/rest/agile/1.0/board/{board_id}/sprint",
                items_key="values",
                params={"state": ",".join(states)},
                page_size=page_size,
            ):
                yield sprint
        except BadRequest as exc:
            # Board kanban responde 400 "The board does not support sprints".
            raise SprintsNotSupported(
                SERVICE, f"Jira: o board {board_id} não usa sprints (kanban).", 400
            ) from exc

    async def get_sprint(self, sprint_id: int) -> dict[str, Any]:
        return await self._http.get(f"/rest/agile/1.0/sprint/{sprint_id}")

    # --- Paginação por offset (startAt/maxResults) -------------------------------

    async def _iter_offset(
        self,
        path: str,
        *,
        items_key: str,
        params: dict[str, Any] | None = None,
        page_size: int,
    ) -> AsyncIterator[dict[str, Any]]:
        start = 0
        while True:
            page = await self._http.get(
                path, params={**(params or {}), "startAt": start, "maxResults": page_size}
            )
            items = page.get(items_key, [])
            for item in items:
                yield item
            start += len(items)
            total = page.get("total")
            if not items or page.get("isLast") is True or (total is not None and start >= total):
                return
