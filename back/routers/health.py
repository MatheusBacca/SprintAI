from fastapi import APIRouter

from schemas.health_schemas import HealthResponse
from services import health_service

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return await health_service.get_health()
