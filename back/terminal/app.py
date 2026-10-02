"""Terminal host: o processo que segura os shells dos terminais do Workspace (B17).

Roda **separado da API**, na `TERMINAL_PORT` e sem `reload` — o launcher sobe a API com
`reload=True`, e cada edição no `back/` derrubaria os shells abertos (inclusive um
`alembic upgrade` no meio). Não abre o banco nem o Cofre: só sabe de sessões.

Transporte sem WebSocket, para a guarda local ficar inteira (o `LocalGuardMiddleware`
deixa passar o que não é HTTP, e o navegador não manda header em WebSocket):

- `GET /api/terminal/stream?since=<id>:<offset>,…` — a saída de **todas** as sessões num
  stream só, lido com `fetch` + `ReadableStream` como o `/api/events`. Um stream por
  terminal esgotaria as seis conexões por origem do navegador;
- `POST /api/terminal/sessions/{id}/input` — as teclas, com o `X-SprintAI` de sempre.

A API recebe **cwd e perfil** — nunca um comando. Quem digita no shell é o dev.
"""

import asyncio
import json
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request, Response, status
from fastapi import Path as PathParam
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from config import get_settings
from core.errors import validation_error_handler
from security.local_guard import LocalGuardMiddleware, build_allowed_origins
from security.paths import PathNotAllowed, resolve_allowed
from security.process_env import clean_environment
from terminal.backend import PtyBackend, SpawnError, WinPtyBackend
from terminal.profiles import profiles
from terminal.sessions import SessionManager, SessionNotFound, TooManySessions

KEEPALIVE_SECONDS = 15
SESSION_ID = r"^[0-9a-f]{16}$"
SINCE_ITEM = re.compile(r"^([0-9a-f]{16}):(\d{1,12})$")
MAX_INPUT_CHARS = 65_536


class SessionCreate(BaseModel):
    cwd: str = Field(min_length=3, max_length=400)
    profile: str = Field(default="powershell", max_length=40)
    cols: int = Field(default=120, ge=10, le=500)
    rows: int = Field(default=30, ge=4, le=200)
    label: str | None = Field(default=None, max_length=80)


class InputIn(BaseModel):
    data: str = Field(max_length=MAX_INPUT_CHARS)


class ResizeIn(BaseModel):
    cols: int = Field(ge=10, le=500)
    rows: int = Field(ge=4, le=200)


def parse_since(raw: str | None) -> dict[str, int]:
    since: dict[str, int] = {}
    for item in (raw or "").split(","):
        match = SINCE_ITEM.match(item.strip())
        if match:
            since[match[1]] = int(match[2])
    return since


def frame(data: dict) -> str:
    return f"event: {data['type']}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def create_app(backend: PtyBackend | None = None, projects_root: Path | None = None) -> FastAPI:
    settings = get_settings()
    root = projects_root or settings.projects_root
    manager = SessionManager(
        backend or WinPtyBackend(settings.terminal_pty_backend),
        env_factory=clean_environment,
        max_sessions=settings.terminal_max_sessions,
        buffer_chars=settings.terminal_buffer_chars,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        # Desligar o terminal host fecha os shells — e a árvore de cada um.
        await manager.shutdown()

    # Sem /docs nem /openapi.json: um processo que segura shells não precisa de vitrine.
    app = FastAPI(
        title="SprintAI · terminal",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.manager = manager

    allowed_origins = build_allowed_origins(settings.front_origin, settings.terminal_port)
    app.add_middleware(LocalGuardMiddleware, allowed_origins=allowed_origins)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "X-SprintAI"],
    )
    app.add_exception_handler(RequestValidationError, validation_error_handler)

    def session_or_404(session_id: str):
        try:
            return manager.get(session_id)
        except SessionNotFound as exc:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Terminal não encontrado."
            ) from exc

    SessionId = Annotated[str, PathParam(pattern=SESSION_ID)]

    @app.get("/api/terminal/health")
    async def health():
        return {"ok": True, "sessions": len(manager.sessions)}

    @app.get("/api/terminal/profiles")
    async def list_profiles():
        return [{"id": p.id, "label": p.label} for p in profiles().values()]

    @app.get("/api/terminal/sessions")
    async def list_sessions():
        return [s.public() for s in manager.ordered()]

    @app.post("/api/terminal/sessions", status_code=status.HTTP_201_CREATED)
    async def create_session(payload: SessionCreate):
        profile = profiles().get(payload.profile)
        if profile is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Perfil desconhecido."
            )
        try:
            cwd = resolve_allowed(payload.cwd, [root])
        except PathNotAllowed as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
        if not cwd.is_dir():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Não é uma pasta.")
        try:
            session = await manager.create(
                profile,
                cwd=str(cwd),
                cols=payload.cols,
                rows=payload.rows,
                label=payload.label or cwd.name,
            )
        except TooManySessions as exc:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=f"Já há {manager.max_sessions} terminais abertos — feche um antes.",
            ) from exc
        except SpawnError as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        return session.public()

    @app.post("/api/terminal/sessions/{session_id}/input", status_code=204)
    async def send_input(session_id: SessionId, payload: InputIn):
        session_or_404(session_id)
        await manager.write(session_id, payload.data)
        return Response(status_code=204)

    @app.post("/api/terminal/sessions/{session_id}/resize", status_code=204)
    async def resize(session_id: SessionId, payload: ResizeIn):
        session_or_404(session_id)
        await manager.resize(session_id, payload.cols, payload.rows)
        return Response(status_code=204)

    @app.delete("/api/terminal/sessions/{session_id}", status_code=204)
    async def close(session_id: SessionId):
        session_or_404(session_id)
        await manager.close(session_id)
        return Response(status_code=204)

    @app.get("/api/terminal/stream")
    async def stream(request: Request, since: Annotated[str | None, Query(max_length=4000)] = None):
        wanted = parse_since(since)

        async def generator() -> AsyncIterator[str]:
            with manager.subscribe() as subscriber:
                # Sem `await` entre assinar e montar o atraso: nenhuma saída cai no meio.
                pending = manager.catch_up(wanted)
                for item in pending:
                    yield frame(item)
                while True:
                    if subscriber.overflowed:
                        yield frame({"type": "resync"})
                        return
                    if await request.is_disconnected():
                        return
                    try:
                        item = await asyncio.wait_for(subscriber.queue.get(), KEEPALIVE_SECONDS)
                    except TimeoutError:
                        yield ": ping\n\n"
                        continue
                    except asyncio.CancelledError:
                        return
                    yield frame(item)

        return StreamingResponse(
            generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
        )

    return app
