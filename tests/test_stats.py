"""Dashboard stats routes tests."""

from unittest.mock import AsyncMock, patch

from tests.factories import make_conversation, make_message


def test_overview_and_volume_trend(db_test_client, mock_conversation_manager_client):
    """/stats/overview and /stats/volume-trend aggregate the ingested conversations."""
    conv1 = make_conversation(1, hours_ago=5)
    conv2 = make_conversation(2, hours_ago=6)
    mock_conversation_manager_client.list_conversations = AsyncMock(side_effect=[[conv1, conv2], []])
    mock_conversation_manager_client.get_messages = AsyncMock(
        side_effect=[
            [make_message(1, "m1", "user", "pregunta1", conv1.created_at)],
            [make_message(2, "m2", "user", "pregunta2", conv2.created_at)],
        ]
    )

    def fake_classify(client, settings, tree, conversation_id, full_text):
        resolution = "resolved" if conversation_id == 1 else "unresolved"
        return {
            "topics": [{"leaf_path": "Tarifas", "resolution": resolution, "reasoning": "ok"}],
            "new_leaves": [{"parent_path": "", "name": "Tarifas"}],
        }

    with patch("app.ingestion.llm.classify_conversation", side_effect=fake_classify):
        response = db_test_client.post("/ingestion/update")
    assert response.status_code == 202

    overview = db_test_client.get("/stats/overview").json()
    assert overview["total_conversations"] == 2
    assert overview["resolved"] == 1
    assert overview["unresolved"] == 1
    assert overview["overall_resolution_rate"] == 0.5

    trend = db_test_client.get("/stats/volume-trend?interval=day").json()
    assert sum(point["total_conversations"] for point in trend) == 2


def test_overview_filters_by_source(db_test_client, mock_conversation_manager_client):
    """/stats/overview?source=... only counts conversations from that channel."""
    conv_web = make_conversation(1, hours_ago=5, source="web")
    conv_whatsapp = make_conversation(2, hours_ago=5, source="whatsapp")
    mock_conversation_manager_client.list_conversations = AsyncMock(side_effect=[[conv_web, conv_whatsapp], []])
    mock_conversation_manager_client.get_messages = AsyncMock(
        side_effect=[
            [make_message(1, "m1", "user", "pregunta1", conv_web.created_at)],
            [make_message(2, "m2", "user", "pregunta2", conv_whatsapp.created_at)],
        ]
    )
    classification = {
        "topics": [{"leaf_path": "Tarifas", "resolution": "resolved", "reasoning": "ok"}],
        "new_leaves": [{"parent_path": "", "name": "Tarifas"}],
    }
    with patch("app.ingestion.llm.classify_conversation", return_value=classification):
        db_test_client.post("/ingestion/update")

    overview_web = db_test_client.get("/stats/overview?source=web").json()
    assert overview_web["total_conversations"] == 1

    overview_all = db_test_client.get("/stats/overview").json()
    assert overview_all["total_conversations"] == 2
