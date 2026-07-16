"""Application condition endpoints tests."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_alive():
    """
    Client responds with a 200 status code for /alive.

    :return:
    """
    # TODO: implement this
    response = client.get("/status/liveness")
    assert response.status_code == 200


def test_startup():
    """
    Client responds with a 200 status code for /startup.

    :return:
    """
    # TODO: implement this
    response = client.get("/status/startup")
    assert response.status_code == 200


def test_readiness(test_client):
    """Client responds with 200 when Redis and configurator are reachable."""
    response = test_client.get("/status/readiness")
    assert response.status_code == 200


def test_readiness_redis_down(test_client_redis_down):
    """Client responds with 503 when Redis is unreachable."""
    response = test_client_redis_down.get("/status/readiness")
    assert response.status_code == 503


def test_readiness_configurator_down(test_client_configurator_down):
    """Client responds with 503 when the configurator service is unreachable."""
    response = test_client_configurator_down.get("/status/readiness")
    assert response.status_code == 503
