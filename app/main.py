"""Main app definition."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

from .config import (
    DynamicConfig,
    get_configurator_handler,
    _resilient_update_loop,
    _resilient_registry_check,
    get_redis_pool,
)
from .models import RootOutput
from .otel import server_request_hook, client_request_hook, client_response_hook, set_otel_config
from .dependencies.config import settings_dep, get_settings, config_dep
from .routers import condition

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

    config = DynamicConfig()
    async with get_configurator_handler(config, settings) as config_handler:
        app.state.config_handler = config_handler
        if settings.configurator.enabled:
            await _resilient_registry_check(config_handler)
            asyncio.create_task(_resilient_update_loop(config_handler))
        yield
    await app.state.redis.aclose()


app = FastAPI(lifespan=lifespan)
FastAPIInstrumentor.instrument_app(
    app,
    server_request_hook=server_request_hook,
    client_request_hook=client_request_hook,
    client_response_hook=client_response_hook,
)


app.include_router(condition.router)


@app.get("/")
async def root(settings: settings_dep, config: config_dep) -> RootOutput:
    """
    Get service info.

    :param settings: settings dependency
    :param config: config dependency
    :return: dictionary with public info
    """
    return RootOutput(**settings.model_dump(), **config.model_dump())
