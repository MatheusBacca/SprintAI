from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from config import LOOPBACK_HOSTS, get_settings
from core.errors import (
    credential_store_error_handler,
    database_unavailable_handler,
    integration_error_handler,
    validation_error_handler,
)
from database.pool import DatabaseUnavailable, close_pool
from integrations.errors import IntegrationError
from routers import (
    activity,
    connections,
    contexts,
    discovery,
    events,
    health,
    home,
    issues,
    notes,
    notifications,
    pr_status,
    preferences,
    progress,
    search,
    sprints,
    sync,
    week,
)
from security.credential_store import CredentialStoreError
from security.local_guard import LocalGuardMiddleware, build_allowed_origins
from services.sync.engine import get_sync_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = get_sync_engine()
    if get_settings().sync_autostart:
        engine.start_scheduler()
    yield
    await engine.stop()
    await close_pool()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)

    allowed_origins = build_allowed_origins(settings.front_origin, settings.api_port)

    # Ordem importa: o último middleware adicionado é o mais externo. O CORS responde
    # o preflight antes; a guarda filtra todo o resto.
    app.add_middleware(LocalGuardMiddleware, allowed_origins=allowed_origins)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-SprintAI"],
    )

    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(IntegrationError, integration_error_handler)
    app.add_exception_handler(CredentialStoreError, credential_store_error_handler)
    app.add_exception_handler(DatabaseUnavailable, database_unavailable_handler)

    app.include_router(health.router, prefix="/api")
    app.include_router(activity.router, prefix="/api")
    app.include_router(notifications.router, prefix="/api")
    app.include_router(home.router, prefix="/api")
    app.include_router(progress.router, prefix="/api")
    app.include_router(events.router, prefix="/api")
    app.include_router(connections.router, prefix="/api")
    app.include_router(discovery.router, prefix="/api")
    app.include_router(sync.router, prefix="/api")
    app.include_router(pr_status.router, prefix="/api")
    app.include_router(sprints.router, prefix="/api")
    app.include_router(issues.router, prefix="/api")
    app.include_router(notes.router, prefix="/api")
    app.include_router(contexts.router, prefix="/api")
    app.include_router(search.router, prefix="/api")
    app.include_router(week.router, prefix="/api")
    app.include_router(preferences.router, prefix="/api")
    return app


app = create_app()


if __name__ == "__main__":
    settings = get_settings()
    if settings.api_host not in LOOPBACK_HOSTS:
        raise SystemExit(f"API_HOST={settings.api_host} recusado: a API só escuta em loopback.")
    back_dir = Path(__file__).resolve().parent
    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
        app_dir=str(back_dir),
        reload_dirs=[str(back_dir)],
        # O stream de eventos (`GET /api/events`) fica aberto de propósito: sem teto,
        # o uvicorn esperaria por ele para sempre a cada reload ou Ctrl+C.
        timeout_graceful_shutdown=5,
        # Instalar pacote ou rodar testes não pode derrubar um sync em andamento.
        reload_excludes=[".venv/*", "tests/*", "*.pyc"],
    )
