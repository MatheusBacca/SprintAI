"""Guarda da API local contra chamadas vindas de outros sites abertos no navegador.

Uma API em 127.0.0.1 é alcançável por qualquer página que o dev abrir. Três
camadas fecham isso:

1. `Host` precisa ser loopback — barra DNS rebinding (um domínio externo que
   passa a resolver para 127.0.0.1 chega com o próprio nome no Host).
2. `Origin`, quando presente, precisa estar na lista do front; sem Origin, um
   `Sec-Fetch-Site: cross-site`/`same-site` é recusado.
3. Rotas `/api` exigem o header `X-SprintAI`. Header customizado força preflight
   de CORS, então um `<form>` ou `fetch` "simples" de outro site não passa.
"""

from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from config import LOOPBACK_HOSTS

CLIENT_HEADER = "x-sprintai"
REJECTED_FETCH_SITES = {"cross-site", "same-site"}


def _hostname(host_header: str) -> str:
    host_header = host_header.strip().lower()
    if host_header.startswith("["):  # [::1]:8765
        return host_header[1 : host_header.find("]")]
    return host_header.rsplit(":", 1)[0] if host_header.count(":") == 1 else host_header


def check_request(
    *,
    method: str,
    path: str,
    headers: dict[str, str],
    allowed_origins: set[str],
    api_prefix: str = "/api",
) -> str | None:
    """Devolve o motivo da recusa, ou None se a requisição pode seguir."""
    if _hostname(headers.get("host", "")) not in LOOPBACK_HOSTS:
        return "Host não permitido"

    origin = headers.get("origin")
    if origin is not None:
        if origin.rstrip("/") not in allowed_origins:
            return "Origem não permitida"
    elif headers.get("sec-fetch-site") in REJECTED_FETCH_SITES:
        return "Requisição de outro site não permitida"

    # Preflight é respondido pelo CORSMiddleware; não carrega o header customizado.
    if method == "OPTIONS":
        return None

    if path.startswith(api_prefix) and CLIENT_HEADER not in headers:
        return "Header X-SprintAI ausente"
    return None


class LocalGuardMiddleware:
    def __init__(self, app: ASGIApp, allowed_origins: set[str]) -> None:
        self.app = app
        self.allowed_origins = {o.rstrip("/") for o in allowed_origins}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        reason = check_request(
            method=request.method,
            path=request.url.path,
            headers={k.lower(): v for k, v in request.headers.items()},
            allowed_origins=self.allowed_origins,
        )
        if reason is not None:
            response = JSONResponse({"detail": reason}, status_code=403)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


def loopback_origins(*ports: int) -> set[str]:
    origins: set[str] = set()
    for port in ports:
        for host in ("127.0.0.1", "localhost"):
            origins.add(f"http://{host}:{port}")
    return origins


def normalize_origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def build_allowed_origins(front_origin: str, api_port: int) -> set[str]:
    """Origens aceitas: a do front (nos dois nomes de loopback) e a da própria API.

    A porta do front sai do `FRONT_ORIGIN`. Cravá-la aqui faria trocar a porta no
    `.env` liberar só a origem escrita lá — abrir a mesma tela pelo outro nome de
    loopback cairia em 403, e o README manda abrir por `127.0.0.1`.
    """
    origin = normalize_origin(front_origin)
    front_port = urlsplit(origin).port
    ports = (front_port, api_port) if front_port else (api_port,)
    return {origin} | loopback_origins(*ports)
