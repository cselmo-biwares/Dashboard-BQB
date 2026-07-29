"""Main app definition."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from chatmessaging.http.client.convmanager import ConversationManagerClient
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

from .config import (
    DynamicConfig,
    get_configurator_handler,
    _resilient_update_loop,
    _resilient_registry_check,
    get_redis_pool,
)
from .db.base import create_engine as create_db_engine, create_sessionmaker as create_db_sessionmaker
from .ingestion.llm import create_llm_client
from .ingestion.service import reap_stale_runs
from .models import RootOutput
from .otel import server_request_hook, client_request_hook, client_response_hook, set_otel_config
from .dependencies.config import settings_dep, get_settings, config_dep
from .routers import audit, auth, condition, conversations, documents, ingestion, notes, prompts, stats, topics, users

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for an application.

    :param app: fastapi app
    :return:
    """
    settings = get_settings()

    set_otel_config(settings)
    HTTPXClientInstrumentor().instrument()

    app.state.redis = await get_redis_pool(settings)

    db_engine = create_db_engine(settings.db_url.encoded_string())
    app.state.db_engine = db_engine
    app.state.db_sessionmaker = create_db_sessionmaker(db_engine)

    app.state.llm_client = create_llm_client(settings.bedrock)

    async with app.state.db_sessionmaker() as session:
        await reap_stale_runs(session, app.state.redis)

    config = DynamicConfig()
    async with (
        get_configurator_handler(config, settings) as config_handler,
        ConversationManagerClient(
            base_url=settings.conversation_manager.url.encoded_string(),
            timeout=settings.conversation_manager.timeout,
        ) as conversation_manager_client,
    ):
        app.state.config_handler = config_handler
        app.state.conversation_manager_client = conversation_manager_client
        if settings.configurator.enabled:
            await _resilient_registry_check(config_handler)
            asyncio.create_task(_resilient_update_loop(config_handler))
        yield
    await app.state.redis.aclose()
    await db_engine.dispose()


app = FastAPI(lifespan=lifespan)

# Read directly from the environment (not via the full Settings object) so importing this
# module never requires app-wide settings (e.g. APP_NAME) to be set - middleware must be
# registered before the app starts, so it can't be deferred to a request-time dependency.
_cors_origins = [origin.strip() for origin in os.environ.get("CORS_ORIGINS", "").split(",") if origin.strip()]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

FastAPIInstrumentor.instrument_app(
    app,
    server_request_hook=server_request_hook,
    client_request_hook=client_request_hook,
    client_response_hook=client_response_hook,
)


app.include_router(condition.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(audit.router)
app.include_router(ingestion.router)
app.include_router(documents.router)
app.include_router(topics.router)
app.include_router(stats.router)
app.include_router(conversations.router)
app.include_router(prompts.router)
app.include_router(notes.router)


@app.get("/")
async def root(settings: settings_dep, config: config_dep) -> RootOutput:
    """
    Get service info.

    :param settings: settings dependency
    :param config: config dependency
    :return: dictionary with public info
    """
    return RootOutput(**settings.model_dump(), **config.model_dump())
