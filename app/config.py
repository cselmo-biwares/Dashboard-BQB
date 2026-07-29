"""App configuration."""

import logging
from typing import Literal

import httpx
from chatmessaging.communication.configurator import ConfigurationUpdateReader, ConfigurationHandler
from chatmessaging.http.client.configurator import RTConfiguratorClient
from chatmessaging.http.schemas.configurator import ModuleType

from pydantic import Field, AnyHttpUrl, RedisDsn, PostgresDsn, BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict
from redis import asyncio as redis
from redis.asyncio import Redis
from tenacity import AsyncRetrying, wait_exponential, before_sleep_log, retry_if_exception_type

logger = logging.getLogger(__name__)


class ConfiguratorSettings(BaseModel):
    """Configurator settings."""

    enabled: bool = Field(description="Enable dynamic configuration. If False, use defaults.", default=False)
    url: AnyHttpUrl = Field(description="URL of the configurator", default=AnyHttpUrl("http://localhost:8000"))
    timeout: int = Field(description="Timeout in seconds", default=60)


class ConversationManagerSettings(BaseModel):
    """Conversation Manager client settings."""

    url: AnyHttpUrl = Field(
        description="URL of the Conversation Manager service", default=AnyHttpUrl("http://localhost:8001")
    )
    timeout: int = Field(description="Timeout in seconds", default=30)


class BedrockSettings(BaseModel):
    """AWS Bedrock (AnthropicBedrock) settings."""

    region_name: str = Field(description="AWS region for Bedrock", default="us-east-1")
    access_key_id: str = Field(description="AWS access key id", default="")
    secret_access_key: str = Field(description="AWS secret access key", default="")
    model: str = Field(description="Bedrock model id", default="")
    max_tokens: int = Field(description="Max tokens per completion", default=4000)
    temperature: float = Field(description="Sampling temperature", default=0.0)


class IngestionSettings(BaseModel):
    """Conversation ingestion pipeline settings."""

    min_age_hours: int = Field(description="Minimum conversation age (hours) before processing it", default=2)
    page_size: int = Field(description="Conversations fetched per page from the Conversation Manager", default=50)
    lock_ttl_seconds: int = Field(description="TTL of the Redis lock guarding concurrent ingestion runs", default=3600)


class AuthSettings(BaseModel):
    """Authentication settings.

    No defaults for secrets/admin credentials: a misconfigured deployment should fail to
    start loudly, rather than silently run with a weak/well-known default.
    """

    jwt_secret: str = Field(description="Secret used to sign session JWTs")
    jwt_algorithm: str = Field(description="JWT signing algorithm", default="HS256")
    session_hours: int = Field(description="Hours before a session token expires", default=12)
    admin_username: str = Field(description="The single admin account's username")
    admin_password: str = Field(description="The single admin account's password")


class RedisPoolConfig(BaseModel):
    """Redis connection pool configuration."""

    max_connections: int = Field(description="Maximum number of connections in the pool", default=10)
    socket_timeout: float | None = Field(
        description="Seconds to wait for a response on an established connection", default=None
    )
    socket_connect_timeout: float | None = Field(
        description="Seconds to wait when opening a new connection", default=None
    )
    retry_on_timeout: bool = Field(description="Retry commands that time out", default=False)
    health_check_interval: int = Field(description="Seconds between background health checks (0 = disabled)", default=0)


class Settings(BaseSettings):
    """Application settings. Automatically retrieved form environment variables."""

    # env_file lets Settings() load .env directly (e.g. when invoked from `alembic`,
    # which doesn't go through uvicorn's --env-file flag). Real environment variables
    # (Docker/K8s) still take precedence over the file when both are present.
    model_config = SettingsConfigDict(
        env_nested_delimiter="__", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str
    env: Literal["local", "dev", "qa", "prod"] = Field(
        description="Environment the service is running in", default="local"
    )

    configurator: ConfiguratorSettings = Field(description="Configurator settings", default=ConfiguratorSettings())
    redis_url: RedisDsn = Field(description="Redis URL", default="redis://localhost:6379")
    redis_pool: RedisPoolConfig = Field(description="Redis connection pool settings", default=RedisPoolConfig())

    db_url: PostgresDsn = Field(
        description="Destination Postgres URL (async driver)",
        default=PostgresDsn("postgresql+asyncpg://postgres:postgres@localhost:5432/dashboard_bqb"),
    )
    conversation_manager: ConversationManagerSettings = Field(
        description="Conversation Manager client settings", default=ConversationManagerSettings()
    )
    bedrock: BedrockSettings = Field(description="AWS Bedrock settings", default=BedrockSettings())
    ingestion: IngestionSettings = Field(description="Ingestion pipeline settings", default=IngestionSettings())
    auth: AuthSettings


class DynamicConfig(BaseModel):
    """A dynamic config to handle with the configurator service."""

    configurable_int: int = Field(description="Example int configurable", default=23)
    configurable_str: str = Field(description="Example str configurable", default="base config")


def get_configurator_handler(config: DynamicConfig, settings: Settings) -> ConfigurationHandler:
    """Get the configurator handler."""
    module_type = ModuleType.other  # TODO: Change me
    module_name = settings.app_name
    config_version = "1.0.0"

    configurator_client = RTConfiguratorClient(
        base_url=settings.configurator.url.encoded_string(), timeout=settings.configurator.timeout
    )
    configurator_update_reader = ConfigurationUpdateReader(
        redis_url=settings.redis_url.encoded_string(), module_type=module_type, module_name=module_name
    )

    config_handler = ConfigurationHandler(
        module_type=module_type,
        module_name=module_name,
        config_version=config_version,
        config=config,
        configurator_client=configurator_client,
        configurator_update_reader=configurator_update_reader,
    )
    return config_handler


async def _resilient_update_loop(config_handler) -> None:
    async for attempt in AsyncRetrying(
        wait=wait_exponential(multiplier=1, min=2, max=60),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    ):
        with attempt:
            await config_handler.configurator_update_reader._sender.connect()
            await config_handler.update_loop()


async def _resilient_registry_check(config_handler: ConfigurationHandler):
    async for attempt in AsyncRetrying(
        retry=retry_if_exception_type(httpx.HTTPError),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    ):
        with attempt:
            await config_handler.check_registry()


async def get_redis_pool(settings: Settings) -> Redis:
    """Get a redis connection pool."""
    pool_cfg = settings.redis_pool
    redis_client = redis.Redis.from_url(
        settings.redis_url.encoded_string(),
        decode_responses=True,
        max_connections=pool_cfg.max_connections,
        socket_timeout=pool_cfg.socket_timeout,
        socket_connect_timeout=pool_cfg.socket_connect_timeout,
        retry_on_timeout=pool_cfg.retry_on_timeout,
        health_check_interval=pool_cfg.health_check_interval,
    )
    return redis_client
