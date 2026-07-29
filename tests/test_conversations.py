"""Conversation detail route tests."""

from unittest.mock import AsyncMock, patch

from tests.factories import make_conversation, make_message


def test_get_conversation_detail_includes_transcript_and_topics(db_test_client, mock_conversation_manager_client):
    """GET /conversations/{id} returns the transcript plus our topic classification."""
    conversation = make_conversation(1, hours_ago=5)
    message = make_message(1, "m1", "user", "Quiero saber sobre tarifas", conversation.created_at)

    mock_conversation_manager_client.list_conversations = AsyncMock(side_effect=[[conversation], []])
    mock_conversation_manager_client.get_messages = AsyncMock(return_value=[message])

    classification = {
        "topics": [{"leaf_path": "Tarifas", "resolution": "resolved", "reasoning": "buena respuesta"}],
        "new_leaves": [{"parent_path": "", "name": "Tarifas"}],
    }
    with patch("app.ingestion.llm.classify_conversation", return_value=classification):
        db_test_client.post("/ingestion/update")

    mock_conversation_manager_client.get_conversation = AsyncMock(return_value=conversation)

    response = db_test_client.get("/conversations/1")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == 1
    assert body["messages"][0]["content"] == "Quiero saber sobre tarifas"
    assert body["topics"] == [{"leaf_path": "Tarifas", "resolution": "resolved", "reasoning": "buena respuesta"}]


def test_get_conversation_detail_not_found(db_test_client, mock_conversation_manager_client):
    """A conversation id the Conversation Manager doesn't know about returns 404."""
    mock_conversation_manager_client.get_conversation = AsyncMock(return_value=None)
    response = db_test_client.get("/conversations/999")
    assert response.status_code == 404
