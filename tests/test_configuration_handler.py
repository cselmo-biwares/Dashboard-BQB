"""Unit tests for ConfigurationHandler."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import ConfigurationHandler, DynamicConfig
from chatmessaging.http.client.configurator import ConfigurableModuleNotFoundError
from chatmessaging.http.schemas.configurator import ModuleConfiguration, ModuleType
from chatmessaging.events.base import EventEnvelope
from chatmessaging.events.configurator import ConfigurationUpdateEvent


MODULE_TYPE = ModuleType.other
MODULE_NAME = "test_module"
CONFIG_VERSION = "1.0.0"


def _make_module_config(
    version: str = "1.0.0",
    values: dict | None = None,
    schema_: dict | None = None,
) -> ModuleConfiguration:
    """Build a ModuleConfiguration with sensible defaults for testing."""
    return ModuleConfiguration(
        module_type=MODULE_TYPE,
        module_name=MODULE_NAME,
        version=version,
        registered_at=datetime.now(),
        last_updated_at=datetime.now(),
        schema_=schema_ if schema_ is not None else DynamicConfig.model_json_schema(),
        values=values if values is not None else {"configurable_int": 23, "configurable_str": "base config"},
    )


def _make_handler(config: DynamicConfig | None = None) -> tuple[ConfigurationHandler, AsyncMock, AsyncMock]:
    """Return (handler, mock_client, mock_reader) with AsyncMock external dependencies."""
    if config is None:
        config = DynamicConfig()
    mock_client = AsyncMock()
    mock_reader = AsyncMock()
    handler = ConfigurationHandler(
        module_type=MODULE_TYPE,
        module_name=MODULE_NAME,
        config_version=CONFIG_VERSION,
        config=config,
        configurator_client=mock_client,
        configurator_update_reader=mock_reader,
    )
    return handler, mock_client, mock_reader


# ---------------------------------------------------------------------------
# update_config
# ---------------------------------------------------------------------------


def test_update_config_updates_fields():
    """update_config applies new values from stored_config onto self.config."""
    handler, _, _ = _make_handler()
    stored = _make_module_config(values={"configurable_int": 99, "configurable_str": "updated"})
    handler.update_config(stored)
    assert handler.config.configurable_int == 99
    assert handler.config.configurable_str == "updated"


def test_update_config_returns_new_instance():
    """update_config replaces self.config with a new object rather than mutating in place."""
    original = DynamicConfig()
    handler, _, _ = _make_handler(config=original)
    stored = _make_module_config(values={"configurable_int": 5, "configurable_str": "x"})
    handler.update_config(stored)
    assert handler.config is not original


# ---------------------------------------------------------------------------
# check_event
# ---------------------------------------------------------------------------

_ENVELOPE = EventEnvelope(event_type="config_update", version=1)


def _make_event(module_type=MODULE_TYPE, module_name=MODULE_NAME) -> ConfigurationUpdateEvent:
    """Build a ConfigurationUpdateEvent targeting the given module."""
    return ConfigurationUpdateEvent(
        envelope=_ENVELOPE,
        module_type=module_type,
        module_name=module_name,
    )


def test_check_event_valid():
    """check_event returns True when both module_type and module_name match the handler."""
    handler, _, _ = _make_handler()
    assert handler.check_event(_make_event()) is True


def test_check_event_wrong_module_type():
    """check_event returns False when the event's module_type does not match."""
    handler, _, _ = _make_handler()
    assert handler.check_event(_make_event(module_type=ModuleType.channel)) is False


def test_check_event_wrong_module_name():
    """check_event returns False when the event's module_name does not match."""
    handler, _, _ = _make_handler()
    assert handler.check_event(_make_event(module_name="other_module")) is False


