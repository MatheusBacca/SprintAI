"""Cliente somente-leitura do Bitbucket Cloud (API 2.0).

Paginação segue o link `next` devolvido pela API; o transporte recusa `next` fora
de `api.bitbucket.org`, então as credenciais nunca vão para outro host.
"""

from collections.abc import AsyncIterator, Iterable
from datetime import UTC, datetime
from typing import Any

import httpx

from integrations.http import ApiTransport

SERVICE = "Bitbucket"
BITBUCKET_API = "https://api.bitbucket.org/2.0"
PR_STATES = ("OPEN", "MERGED", "DECLINED", "SUPERSEDED")


def _bbql_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _bbql_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


class BitbucketClient:
    def __init__(self, transport: ApiTransport, workspace: str) -> None:
        self._http = transport
        self.workspace = workspace

    @classmethod
    def create(
        cls,
        *,
        email: str,
        api_token: str,
        workspace: str,
        client: httpx.AsyncClient | None = None,
        **transport_kwargs: Any,
    ) -> "BitbucketClient":
        transport = ApiTransport(
            service=SERVICE,
            base_url=BITBUCKET_API,
            auth=(email, api_token),
            client=client,
            **transport_kwargs,
        )
        return cls(transport, workspace)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "BitbucketClient":
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.aclose()

    async def current_user(self) -> dict[str, Any]:
        return await self._http.get("/user")

    # --- Repositórios -------------------------------------------------------------

    async def iter_repositories(
        self,
        *,
        updated_since: datetime | None = None,
        slugs: Iterable[str] = (),
        page_size: int = 100,
    ) -> AsyncIterator[dict[str, Any]]:
        params: dict[str, Any] = {"pagelen": page_size, "sort": "-updated_on"}
        filters = []
        if updated_since:
            filters.append(f"updated_on > {_bbql_datetime(updated_since)}")
        slugs = list(slugs)
        if slugs:
            filters.append("(" + " OR ".join(f"slug = {_bbql_string(s)}" for s in slugs) + ")")
        if filters:
            params["q"] = " AND ".join(filters)
        async for repo in self._iter_pages(f"/repositories/{self.workspace}", params):
            yield repo

    async def repository_count(self) -> int | None:
        """Total de repositórios visíveis no workspace (valida acesso de leitura)."""
        page = await self._http.get(f"/repositories/{self.workspace}", params={"pagelen": 1})
        return page.get("size")

    # --- Pull requests ------------------------------------------------------------

    async def iter_pull_requests(
        self,
        repo_slug: str,
        *,
        states: Iterable[str] = PR_STATES,
        updated_since: datetime | None = None,
        page_size: int = 50,
    ) -> AsyncIterator[dict[str, Any]]:
        params: list[tuple[str, Any]] = [("pagelen", page_size), ("sort", "-updated_on")]
        params += [("state", state) for state in states]
        # Participantes (aprovações / changes requested) não vêm por padrão na listagem.
        params.append(("fields", "+values.participants,+values.draft"))
        if updated_since:
            params.append(("q", f"updated_on > {_bbql_datetime(updated_since)}"))
        async for pr in self._iter_pages(
            f"/repositories/{self.workspace}/{repo_slug}/pullrequests", params
        ):
            yield pr

    async def get_pull_request(self, repo_slug: str, pr_id: int) -> dict[str, Any]:
        return await self._http.get(
            f"/repositories/{self.workspace}/{repo_slug}/pullrequests/{pr_id}"
        )

    async def iter_pull_request_comments(
        self, repo_slug: str, pr_id: int, *, page_size: int = 50
    ) -> AsyncIterator[dict[str, Any]]:
        """Comentários de um PR, do mais antigo para o mais novo.

        Chamado só quando o `comment_count` do PR mudou — é uma requisição por PR e
        por ciclo, e varrer todos os PRs abertos a cada sweep estouraria o limite.
        """
        async for comment in self._iter_pages(
            f"/repositories/{self.workspace}/{repo_slug}/pullrequests/{pr_id}/comments",
            {"pagelen": page_size, "sort": "created_on"},
        ):
            yield comment

    async def iter_pull_request_statuses(
        self, repo_slug: str, pr_id: int
    ) -> AsyncIterator[dict[str, Any]]:
        async for status in self._iter_pages(
            f"/repositories/{self.workspace}/{repo_slug}/pullrequests/{pr_id}/statuses",
            {"pagelen": 50},
        ):
            yield status

    # --- Branches -----------------------------------------------------------------

    async def iter_branches(
        self, repo_slug: str, *, name_contains: str | None = None, page_size: int = 100
    ) -> AsyncIterator[dict[str, Any]]:
        params: dict[str, Any] = {"pagelen": page_size, "sort": "-target.date"}
        if name_contains:
            params["q"] = f"name ~ {_bbql_string(name_contains)}"
        async for branch in self._iter_pages(
            f"/repositories/{self.workspace}/{repo_slug}/refs/branches", params
        ):
            yield branch

    # --- Paginação ----------------------------------------------------------------

    async def _iter_pages(
        self, path: str, params: dict[str, Any] | list[tuple[str, Any]]
    ) -> AsyncIterator[dict[str, Any]]:
        page = await self._http.get(path, params=params)
        while True:
            for item in page.get("values", []):
                yield item
            next_url = page.get("next")
            if not next_url:
                return
            # `next` já carrega todos os parâmetros da consulta.
            page = await self._http.get(next_url)
