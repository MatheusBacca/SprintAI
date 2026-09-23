"""Barramento de eventos em memória (B11).

Um processo, um dev: pub/sub com `asyncio.Queue`, sem Redis nem broker. Quem escreve
no banco publica o que mudou; o `GET /api/events` transmite para as abas abertas.

A fila de cada assinante tem teto: uma aba lenta (ou em segundo plano) descarta o
evento mais antigo em vez de segurar o publicador — o front recarrega do zero quando
volta ao foco, então perder um aviso não corrompe nada.
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from core.logger import get_logger

logger = get_logger(__name__)

QUEUE_SIZE = 64

SYNC_FINISHED = "sync.finished"
ACTIVITY_NEW = "activity.new"
NOTE_CHANGED = "note.changed"
CONTEXT_CHANGED = "context.changed"
HARNESS_CHANGED = "harness.changed"
PROGRESS_CHANGED = "progress.changed"
# O dev mudou status ou Story Points pelo SprintAI (a escrita já está no espelho).
ISSUE_CHANGED = "issue.changed"


@dataclass(frozen=True)
class Event:
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    at: datetime = field(default_factory=lambda: datetime.now(UTC))


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[Event]] = set()

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def publish(self, kind: str, payload: dict[str, Any] | None = None) -> None:
        event = Event(kind=kind, payload=payload or {})
        for queue in list(self._subscribers):
            if queue.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(event)

    @contextlib.asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[Event]]:
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=QUEUE_SIZE)
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)


_bus = EventBus()


def get_bus() -> EventBus:
    return _bus


def publish(kind: str, payload: dict[str, Any] | None = None) -> None:
    """Atalho para quem só quer avisar (serviços de escrita, sync)."""
    _bus.publish(kind, payload)
