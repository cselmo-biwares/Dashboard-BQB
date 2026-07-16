"""Application config dependencies."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from starlette.requests import Request

from app.config import Settings, DynamicConfig
from chatmessaging.http.client.configurator import RTConfiguratorClient


@lru_cache
def get_settings() -> Settings:
    """
    Get application settings.

    :return: Settings object
    """
    return Settings()


settings_dep = Annotated[Settings, Depends(get_settings)]


def get_configuration(request: Request) -> DynamicConfig:
    """Get the dynamic application configuration."""
    return request.app.state.config_handler.config


config_dep = Annotated[DynamicConfig, Depends(get_configuration)]


def get_configurator_client(request: Request) -> RTConfiguratorClient:
    """Get the configurator HTTP client."""
    return request.app.state.config_handler.configurator_client


configurator_client_dep = Annotated[RTConfiguratorClient, Depends(get_configurator_client)]
