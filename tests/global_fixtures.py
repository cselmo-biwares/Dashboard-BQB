"""Utils for testing."""

from typing import Generator
from unittest.mock import patch, AsyncMock, MagicMock

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient

from app.config import Settings, ConfiguratorSettings
from app.dependencies.config import get_settings, get_configurator_client


def get_settings_override():
    """
    Get application settings override.

    :return:
    """
    return Settings(
        app_name="test_app",
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

    settings = Settings(app_name="test_app", configurator=ConfiguratorSettings(enabled=True))

    mock_configurator = MagicMock()
    mock_configurator.ping = AsyncMock(return_value=False)

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_configurator_client] = lambda: mock_configurator

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
