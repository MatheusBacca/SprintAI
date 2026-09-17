from schemas.health_schemas import DatabaseHealth
from services import health_service


async def test_health_ok_quando_banco_responde(client, monkeypatch):
    async def fake_check():
        return DatabaseHealth(status="up", extensions=["pg_trgm", "unaccent", "vector"])

    monkeypatch.setattr(health_service, "check_database", fake_check)

    response = await client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "SprintAI"
    assert body["database"]["extensions"] == ["pg_trgm", "unaccent", "vector"]


async def test_health_degradado_quando_banco_fora(client, monkeypatch):
    async def fake_check():
        return DatabaseHealth(status="down", detail="ConnectionRefusedError")

    monkeypatch.setattr(health_service, "check_database", fake_check)

    response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"


async def test_check_database_nao_explode_sem_banco(monkeypatch):
    async def boom():
        raise ConnectionRefusedError()

    monkeypatch.setattr(health_service, "get_pool", boom)

    result = await health_service.check_database()

    assert result.status == "down"
    assert result.detail == "ConnectionRefusedError"
