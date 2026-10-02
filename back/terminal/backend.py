"""PTY do terminal host: o processo de verdade por trás de cada terminal da tela (B17).

Usa o `winpty.PTY` do pywinpty direto, com uma thread de leitura própria — o
`PtyProcess` do pacote abre um socket TCP em loopback por sessão só para entregar a saída,
o que aqui não precisa.

**Backend WinPTY (1), não ConPTY (0).** O spike W0 (02/10/2026) mostrou que o ConPTY do
pywinpty cria o processo com o Ctrl+C desligado para os filhos — sem Ctrl+C não dá para
parar um `npm run dev`. O WinPTY passou em acentos, Ctrl+C, redimensionar e PSReadLine.
`TERMINAL_PTY_BACKEND` troca, para reavaliar quando o pywinpty corrigir.

**Encerrar** é `taskkill /T /F` no shell — a árvore inteira, senão um `npm run dev` aberto
pelo shell ficaria órfão rodando depois da aba fechada.
"""

import os
import shutil
import subprocess
import sys
from typing import Protocol

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


class PtyHandle(Protocol):
    pid: int | None

    def read(self) -> str:
        """Bloqueia até ter saída. String vazia + `alive` falso = o processo acabou."""

    def write(self, data: str) -> None: ...

    def resize(self, cols: int, rows: int) -> None: ...

    def alive(self) -> bool: ...

    def exit_code(self) -> int | None: ...

    def kill(self) -> None: ...


class PtyBackend(Protocol):
    def spawn(
        self, argv: list[str], *, cwd: str, env: dict[str, str], cols: int, rows: int
    ) -> PtyHandle: ...


class SpawnError(Exception):
    pass


class WinPtyHandle:
    def __init__(self, pty) -> None:
        self._pty = pty
        self.pid = pty.pid

    def read(self) -> str:
        try:
            data = self._pty.read(blocking=True)
        except Exception:  # noqa: BLE001 — EOF e erro de leitura terminam a sessão igual
            return ""
        return data or ""

    def write(self, data: str) -> None:
        if self._pty.isalive():
            self._pty.write(data)

    def resize(self, cols: int, rows: int) -> None:
        if self._pty.isalive():
            self._pty.set_size(cols, rows)

    def alive(self) -> bool:
        try:
            return bool(self._pty.isalive()) and not self._pty.iseof()
        except Exception:  # noqa: BLE001
            return False

    def exit_code(self) -> int | None:
        try:
            return self._pty.get_exitstatus()
        except Exception:  # noqa: BLE001
            return None

    def kill(self) -> None:
        if self.pid:
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(self.pid)],
                capture_output=True,
                creationflags=_CREATE_NO_WINDOW,
                check=False,
            )
        try:
            self._pty.cancel_io()
        except Exception:  # noqa: BLE001
            pass


class WinPtyBackend:
    def __init__(self, backend: int = 1) -> None:
        self.backend = backend

    def spawn(
        self, argv: list[str], *, cwd: str, env: dict[str, str], cols: int, rows: int
    ) -> WinPtyHandle:
        from winpty import PTY  # só existe no Windows

        # O winpty quer o caminho inteiro do executável; o perfil já manda, o teste não.
        exe = argv[0] if os.path.isabs(argv[0]) else shutil.which(argv[0], path=env.get("PATH"))
        if not exe:
            raise SpawnError("Executável do terminal não encontrado.")
        pty = PTY(cols, rows, backend=self.backend)
        cmdline = " " + subprocess.list2cmdline(argv[1:]) if len(argv) > 1 else None
        environment = "\0".join(f"{k}={v}" for k, v in env.items()) + "\0"
        try:
            pty.spawn(exe, cmdline=cmdline, cwd=cwd, env=environment)
        except Exception as exc:  # noqa: BLE001
            raise SpawnError("Não foi possível abrir o terminal.") from exc
        return WinPtyHandle(pty)
