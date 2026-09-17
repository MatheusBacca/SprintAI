from typing import Literal

from pydantic import BaseModel


class DatabaseHealth(BaseModel):
    status: Literal["up", "down"]
    detail: str | None = None
    extensions: list[str] = []


class HealthResponse(BaseModel):
    app: str
    version: str
    status: Literal["ok", "degraded"]
    database: DatabaseHealth
