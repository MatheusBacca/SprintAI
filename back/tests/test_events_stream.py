"""B11 — barramento em memória e o stream local de eventos."""

import asyncio
import json

import pytest

from realtime import bus as bus_module
from realtime.bus import ACTIVITY_NEW, NOTE_CHANGED, QUEUE_SIZE, Event, EventBus
from routers.events import _frame, stream


async def test_assinante_recebe_o_que_foi_publicado():
    bus = EventBus()
    async with bus.subscribe() as queue:
        bus.publish(NOTE_CHANGED, {"id": 7})
        event = queue.get_nowait()

    assert (event.kind, event.payload) == (NOTE_CHANGED, {"id": 7})
    assert bus.subscriber_count == 0


async def test_sem_assinante_publicar_nao_quebra():
    EventBus().publish(ACTIVITY_NEW, {"count": 1})


async def test_fila_cheia_descarta_o_mais_antigo_em_vez_de_travar():
    bus = EventBus()
    async with bus.subscribe() as queue:
        for i in range(QUEUE_SIZE + 5):
            bus.publish(NOTE_CHANGED, {"id": i})
        assert queue.qsize() == QUEUE_SIZE
        # O mais velho caiu fora; o mais novo ficou.
        assert queue.get_nowait().payload["id"] == 5


async def test_cada_aba_recebe_a_sua_copia():
    bus = EventBus()
    async with bus.subscribe() as uma, bus.subscribe() as outra:
        bus.publish(NOTE_CHANGED, {"id": 1})
        assert uma.get_nowait().payload["id"] == outra.get_nowait().payload["id"] == 1


def test_frame_sse_leva_o_tipo_e_o_horario():
    frame = _frame(Event(kind=NOTE_CHANGED, payload={"id": 7}))
    linhas = frame.strip().splitlines()

    assert linhas[0] == f"event: {NOTE_CHANGED}"
    assert linhas[1].startswith('data: {"id": 7, "at": "')
    assert frame.endswith("\n\n")


class FakeRequest:
    """O `stream` só usa `is_disconnected` do Request."""

    def __init__(self, disconnected: bool = False) -> None:
        self._disconnected = disconnected

    async def is_disconnected(self) -> bool:
        return self._disconnected


async def test_stream_entrega_evento_publicado_depois_da_conexao():
    response = await stream(FakeRequest())
    frames = response.body_iterator

    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache, no-transform"
    assert await asyncio.wait_for(anext(frames), timeout=2) == ": conectado\n\n"

    bus_module.publish(ACTIVITY_NEW, {"count": 3})
    frame = await asyncio.wait_for(anext(frames), timeout=2)
    await frames.aclose()

    kind, data = frame.strip().splitlines()
    assert kind == f"event: {ACTIVITY_NEW}"
    assert json.loads(data.removeprefix("data: "))["count"] == 3


async def test_stream_manda_ping_quando_nao_ha_nada(monkeypatch):
    monkeypatch.setattr("routers.events.KEEPALIVE_SECONDS", 0.01)
    frames = (await stream(FakeRequest())).body_iterator

    await anext(frames)  # ": conectado"
    assert await asyncio.wait_for(anext(frames), timeout=2) == ": ping\n\n"
    await frames.aclose()


async def test_aba_fechada_encerra_o_stream():
    frames = (await stream(FakeRequest(disconnected=True))).body_iterator

    assert await anext(frames) == ": conectado\n\n"
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(anext(frames), timeout=2)
    # E o assinante saiu do barramento.
    assert bus_module.get_bus().subscriber_count == 0


async def test_stream_exige_o_header_da_guarda_local(raw_client):
    response = await raw_client.get("/api/events")
    assert response.status_code == 403
