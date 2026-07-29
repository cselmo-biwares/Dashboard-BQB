"""Conversation ingestion pipeline tests."""

from unittest.mock import AsyncMock, patch

import fakeredis.aioredis

from app.ingestion.service import release_lock, try_acquire_lock
from tests.factories import make_conversation, make_message


def test_update_triggers_ingestion_and_classifies(db_test_client, mock_conversation_manager_client):
    """POST /ingestion/update fetches, classifies and marks conversations processed."""
    conversation = make_conversation(1, hours_ago=5)
    mock_conversation_manager_client.list_conversations = AsyncMock(side_effect=[[conversation], []])
    mock_conversation_manager_client.get_messages = AsyncMock(
        return_value=[
            make_message(1, "m1", "user", "Quiero saber sobre tarifas", conversation.created_at),
        ]
    )

    classification = {
        "topics": [{"leaf_path": "Tarifas", "resolution": "resolved", "reasoning": "ok"}],
        "new_leaves": [{"parent_path": "", "name": "Tarifas"}],
    }
    with patch("app.ingestion.llm.classify_conversation", return_value=classification):
        response = db_test_client.post("/ingestion/update")
        assert response.status_code == 202
        run_id = response.json()["run_id"]

    run = db_test_client.get(f"/ingestion/runs/{run_id}").json()
    assert run["status"] == "success"
    assert run["conversations_processed"] == 1
    assert run["conversations_failed"] == 0

    latest = db_test_client.get("/ingestion/runs/latest").json()
    assert latest["id"] == run_id

    tree = db_test_client.get("/topics/tree").json()
    assert tree["children"][0]["name"] == "Tarifas"
    assert tree["children"][0]["conversation_count"] == 1


def test_unprocess_removes_processed_marker_and_topic_assignment(db_test_client, mock_conversation_manager_client):
    """POST /ingestion/unprocess un-marks matching conversations and drops their topic assignments."""
    conversation = make_conversation(1, hours_ago=5)
    mock_conversation_manager_client.list_conversations = AsyncMock(side_effect=[[conversation], []])
    mock_conversation_manager_client.get_messages = AsyncMock(
        return_value=[make_message(1, "m1", "user", "Quiero saber sobre tarifas", conversation.created_at)]
    )
    classification = {
        "topics": [{"leaf_path": "Tarifas", "resolution": "resolved", "reasoning": "ok"}],
        "new_leaves": [{"parent_path": "", "name": "Tarifas"}],
    }
    with patch("app.ingestion.llm.classify_conversation", return_value=classification):
        db_test_client.post("/ingestion/update")

    assert db_test_client.get("/topics/tree").json()["children"][0]["conversation_count"] == 1

    response = db_test_client.post("/ingestion/unprocess", json={"source": conversation.source})
    assert response.status_code == 200
    body = response.json()
    assert body["conversations_affected"] == 1
    assert body["topic_assignments_removed"] == 1

    # The leaf survives (it's stable identity), but no longer has any conversations counted.
    assert db_test_client.get("/topics/tree").json()["children"][0]["conversation_count"] == 0


def test_unprocess_requires_at_least_one_filter(db_test_client):
    """An unfiltered unprocess request is rejected — no one-click full reset."""
    assert db_test_client.post("/ingestion/unprocess", json={}).status_code == 400


def test_unprocess_no_matches_is_a_noop(db_test_client):
    """Unprocessing a filter that matches nothing returns zero counts, not an error."""
    response = db_test_client.post("/ingestion/unprocess", json={"source": "nonexistent-channel"})
    assert response.status_code == 200
    assert response.json() == {"conversations_affected": 0, "topic_assignments_removed": 0}


def test_get_run_not_found(db_test_client):
    """A non-existent run id returns 404."""
    assert db_test_client.get("/ingestion/runs/999").status_code == 404


def test_latest_run_not_found_when_none_yet(db_test_client):
    """No runs yet returns 404 for /runs/latest."""
    assert db_test_client.get("/ingestion/runs/latest").status_code == 404


async def test_lock_acquire_and_release():
    """The Redis lock guards against concurrent ingestion runs and only the owner can release it."""
    redis_client = fakeredis.aioredis.FakeRedis()

    assert await try_acquire_lock(redis_client, "tok1", 60) is True
    assert await try_acquire_lock(redis_client, "tok2", 60) is False

    await release_lock(redis_client, "tok2")  # wrong token: no-op
    assert await try_acquire_lock(redis_client, "tok3", 60) is False

    await release_lock(redis_client, "tok1")  # correct token: releases
    assert await try_acquire_lock(redis_client, "tok4", 60) is True
