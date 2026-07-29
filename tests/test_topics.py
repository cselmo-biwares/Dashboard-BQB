"""Topic tree routes tests: explorer, resolution ranking, documents, restructure."""

from unittest.mock import AsyncMock, patch

from tests.factories import make_conversation, make_message


def _classify_document(db_test_client, name: str, leaf_path: str):
    classification = {"leaf_paths": [leaf_path], "new_leaves": [{"parent_path": "", "name": leaf_path}]}
    with patch("app.ingestion.llm.classify_document", return_value=classification):
        return db_test_client.post("/documents", json={"name": name, "content": "x"})


def _ingest_one_conversation(db_test_client, mock_conversation_manager_client, leaf_path: str, resolution: str):
    conversation = make_conversation(1, hours_ago=5)
    mock_conversation_manager_client.list_conversations = AsyncMock(side_effect=[[conversation], []])
    mock_conversation_manager_client.get_messages = AsyncMock(
        return_value=[make_message(1, "m1", "user", "pregunta", conversation.created_at)]
    )
    classification = {
        "topics": [{"leaf_path": leaf_path, "resolution": resolution, "reasoning": "ok"}],
        "new_leaves": [{"parent_path": "", "name": leaf_path}],
    }
    with patch("app.ingestion.llm.classify_conversation", return_value=classification):
        response = db_test_client.post("/ingestion/update")
    assert response.status_code == 202


def test_topic_documents_list_and_unassign(db_test_client):
    """Documents can be listed per leaf and unassigned without deleting them."""
    created = _classify_document(db_test_client, "tarifas.md", "Tarifas")
    document_id = created.json()["document"]["id"]

    tree = db_test_client.get("/topics/tree").json()
    topic_id = tree["children"][0]["id"]

    docs = db_test_client.get(f"/topics/{topic_id}/documents").json()
    assert [d["id"] for d in docs] == [document_id]

    response = db_test_client.delete(f"/topics/{topic_id}/documents/{document_id}")
    assert response.status_code == 204
    assert db_test_client.get(f"/topics/{topic_id}/documents").json() == []

    # the document itself and the leaf still exist
    assert len(db_test_client.get("/documents").json()) == 1
    assert db_test_client.get("/topics/tree").json()["children"][0]["name"] == "Tarifas"


def test_unassign_document_not_found(db_test_client):
    """Unassigning a non-existent (topic, document) pair returns 404."""
    assert db_test_client.delete("/topics/1/documents/1").status_code == 404


def test_resolution_summary_flags_documentation_gap(db_test_client, mock_conversation_manager_client):
    """A leaf with conversations but no assigned document is flagged has_documentation=False."""
    _ingest_one_conversation(db_test_client, mock_conversation_manager_client, "Tarifas", "unresolved")

    rows = db_test_client.get("/topics/resolution-summary").json()
    assert len(rows) == 1
    row = rows[0]
    assert row["leaf_path"] == "Tarifas"
    assert row["total_conversations"] == 1
    assert row["unresolved"] == 1
    assert row["resolution_rate"] == 0.0
    assert row["has_documentation"] is False


def test_resolution_summary_ordering_and_limit(db_test_client, mock_conversation_manager_client):
    """resolution-summary respects order_by/dir/limit."""
    _ingest_one_conversation(db_test_client, mock_conversation_manager_client, "Tarifas", "resolved")

    rows = db_test_client.get("/topics/resolution-summary?order_by=resolution_rate&dir=desc&limit=1").json()
    assert len(rows) == 1
    assert rows[0]["resolution_rate"] == 1.0


