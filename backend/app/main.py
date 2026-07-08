"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import get_settings
from app.database.redis_client import close_redis, get_redis
from app.database.session import close_db, init_db
from app.middleware.logging_middleware import RequestLoggingMiddleware
from app.routers import conversations, health, memory, messages, send, webhook
from app.services.evolution_client import evolution_client
from app.services.openrouter_client import openrouter_client
from app.utils.logging import setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    logger.info("Starting %s (%s)", settings.app_name, settings.app_env)

    await init_db()
    await get_redis()
    await evolution_client.start()
    await openrouter_client.start()

    try:
        bootstrap = await evolution_client.ensure_instance()
        logger.info("Evolution bootstrap result keys=%s", list(bootstrap.keys()))
        state = bootstrap.get("state") or {}
        logger.info("Evolution connection state=%s", state)
    except Exception as exc:  # noqa: BLE001
        logger.error("Evolution bootstrap failed (will retry on webhook/health): %s", exc)

    yield

    logger.info("Shutting down %s", settings.app_name)
    await openrouter_client.close()
    await evolution_client.close()
    await close_redis()
    await close_db()


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description=(
            "Production WhatsApp AI Assistant powered by Evolution API and OpenRouter. "
            "Receives webhooks, maintains conversation memory, and replies automatically."
        ),
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_middleware(RequestLoggingMiddleware)

    application.include_router(webhook.router)
    application.include_router(send.router)
    application.include_router(health.router)
    application.include_router(conversations.router)
    application.include_router(messages.router)
    application.include_router(memory.router)

    return application


app = create_app()

# White-space normalized
