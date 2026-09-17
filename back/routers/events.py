"""Stream de eventos locais (B11).

Formato Server-Sent Events, mas **não** consumido por `EventSource`: a API exige o
header `X-SprintAI` e o `EventSource` não manda header nenhum. O front lê com
`fetch` + `ReadableStream`, e a guarda local continua inteira.
"""

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from realtime.bus import Event, get_bus

router = APIRouter(tags=["events"])

# Sem tráfego, um comentário SSE de tempos em tempos mantém a conexão viva e faz o
# cliente perceber rápido quando a API cai.
KEEPALIVE_SECONDS = 20


def _frame(event: Event) -> str:
    data = json.dumps({**event.payload, "at": event.at.isoformat()}, ensure_ascii=False)
    return f"event: {event.kind}\ndata: {data}\n\n"


@router.get("/events")
async def stream(request: Request) -> StreamingResponse:
    async def generator() -> AsyncIterator[str]:
        async with get_bus().subscribe() as queue:
            yield ": conectado\n\n"
            while True:
                if await request.is_disconnected():
                    return
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_SECONDS)
                except TimeoutError:
                    yield ": ping\n\n"
                    continue
                except asyncio.CancelledError:
                    return
                yield _frame(event)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