def test_restructure_keeps_leaves_but_changes_structure(db_test_client):
    """Restructuring can regroup nodes but must keep every leaf's assignments intact."""
    _classify_document(db_test_client, "tarifas.md", "Tarifas")
    _classify_document(db_test_client, "equipaje.md", "Equipaje")

    new_structure = {
        "name": "root",
        "children": [
            {
                "name": "Compras",
                "type": "node",
                "children": [{"name": "Tarifas", "type": "leaf"}, {"name": "Equipaje", "type": "leaf"}],
            }
        ],
    }
    with patch("app.ingestion.llm.restructure_tree", return_value=new_structure):
        response = db_test_client.post("/topics/restructure", json={"instruction": "agrupá todo bajo Compras"})

    assert response.status_code == 200
    assert response.json()["leaves_kept"] == 2

    tree = db_test_client.get("/topics/tree").json()
    assert tree["children"][0]["name"] == "Compras"
    leaf_names = {c["name"] for c in tree["children"][0]["children"]}
    assert leaf_names == {"Tarifas", "Equipaje"}


def test_restructure_rejects_dropped_leaf(db_test_client):
    """A restructure result that drops a leaf is rejected (409) and nothing is applied."""
    _classify_document(db_test_client, "tarifas.md", "Tarifas")

    bad_structure = {"name": "root", "children": []}
    with patch("app.ingestion.llm.restructure_tree", return_value=bad_structure):
        response = db_test_client.post("/topics/restructure", json={})

    assert response.status_code == 409
    # tree unchanged
    tree = db_test_client.get("/topics/tree").json()
    assert tree["children"][0]["name"] == "Tarifas"


def test_create_node_and_leaf_by_hand(db_test_client):
    """A node and a leaf under it can be created manually, without going through the LLM."""
    node = db_test_client.post("/topics", json={"parent_id": None, "name": "Pagos", "type": "node"})
    assert node.status_code == 201
    node_id = node.json()["id"]

    leaf = db_test_client.post("/topics", json={"parent_id": node_id, "name": "Tarjetas", "type": "leaf"})
    assert leaf.status_code == 201
    assert leaf.json()["parent_id"] == node_id

    tree = db_test_client.get("/topics/tree").json()
    assert tree["children"][0]["name"] == "Pagos"
    assert tree["children"][0]["children"][0]["name"] == "Tarjetas"


def test_create_leaf_under_leaf_rejected(db_test_client):
    """A leaf can't be used as a parent."""
    leaf = db_test_client.post("/topics", json={"parent_id": None, "name": "Tarifas", "type": "leaf"})
    leaf_id = leaf.json()["id"]

    response = db_test_client.post("/topics", json={"parent_id": leaf_id, "name": "Sub", "type": "leaf"})
    assert response.status_code == 409


def test_create_topic_duplicate_name_conflicts(db_test_client):
    """Two leaves with the same name (globally unique) 409 instead of erroring."""
    db_test_client.post("/topics", json={"parent_id": None, "name": "Tarifas", "type": "leaf"})
    response = db_test_client.post("/topics", json={"parent_id": None, "name": "Tarifas", "type": "leaf"})
    assert response.status_code == 409