# ---------------------------------------------------------------------------
# check_registry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_registry_module_not_found_registers_and_updates():
    """When the module is not registered, check_registry registers it and updates config."""
    handler, mock_client, _ = _make_handler()
    stored = _make_module_config()
    mock_client.get_module.side_effect = ConfigurableModuleNotFoundError("module not found")
    mock_client.register_module.return_value = stored

    await handler.check_registry()

    mock_client.register_module.assert_awaited_once_with(
        MODULE_TYPE, MODULE_NAME, version=CONFIG_VERSION, config=handler.config
    )
    assert handler.config.configurable_int == stored.values["configurable_int"]


@pytest.mark.asyncio
async def test_check_registry_version_match_schema_match_updates_config():
    """When versions and schemas agree, check_registry updates config without re-registering."""
    handler, mock_client, _ = _make_handler()
    stored = _make_module_config(version=CONFIG_VERSION)
    mock_client.get_module.return_value = stored

    await handler.check_registry()

    mock_client.register_module.assert_not_awaited()
    assert handler.config.configurable_int == stored.values["configurable_int"]


@pytest.mark.asyncio
async def test_check_registry_version_match_schema_mismatch_raises():
    """check_registry raises ValueError when the version matches but the schema differs."""
    handler, mock_client, _ = _make_handler()
    stored = _make_module_config(version=CONFIG_VERSION, schema_={"different": "schema"})
    mock_client.get_module.return_value = stored

    with pytest.raises(ValueError):
        await handler.check_registry()


@pytest.mark.asyncio
async def test_check_registry_stored_version_higher_raises():
    """check_registry raises ValueError when the registry holds a newer version than the service."""
    handler, mock_client, _ = _make_handler()
    stored = _make_module_config(version="2.0.0")
    mock_client.get_module.return_value = stored

    with pytest.raises(ValueError):
        await handler.check_registry()


@pytest.mark.asyncio
async def test_check_registry_local_version_higher_reregisters_and_updates():
    """When the local version is ahead of the registry, check_registry re-registers and updates config."""
    handler, mock_client, _ = _make_handler()
    old_stored = _make_module_config(version="0.9.0")
    new_stored = _make_module_config(version=CONFIG_VERSION, values={"configurable_int": 42, "configurable_str": "new"})
    mock_client.get_module.return_value = old_stored
    mock_client.register_module.return_value = new_stored

    await handler.check_registry()

    mock_client.register_module.assert_awaited_once()
    assert handler.config.configurable_int == 42


# ---------------------------------------------------------------------------
# update_loop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def _run_update_loop_with_events(handler, mock_client, mock_reader, events: list):
    """Drive update_loop to completion by having the reader yield a finite list of events."""

    async def _listen():
        for event in events:
            yield event

    mock_reader.__aenter__.return_value = mock_reader
    mock_reader.__aexit__ = AsyncMock(return_value=None)
    mock_reader.listen = MagicMock(return_value=_listen())

    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__ = AsyncMock(return_value=None)

    await handler.update_loop()


@pytest.mark.asyncio
async def test_update_loop_matching_event_calls_update():
    """update_loop fetches new config and calls update_config when a matching event arrives."""
    handler, mock_client, mock_reader = _make_handler()
    new_stored = _make_module_config(values={"configurable_int": 77, "configurable_str": "loop"})
    mock_client.get_module.return_value = new_stored

    event = _make_event()
    await _run_update_loop_with_events(handler, mock_client, mock_reader, [event])

    mock_client.get_module.assert_awaited_once_with(MODULE_TYPE, MODULE_NAME)
    assert handler.config.configurable_int == 77


@pytest.mark.asyncio
async def test_update_loop_non_matching_event_skips_update():
    """update_loop ignores events that target a different module, leaving config unchanged."""
    handler, mock_client, mock_reader = _make_handler()

    wrong_event = _make_event(module_name="other_module")
    await _run_update_loop_with_events(handler, mock_client, mock_reader, [wrong_event])

    mock_client.get_module.assert_not_awaited()
    assert handler.config.configurable_int == 23
