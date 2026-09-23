"""Transporte HTTP comum aos clientes Jira e Bitbucket.

- Basic auth (e-mail + token) aplicado só para hosts da lista permitida: uma URL de
  paginação apontando para outro host é recusada antes de enviar credenciais.
- Novas tentativas com backoff em 429/502/503/504 e falhas de rede, respeitando
  `Retry-After`. Escrita que não pode repetir (`idempotent=False`, a transição do Jira)
  só tenta de novo quando o pedido com certeza não chegou: 429 e falha de conexão.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlsplit

import httpx

from core.logger import get_logger
from integrations.errors import IntegrationError, IntegrationUnavailable, error_for_status

logger = get_logger(__name__)

DEFAULT_TIMEOUT = httpx.Timeout(20.0, connect=5.0)
RETRY_STATUSES = {429, 502, 503, 504}
# 429 é recusa antes de processar; 5xx e timeout de leitura podem ter chegado a aplicar.
UNSAFE_RETRY_STATUSES = {429}
MAX_BACKOFF_SECONDS = 60.0

Sleep = Callable[[float], Awaitable[None]]


def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return min(float(retry_after), MAX_BACKOFF_SECONDS)
            except ValueError:
                pass
    return min(2.0**attempt, MAX_BACKOFF_SECONDS)


class ApiTransport:
    def __init__(
        self,
        *,
        service: str,
        base_url: str,
        auth: tuple[str, str],
        client: httpx.AsyncClient | None = None,
        max_retries: int = 3,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self.service = service
        self.base_url = base_url.rstrip("/")
        self._auth = auth
        self._allowed_host = urlsplit(self.base_url).netloc
        self._client = client or httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)
        self._owns_client = client is None
        self._max_retries = max_retries
        self._sleep = sleep

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "ApiTransport":
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.aclose()

    def _resolve_url(self, path_or_url: str) -> str:
        if path_or_url.startswith(("http://", "https://")):
            if urlsplit(path_or_url).netloc != self._allowed_host or not path_or_url.startswith(
                "https://"
            ):
                raise IntegrationError(
                    self.service, f"{self.service}: URL de paginação fora do host esperado."
                )
            return path_or_url
        return f"{self.base_url}/{path_or_url.lstrip('/')}"

    async def request(
        self,
        method: str,
        path_or_url: str,
        *,
        params: dict[str, Any] | list[tuple[str, Any]] | None = None,
        json: Any = None,
        idempotent: bool = True,
    ) -> Any:
        url = self._resolve_url(path_or_url)
        retry_statuses = RETRY_STATUSES if idempotent else UNSAFE_RETRY_STATUSES
        attempt = 0
        while True:
            response: httpx.Response | None = None
            try:
                response = await self._client.request(
                    method,
                    url,
                    params=params,
                    json=json,
                    auth=self._auth,
                    headers={"Accept": "application/json"},
                )
            except httpx.TransportError as exc:
                sent_maybe = not isinstance(exc, httpx.ConnectError | httpx.ConnectTimeout)
                if sent_maybe and not idempotent:
                    raise IntegrationUnavailable(
                        self.service,
                        f"{self.service}: sem resposta a tempo — confira no {self.service} "
                        "se a mudança entrou.",
                    ) from exc
                if attempt >= self._max_retries:
                    raise IntegrationUnavailable(
                        self.service, f"{self.service}: não foi possível conectar."
                    ) from exc
            else:
                if response.status_code < 400:
                    return response.json() if response.content else None
                if response.status_code not in retry_statuses or attempt >= self._max_retries:
                    raise error_for_status(self.service, response.status_code)

            delay = _retry_delay(response, attempt)
            logger.info(
                "%s: nova tentativa %s/%s em %.1fs (%s %s)",
                self.service,
                attempt + 1,
                self._max_retries,
                delay,
                method,
                urlsplit(url).path,
            )
            await self._sleep(delay)
            attempt += 1

    async def get(self, path_or_url: str, **kwargs) -> Any:
        return await self.request("GET", path_or_url, **kwargs)

    async def post(self, path_or_url: str, **kwargs) -> Any:
        return await self.request("POST", path_or_url, **kwargs)

    async def put(self, path_or_url: str, **kwargs) -> Any:
        return await self.request("PUT", path_or_url, **kwargs)
