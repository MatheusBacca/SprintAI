"""Abrir a pasta de um repo no VS Code ou no Windows Terminal (botões do Workspace).

Comando fixo e caminho validado pela guarda de caminho antes de chegar aqui. Os dois são
chamados pelo executável, nunca por um `.cmd`: o `code` que está no PATH é um
`code.cmd`, e argumento passado a arquivo de lote passa pelo `cmd.exe`, onde `&` ou `|`
no nome de uma pasta viraria outro comando. O VS Code é aberto pelo `Code.exe`, que mora
duas pastas acima do `bin\\code.cmd`.

O `wt` separa subcomandos por `;` na própria linha de comando — pasta com `;` no nome é
recusada em vez de escapada.
"""

import shutil
import subprocess
import sys
from pathlib import Path

from security.process_env import clean_environment

_DETACHED = (
    subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    if sys.platform == "win32"
    else 0
)


class LauncherUnavailable(Exception):
    pass


def vscode_executable() -> Path | None:
    cli = shutil.which("code")
    if cli is None:
        return None
    candidate = Path(cli).resolve().parent.parent / "Code.exe"
    return candidate if candidate.is_file() else None


def windows_terminal_executable() -> Path | None:
    found = shutil.which("wt")
    return Path(found) if found else None


def command_for(target: str, folder: Path) -> list[str]:
    if target == "ide":
        exe = vscode_executable()
        if exe is None:
            raise LauncherUnavailable("VS Code não encontrado (o `code` não está no PATH).")
        return [str(exe), str(folder)]
    if target == "terminal":
        if ";" in str(folder):
            raise LauncherUnavailable("O Windows Terminal não abre pasta com ';' no nome.")
        exe = windows_terminal_executable()
        if exe is None:
            raise LauncherUnavailable("Windows Terminal não encontrado (`wt`).")
        return [str(exe), "-d", str(folder)]
    raise LauncherUnavailable("Destino desconhecido.")


def launch(target: str, folder: Path) -> None:
    """Sobe o programa solto da API: fechar o SprintAI não fecha o VS Code."""
    command = command_for(target, folder)
    subprocess.Popen(
        command,
        cwd=str(folder),
        env=clean_environment(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=_DETACHED,
        close_fds=True,
    )
