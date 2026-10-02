"""Ambiente dos processos que o SprintAI abre para o dev (terminal, VS Code, Windows Terminal).

O processo herda o ambiente do usuário, menos o que é configuração do próprio SprintAI —
os campos do `Settings` (`DB_PASSWORD`, `API_PORT`, …) e qualquer `SPRINTAI_*`. Um shell
aberto pelo SprintAI não pode sair sabendo a senha do banco local só porque nasceu de lá.
"""

import os

from config import Settings


def sprintai_variables() -> set[str]:
    return {name.upper() for name in Settings.model_fields}


def clean_environment(extra: dict[str, str] | None = None) -> dict[str, str]:
    own = sprintai_variables()
    env = {
        key: value
        for key, value in os.environ.items()
        if key.upper() not in own and not key.upper().startswith("SPRINTAI_")
    }
    env.update(extra or {})
    return env