def test_rename_topic(db_test_client):
    """Renaming a node/leaf updates it in place."""
    created = db_test_client.post("/topics", json={"parent_id": None, "name": "Pagos", "type": "node"})
    topic_id = created.json()["id"]

    renamed = db_test_client.patch(f"/topics/{topic_id}", json={"name": "Pagos y facturación"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Pagos y facturación"


def test_move_topic_reparents(db_test_client):
    """Dragging a leaf under a different node changes its parent_id."""
    node_a = db_test_client.post("/topics", json={"parent_id": None, "name": "A", "type": "node"}).json()
    node_b = db_test_client.post("/topics", json={"parent_id": None, "name": "B", "type": "node"}).json()
    leaf = db_test_client.post("/topics", json={"parent_id": node_a["id"], "name": "Hoja", "type": "leaf"}).json()

    moved = db_test_client.patch(f"/topics/{leaf['id']}/move", json={"parent_id": node_b["id"]})
    assert moved.status_code == 200
    assert moved.json()["parent_id"] == node_b["id"]


def test_move_topic_rejects_cycle(db_test_client):
    """A node can't be moved into its own subtree."""
    parent = db_test_client.post("/topics", json={"parent_id": None, "name": "Padre", "type": "node"}).json()
    child = db_test_client.post("/topics", json={"parent_id": parent["id"], "name": "Hijo", "type": "node"}).json()

    response = db_test_client.patch(f"/topics/{parent['id']}/move", json={"parent_id": child["id"]})
    assert response.status_code == 409


def test_delete_empty_node(db_test_client):
    """An empty node can be deleted."""
    node = db_test_client.post("/topics", json={"parent_id": None, "name": "Vacío", "type": "node"}).json()
    response = db_test_client.delete(f"/topics/{node['id']}")
    assert response.status_code == 204
    assert db_test_client.get("/topics/tree").json()["children"] == []


def test_delete_node_with_children_rejected(db_test_client):
    """A node with children can't be deleted directly."""
    node = db_test_client.post("/topics", json={"parent_id": None, "name": "Padre", "type": "node"}).json()
    db_test_client.post("/topics", json={"parent_id": node["id"], "name": "Hijo", "type": "leaf"})

    response = db_test_client.delete(f"/topics/{node['id']}")
    assert response.status_code == 409


def test_delete_leaf_with_documents_rejected(db_test_client):
    """A leaf with an assigned document can't be deleted until it's unassigned."""
    created = _classify_document(db_test_client, "tarifas.md", "Tarifas")
    document_id = created.json()["document"]["id"]
    leaf_id = db_test_client.get("/topics/tree").json()["children"][0]["id"]

    assert db_test_client.delete(f"/topics/{leaf_id}").status_code == 409

    db_test_client.delete(f"/topics/{leaf_id}/documents/{document_id}")
    assert db_test_client.delete(f"/topics/{leaf_id}").status_code == 204


def test_root_cause_synthesizes_common_reason(db_test_client, mock_conversation_manager_client):
    """The root-cause endpoint feeds the stored per-conversation reasoning into one LLM call."""
    _ingest_one_conversation(db_test_client, mock_conversation_manager_client, "Tarifas", "unresolved")
    leaf_id = db_test_client.get("/topics/tree").json()["children"][0]["id"]

    analysis = {
        "main_cause": "El bot no tiene la tarifa actualizada",
        "explanation": "La mayoría de los casos fallan porque el bot responde con precios viejos.",
        "secondary_causes": ["Falta de documentación de tarifas promocionales"],
    }
    with patch("app.ingestion.llm.summarize_root_cause", return_value=analysis):
        response = db_test_client.get(f"/topics/{leaf_id}/root-cause?resolution=unresolved")

    assert response.status_code == 200
    body = response.json()
    assert body["main_cause"] == analysis["main_cause"]
    assert body["total_matching"] == 1
    assert body["sample_size"] == 1


def test_root_cause_no_matching_conversations(db_test_client):
    """No conversations with that resolution for the topic returns 404, not an empty analysis."""
    leaf = db_test_client.post("/topics", json={"parent_id": None, "name": "Tarifas", "type": "leaf"}).json()
    response = db_test_client.get(f"/topics/{leaf['id']}/root-cause?resolution=partial")
    assert response.status_code == 404


def test_root_cause_topic_not_found(db_test_client):
    """A non-existent topic id returns 404."""
    assert db_test_client.get("/topics/999/root-cause?resolution=unresolved").status_code == 404


def test_activity_heatmap_has_168_cells_summing_to_total(db_test_client, mock_conversation_manager_client):
    """The heatmap always returns 7x24 cells, with totals adding up to the observed conversations."""
    _ingest_one_conversation(db_test_client, mock_conversation_manager_client, "Tarifas", "resolved")
    leaf_id = db_test_client.get("/topics/tree").json()["children"][0]["id"]

    response = db_test_client.get(f"/topics/{leaf_id}/activity-heatmap")
    assert response.status_code == 200
    body = response.json()
    assert body["total_conversations"] == 1
    assert len(body["cells"]) == 168
    assert sum(c["total"] for c in body["cells"]) == 1
    hit_cells = [c for c in body["cells"] if c["total"] == 1]
    assert len(hit_cells) == 1
    assert hit_cells[0]["average"] > 0


def test_activity_heatmap_no_conversations_404(db_test_client):
    """A topic with no conversations at all returns 404."""
    leaf = db_test_client.post("/topics", json={"parent_id": None, "name": "Tarifas", "type": "leaf"}).json()
    assert db_test_client.get(f"/topics/{leaf['id']}/activity-heatmap").status_code == 404


def test_activity_heatmap_topic_not_found(db_test_client):
    """A non-existent topic id returns 404."""
    assert db_test_client.get("/topics/999/activity-heatmap").status_code == 404


def test_whole_tree_activity_heatmap(db_test_client, mock_conversation_manager_client):
    """GET /topics/activity-heatmap aggregates across every leaf, not just one topic."""
    _ingest_one_conversation(db_test_client, mock_conversation_manager_client, "Tarifas", "resolved")

    response = db_test_client.get("/topics/activity-heatmap")
    assert response.status_code == 200
    body = response.json()
    assert body["topic_id"] is None
    assert body["total_conversations"] == 1
    assert len(body["cells"]) == 168
    assert sum(c["total"] for c in body["cells"]) == 1


def test_whole_tree_activity_heatmap_no_conversations_404(db_test_client):
    """No processed conversations anywhere returns 404, not an empty heatmap."""
    assert db_test_client.get("/topics/activity-heatmap").status_code == 404


def test_tree_root_reports_aggregated_metrics(db_test_client, mock_conversation_manager_client):
    """The synthetic root node's counts must sum its children, same as any other node."""
    _classify_document(db_test_client, "tarifas.md", "Tarifas")
    _ingest_one_conversation(db_test_client, mock_conversation_manager_client, "Tarifas", "resolved")

    tree = db_test_client.get("/topics/tree").json()
    assert tree["id"] is None
    assert tree["document_count"] == 1
    assert tree["conversation_count"] == 1
    assert tree["resolution_breakdown"]["resolved"] == 1


def test_topic_conversations_respects_source_filter(db_test_client, mock_conversation_manager_client):
    """GET /topics/{id}/conversations?source= only returns conversations from that channel."""
    conv_a = make_conversation(1, hours_ago=5, source="channel-a")
    mock_conversation_manager_client.list_conversations = AsyncMock(side_effect=[[conv_a], []])
    mock_conversation_manager_client.get_messages = AsyncMock(
        return_value=[make_message(1, "m1", "user", "pregunta", conv_a.created_at)]
    )
    classification = {
        "topics": [{"leaf_path": "Tarifas", "resolution": "resolved", "reasoning": "ok"}],
        "new_leaves": [{"parent_path": "", "name": "Tarifas"}],
    }
    with patch("app.ingestion.llm.classify_conversation", return_value=classification):
        db_test_client.post("/ingestion/update")

    conv_b = make_conversation(2, hours_ago=4, source="channel-b")
    mock_conversation_manager_client.list_conversations = AsyncMock(side_effect=[[conv_b], []])
    mock_conversation_manager_client.get_messages = AsyncMock(
        return_value=[make_message(2, "m2", "user", "pregunta", conv_b.created_at)]
    )
    with patch("app.ingestion.llm.classify_conversation", return_value=classification):
        db_test_client.post("/ingestion/update")

    leaf_id = db_test_client.get("/topics/tree").json()["children"][0]["id"]

    unfiltered = db_test_client.get(f"/topics/{leaf_id}/conversations").json()
    assert unfiltered["total"] == 2

    filtered = db_test_client.get(f"/topics/{leaf_id}/conversations?source=channel-a").json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["conversation_id"] == 1
