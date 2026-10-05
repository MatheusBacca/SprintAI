"""Cliente do Bitbucket Cloud (API 2.0).

Quase tudo é leitura. Escreve só duas coisas, cada uma depois da confirmação do dev na tela:
o **merge** de um PR (o "Concluir" do card) e a **lista de reviewers** de um PR. O merge vai
com `idempotent=False`: repetir depois de um 5xx poderia mergear de novo o que já entrou.

Paginação segue o link `next` devolvido pela API; o transporte recusa `next` fora
de `api.bitbucket.org`, então as credenciais nunca vão para outro host.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from datetime import UTC, datetime
from typing import Any

import httpx

from integrations.http import ApiTransport

SERVICE = "Bitbucket"
BITBUCKET_API = "https://api.bitbucket.org/2.0"
PR_STATES = ("OPEN", "MERGED", "DECLINED", "SUPERSEDED")
MERGE_STRATEGIES = ("merge_commit", "squash", "fast_forward")

# Tudo o que o SprintAI usa do Bitbucket, e para quê — o teste de conexão confere contra os
# escopos que o próprio Bitbucket diz que o token tem (`x-oauth-scopes`).
REQUIRED_SCOPES: dict[str, str] = {
    "read:user:bitbucket": "ler a sua conta",
    "read:repository:bitbucket": "listar repositórios e branches",
    "read:pullrequest:bitbucket": "espelhar PRs, comentários e builds",
    "read:workspace:bitbucket": "listar os membros para escolher reviewer",
    "write:pullrequest:bitbucket": "mergear no Concluir e mexer nos reviewers",
}
# Sem estes, o espelho do Bitbucket não funciona: a conexão nem é salva.
ESSENTIAL_SCOPES = (
    "read:user:bitbucket",
    "read:repository:bitbucket",
    "read:pullrequest:bitbucket",
)
# Merge demorado vira 202 com um link de acompanhamento: espera este tanto antes de desistir
# de saber o fim (o merge segue no Bitbucket).
MERGE_POLL_SECONDS = 2.0
MERGE_POLL_ATTEMPTS = 15


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

    async def current_user_with_scopes(self) -> tuple[dict[str, Any], set[str] | None]:
        """A conta e os escopos do token, como o Bitbucket informa no `x-oauth-scopes`.
        `None` quando ele não diz (credencial sem escopos declarados)."""
        response = await self._http.get("/user", raw=True)
        header = response.headers.get("x-oauth-scopes")
        scopes = {s.strip() for s in header.split(",") if s.strip()} if header else None
        return (response.json() if response.content else {}), scopes

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

    async def merge_pull_request(
        self,
        repo_slug: str,
        pr_id: int,
        *,
        strategy: str,
        close_source_branch: bool,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> dict[str, Any]:
        """Mergeia o PR e devolve o PR mergeado. Não repete: um 5xx pode ter mergeado."""
        if strategy not in MERGE_STRATEGIES:
            raise ValueError(f"Estratégia de merge desconhecida: {strategy}")
        result = await self._http.post(
            f"/repositories/{self.workspace}/{repo_slug}/pullrequests/{pr_id}/merge",
            json={
                "type": "pullrequest",
                "merge_strategy": strategy,
                "close_source_branch": close_source_branch,
            },
            idempotent=False,
        )
        # Merge longo: o Bitbucket responde 202 com a tarefa e o link para acompanhar.
        if (result or {}).get("task_status"):
            return await self._wait_merge(result, sleep=sleep)
        return result or {}

    async def _wait_merge(
        self, task: dict[str, Any], *, sleep: Callable[[float], Awaitable[None]] | None = None
    ) -> dict[str, Any]:
        sleep = sleep or asyncio.sleep
        link = ((task.get("links") or {}).get("self") or {}).get("href")
        for _ in range(MERGE_POLL_ATTEMPTS):
            if task.get("task_status") == "SUCCESS":
                return task.get("merge_result") or {}
            if not link:
                break
            await sleep(MERGE_POLL_SECONDS)
            task = await self._http.get(link)
        return {"state": "MERGING"}

    async def set_reviewers(
        self,
        repo_slug: str,
        pr_id: int,
        reviewers: list[dict[str, str]],
        *,
        title: str | None = None,
    ) -> dict[str, Any]:
        """Troca a lista inteira de reviewers do PR (`[{uuid}]` ou `[{account_id}]`).

        O Bitbucket pede o título junto no PUT; ele vai como está (lido aqui, se não vier).
        Lista inteira e não "adicionar um": repetir o mesmo PUT dá o mesmo PR, então pode
        tentar de novo.
        """
        path = f"/repositories/{self.workspace}/{repo_slug}/pullrequests/{pr_id}"
        if title is None:
            title = (await self._http.get(path)).get("title") or ""
        return await self._http.put(path, json={"title": title, "reviewers": reviewers})

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

    # --- Membros do workspace ------------------------------------------------------

    async def iter_workspace_members(
        self, *, page_size: int = 100
    ) -> AsyncIterator[dict[str, Any]]:
        """Quem pode ser reviewer: os membros do workspace (`read:workspace:bitbucket`)."""
        async for membership in self._iter_pages(
            f"/workspaces/{self.workspace}/members", {"pagelen": page_size}
        ):
            yield membership.get("user") or {}

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
