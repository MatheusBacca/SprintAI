"""Entrada do terminal host (`uv run python terminal_host.py`).

Processo à parte da API, **sem reload**: é ele que segura os shells dos terminais do
Workspace, e um reload da API não pode derrubá-los. Ver `terminal/app.py`.
"""

import uvicorn

from config import LOOPBACK_HOSTS, get_settings
from terminal.app import create_app

app = create_app()

if __name__ == "__main__":
    settings = get_settings()
    if settings.api_host not in LOOPBACK_HOSTS:
        raise SystemExit(
            f"API_HOST={settings.api_host} recusado: o terminal só escuta em loopback."
        )
    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.terminal_port,
        # O stream fica aberto de propósito; sem teto, desligar esperaria por ele.
        timeout_graceful_shutdown=3,
        # A URL do stream e do input não tem segredo, mas o log de acesso a cada tecla
        # enchia o `.logs/terminal.log` à toa.
        access_log=False,
    )
