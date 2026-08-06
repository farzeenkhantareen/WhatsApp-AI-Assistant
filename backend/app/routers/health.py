"""Health check endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.api.schemas import HealthResponse
from app.config.settings import get_settings
from app.database.redis_client import redis_ping
from app.database.session import engine
from app.services.evolution_client import evolution_client

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(response: Response) -> HealthResponse:
    settings = get_settings()
    db_ok = False
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False

    redis_ok = await redis_ping()
    evolution_ok = await evolution_client.health()
    state = {}
    try:
        state = await evolution_client.get_connection_state()
    except Exception as exc:  # noqa: BLE001
        state = {"error": str(exc)}

    if db_ok and redis_ok:
        overall = "ok" if evolution_ok else "degraded"
        response.status_code = status.HTTP_200_OK
    else:
        overall = "unhealthy"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthResponse(
        status=overall,
        database=db_ok,
        redis=redis_ok,
        evolution=evolution_ok,
        instance=settings.instance_name,
        details={"connection": state},
    )

# Optimized health check formats

# Optimized health check formats
