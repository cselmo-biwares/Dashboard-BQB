"""Application main routes tests."""

from app.config import DynamicConfig


def test_root(test_client, app_settings):
    """
    Test that / route returns app info with default dynamic config.

    :return:
    """
    response = test_client.get("/")
    assert response.status_code == 200
    assert response.json() == {
        "app_name": app_settings.app_name,
        "configurable_int": 23,
        "configurable_str": "base config",
    }


def test_root_config_update(test_client, app_settings):
    """
    Test that updating config_handler.config is immediately visible in responses.

    Verifies the shared state: get_configuration reads config_handler.config on
    every request, so any update to it is reflected without restarting.

    :return:
    """
    response = test_client.get("/")
    assert response.status_code == 200
    assert response.json()["configurable_int"] == 23

    test_client.app.state.config_handler.config = DynamicConfig(
        configurable_int=99,
        configurable_str="updated",
    )

    response = test_client.get("/")
    assert response.status_code == 200
    assert response.json() == {
        "app_name": app_settings.app_name,
        "configurable_int": 99,
        "configurable_str": "updated",
    }
