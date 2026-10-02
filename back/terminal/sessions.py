"""Sessões do terminal host: cada uma é um shell vivo, com a saída numerada (B17).

A saída de cada sessão é uma sequência só, contada em caracteres desde que ela abriu
(`offset`). O que passou fica num buffer circular em memória — o bastante para redesenhar
a tela —, e quem se conecta ao stream diz até onde já tem (`since`): recebe só o que falta,
ou um `reset` com o buffer inteiro se ficou para trás dele. É isso que deixa recarregar a
página sem perder o terminal.

Nada da saída vai para log, banco ou disco: ela pode ter qualquer coisa que o dev digitou.

A leitura do PTY é bloqueante e roda numa thread por sessão; tudo o que mexe no estado
(buffer, assinantes) roda no loop do asyncio, chamado pela thread com
`call_soon_threadsafe`.
"""

import asyncio
import contextlib
import secrets
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from terminal.backend import PtyBackend, PtyHandle
from terminal.profiles import Profile

SUBSCRIBER_QUEUE = 512


class TooManySessions(Exception):
    pass


class SessionNotFound(Exception):
    pass


@dataclass
class Session:
    id: str
    profile: Profile
    label: str
    cwd: str
    cols: int
    rows: int
    created_at: datetime
    handle: PtyHandle
    buffer_chars: int
    chunks: deque[str] = field(default_factory=deque)
    buffer_start: int = 0
    offset: int = 0
    size: int = 0
    alive: bool = True
    exit_code: int | None = None
    write_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def append(self, text: str) -> int:
        start = self.offset
        self.chunks.append(text)
        self.offset += len(text)
        self.size += len(text)
        while self.size > self.buffer_chars and len(self.chunks) > 1:
            dropped = self.chunks.popleft()
            self.size -= len(dropped)
            self.buffer_start += len(dropped)
        return start

    def since(self, offset: int | None) -> tuple[bool, int, str]:
        """(reset, offset do texto, texto) para quem já tem até `offset`."""
        if offset is None or offset < self.buffer_start or offset > self.offset:
            return True, self.buffer_start, "".join(self.chunks)
        if offset == self.offset:
            return False, offset, ""
        return False, offset, "".join(self.chunks)[offset - self.buffer_start :]

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "profile": self.profile.id,
            "label": self.label,
            "cwd": self.cwd,
            "cols": self.cols,
            "rows": self.rows,
            "created_at": self.created_at.isoformat(),
            "alive": self.alive,
            "exit_code": self.exit_code,
            "offset": self.offset,
        }


class Subscriber:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE)
        # Cliente lento demais: em vez de jogar saída fora no meio (o terminal desenharia
        # errado), o stream acaba e o cliente volta com o `since` — e recebe o que falta.
        self.overflowed = False

    def push(self, frame: dict[str, Any]) -> None:
        if self.overflowed:
            return
        try:
            self.queue.put_nowait(frame)
        except asyncio.QueueFull:
            self.overflowed = True


