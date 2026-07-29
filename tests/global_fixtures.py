"""Utils for testing."""

from typing import AsyncGenerator, Generator
from unittest.mock import patch, AsyncMock, MagicMock

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.auth import AuthenticatedUser
from app.config import AuthSettings, Settings, ConfiguratorSettings
from app.db.base import Base
from app.db import models  # noqa: F401 registers ORM models on Base.metadata
from app.dependencies.auth import get_current_user
from app.dependencies.config import get_settings, get_configurator_client
from app.dependencies.conversation_manager import get_conversation_manager_client
from app.dependencies.db import get_db_session
from app.dependencies.llm import get_llm_client


def override_get_current_user() -> AuthenticatedUser:
    """Return the default test identity: admin, so every protected route is reachable without a real login."""
    return AuthenticatedUser(username="test-admin", role="admin")


def get_settings_override():
    """
    Get application settings override.

    :return:
    """
    return Settings(
        app_name="test_app",
        auth=AuthSettings(
            jwt_secret="test-jwt-secret", admin_username="test-admin-user", admin_password="test-admin-pw"
        ),
    )


@pytest.fixture(scope="function")
def app_settings() -> Settings:
    """
    Get settings as a pytest.fixture.

    :return:
    """
    return get_settings_override()


@pytest.fixture(scope="function")
def test_client() -> Generator[TestClient, None, None]:
    """
    Get a test client that runs the full app lifespan with external calls mocked.

    Uses TestClient as a context manager so the lifespan (and therefore
    app.state.config_handler) is properly initialised before tests run.

    :return:
    """
    from app.main import app

    app.dependency_overrides[get_settings] = get_settings_override
    app.dependency_overrides[get_current_user] = override_get_current_user

    with (
        patch("app.main.get_settings", return_value=get_settings_override()),
        patch("app.main.set_otel_config"),
        patch("app.config.redis.Redis.from_url", return_value=fakeredis.aioredis.FakeRedis()),
        patch("app.config.RTConfiguratorClient"),
        patch("app.config.ConfigurationUpdateReader"),
        patch("app.config.ConfigurationHandler.check_registry", new_callable=AsyncMock),
        patch("app.config.ConfigurationHandler.update_loop", new_callable=AsyncMock),
    ):
        with TestClient(app) as client:
            yield client


@pytest.fixture(scope="function")
def test_client_redis_down() -> Generator[TestClient, None, None]:
    """Test client with a Redis instance that refuses all connections."""
    from app.main import app

    app.dependency_overrides[get_settings] = get_settings_override
    app.dependency_overrides[get_current_user] = override_get_current_user

    fake_server = fakeredis.FakeServer()
    fake_server.connected = False

    with (
        patch("app.main.get_settings", return_value=get_settings_override()),
        patch("app.main.set_otel_config"),
        patch("app.config.redis.Redis.from_url", return_value=fakeredis.aioredis.FakeRedis(server=fake_server)),
        patch("app.config.RTConfiguratorClient"),
        patch("app.config.ConfigurationUpdateReader"),
        patch("app.config.ConfigurationHandler.check_registry", new_callable=AsyncMock),
        patch("app.config.ConfigurationHandler.update_loop", new_callable=AsyncMock),
    ):
        with TestClient(app) as client:
            yield client


@pytest.fixture(scope="function")
def test_client_configurator_down() -> Generator[TestClient, None, None]:
    """Test client with configurator enabled but unreachable."""
    from app.main import app

    settings = Settings(
        app_name="test_app",
        configurator=ConfiguratorSettings(enabled=True),
        auth=AuthSettings(
            jwt_secret="test-jwt-secret", admin_username="test-admin-user", admin_password="test-admin-pw"
        ),
    )

    mock_configurator = MagicMock()
    mock_configurator.ping = AsyncMock(return_value=False)

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_configurator_client] = lambda: mock_configurator
    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        with (
            patch("app.main.get_settings", return_value=settings),
            patch("app.main.set_otel_config"),
            patch("app.config.redis.Redis.from_url", return_value=fakeredis.aioredis.FakeRedis()),
            patch("app.config.RTConfiguratorClient"),
            patch("app.config.ConfigurationUpdateReader"),
            patch("app.config.ConfigurationHandler.check_registry", new_callable=AsyncMock),
            patch("app.main._resilient_update_loop", new_callable=AsyncMock),
        ):
            with TestClient(app) as client:
                yield client
    finally:
        app.dependency_overrides.pop(get_configurator_client, None)


@pytest.fixture(scope="function")
async def db_sessionmaker() -> AsyncGenerator[async_sessionmaker, None]:
    """Get a sessionmaker bound to a fresh in-memory SQLite DB with the schema created.

    StaticPool keeps a single connection alive for the engine's lifetime, so every
    session sees the same in-memory database instead of each getting its own empty one.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    yield sessionmaker
    await engine.dispose()


@pytest.fixture(scope="function")
def mock_conversation_manager_client() -> MagicMock:
    """Get a mock Conversation Manager client; tests configure the methods they need."""
    return MagicMock()


@pytest.fixture(scope="function")
def mock_llm_client() -> MagicMock:
    """Get a mock AnthropicBedrock client; tests patch `app.ingestion.llm.classify_*`/`restructure_tree`."""
    return MagicMock()


@pytest.fixture(scope="function")
def db_test_client(
    db_sessionmaker: async_sessionmaker, mock_conversation_manager_client: MagicMock, mock_llm_client: MagicMock
) -> Generator[TestClient, None, None]:
    """Test client for DB-backed routes (documents/topics/ingestion/stats/conversations).

    Redirects both the request-scoped DB session and the background-task sessionmaker
    (`app.state.db_sessionmaker`, used by /ingestion/update's background job) to the same
    in-memory SQLite DB, and overrides the Conversation Manager/LLM clients with mocks.
    """
    from app.main import app

    async def override_get_db_session() -> AsyncGenerator:
        async with db_sessionmaker() as session:
            yield session

    app.dependency_overrides[get_settings] = get_settings_override
    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_conversation_manager_client] = lambda: mock_conversation_manager_client
    app.dependency_overrides[get_llm_client] = lambda: mock_llm_client
    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        with (
            patch("app.main.get_settings", return_value=get_settings_override()),
            patch("app.main.set_otel_config"),
            patch("app.config.redis.Redis.from_url", return_value=fakeredis.aioredis.FakeRedis()),
            patch("app.config.RTConfiguratorClient"),
            patch("app.config.ConfigurationUpdateReader"),
            patch("app.config.ConfigurationHandler.check_registry", new_callable=AsyncMock),
            patch("app.config.ConfigurationHandler.update_loop", new_callable=AsyncMock),
        ):
            with TestClient(app) as client:
                app.state.db_sessionmaker = db_sessionmaker
                yield client
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_conversation_manager_client, None)
        app.dependency_overrides.pop(get_llm_client, None)
        app.dependency_overrides.pop(get_current_user, None)