class SessionManager:
    def __init__(
        self,
        backend: PtyBackend,
        *,
        env_factory: Callable[[], dict[str, str]],
        max_sessions: int = 12,
        buffer_chars: int = 200_000,
    ) -> None:
        self.backend = backend
        self.env_factory = env_factory
        self.max_sessions = max_sessions
        self.buffer_chars = buffer_chars
        self.sessions: dict[str, Session] = {}
        self.subscribers: set[Subscriber] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    # --- Ciclo de vida -----------------------------------------------------------------

    async def create(
        self, profile: Profile, *, cwd: str, cols: int, rows: int, label: str
    ) -> Session:
        if len(self.sessions) >= self.max_sessions:
            raise TooManySessions(self.max_sessions)
        self._loop = asyncio.get_running_loop()
        handle = await asyncio.to_thread(
            self.backend.spawn,
            list(profile.argv),
            cwd=cwd,
            env=self.env_factory(),
            cols=cols,
            rows=rows,
        )
        session = Session(
            id=secrets.token_hex(8),
            profile=profile,
            label=label,
            cwd=cwd,
            cols=cols,
            rows=rows,
            created_at=datetime.now(UTC),
            handle=handle,
            buffer_chars=self.buffer_chars,
        )
        self.sessions[session.id] = session
        threading.Thread(
            target=self._read_loop, args=(session.id, handle), daemon=True, name=f"pty-{session.id}"
        ).start()
        self._publish({"type": "opened", "session": session.public()})
        return session

    def get(self, session_id: str) -> Session:
        session = self.sessions.get(session_id)
        if session is None:
            raise SessionNotFound(session_id)
        return session

    def ordered(self) -> list[Session]:
        return sorted(self.sessions.values(), key=lambda s: s.created_at)

    async def write(self, session_id: str, data: str) -> None:
        session = self.get(session_id)
        if not session.alive:
            return
        # Um POST por rajada de teclas: o lock mantém a ordem entre eles.
        async with session.write_lock:
            await asyncio.to_thread(session.handle.write, data)

    async def resize(self, session_id: str, cols: int, rows: int) -> None:
        session = self.get(session_id)
        session.cols, session.rows = cols, rows
        if session.alive:
            await asyncio.to_thread(session.handle.resize, cols, rows)

    async def close(self, session_id: str) -> None:
        session = self.sessions.pop(session_id, None)
        if session is None:
            raise SessionNotFound(session_id)
        if session.alive:
            await asyncio.to_thread(session.handle.kill)
        self._publish({"type": "closed", "s": session_id})

    async def shutdown(self) -> None:
        for session_id in list(self.sessions):
            with contextlib.suppress(SessionNotFound):
                await self.close(session_id)

    # --- Thread de leitura -----------------------------------------------------------------

    def _read_loop(self, session_id: str, handle: PtyHandle) -> None:
        loop = self._loop
        while True:
            data = handle.read()
            if data:
                loop.call_soon_threadsafe(self._on_output, session_id, data)
                continue
            if not handle.alive():
                break
            time.sleep(0.02)
        loop.call_soon_threadsafe(self._on_exit, session_id, handle.exit_code())

    def _on_output(self, session_id: str, data: str) -> None:
        session = self.sessions.get(session_id)
        if session is None:
            return
        start = session.append(data)
        self._publish({"type": "out", "s": session_id, "o": start, "d": data})

    def _on_exit(self, session_id: str, code: int | None) -> None:
        session = self.sessions.get(session_id)
        if session is None:
            return
        session.alive = False
        session.exit_code = code
        self._publish({"type": "exit", "s": session_id, "code": code})

    # --- Stream ---------------------------------------------------------------------------

    def _publish(self, frame: dict[str, Any]) -> None:
        for subscriber in list(self.subscribers):
            subscriber.push(frame)

    def catch_up(self, since: dict[str, int]) -> list[dict[str, Any]]:
        """O que cada sessão tem além do `since` do cliente: `out` com o que falta, ou `reset`
        com o buffer inteiro para quem nunca viu a sessão (ou ficou para trás dele)."""
        frames: list[dict[str, Any]] = [
            {"type": "hello", "sessions": [s.public() for s in self.ordered()]}
        ]
        for session in self.ordered():
            reset, offset, text = session.since(since.get(session.id))
            if reset:
                frames.append({"type": "reset", "s": session.id, "o": offset, "d": text})
            elif text:
                frames.append({"type": "out", "s": session.id, "o": offset, "d": text})
            if not session.alive:
                frames.append({"type": "exit", "s": session.id, "code": session.exit_code})
        return frames

    @contextlib.contextmanager
    def subscribe(self):
        subscriber = Subscriber()
        self.subscribers.add(subscriber)
        try:
            yield subscriber
        finally:
            self.subscribers.discard(subscriber)
