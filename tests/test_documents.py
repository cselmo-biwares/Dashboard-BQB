"""Document ingestion routes tests."""

from unittest.mock import patch


def test_create_document_classifies_and_assigns(db_test_client):
    """POST /documents creates the document and assigns it to the classified leaves."""
    classification = {"leaf_paths": ["Tarifas"], "new_leaves": [{"parent_path": "", "name": "Tarifas"}]}
    with patch("app.ingestion.llm.classify_document", return_value=classification):
        response = db_test_client.post("/documents", json={"name": "tarifas.md", "content": "contenido"})

    assert response.status_code == 200
    body = response.json()
    assert body["document"]["name"] == "tarifas.md"
    assert body["assigned_leaf_paths"] == ["Tarifas"]


def test_create_document_upserts_by_name(db_test_client):
    """Sending a document with an existing name updates its content instead of duplicating it."""
    classification = {"leaf_paths": [], "new_leaves": []}
    with patch("app.ingestion.llm.classify_document", return_value=classification):
        first = db_test_client.post("/documents", json={"name": "doc.md", "content": "v1"})
        second = db_test_client.post("/documents", json={"name": "doc.md", "content": "v2"})

    assert first.json()["document"]["id"] == second.json()["document"]["id"]
    assert second.json()["document"]["content"] == "v2"
    assert len(db_test_client.get("/documents").json()) == 1


def test_delete_document(db_test_client):
    """Deleting a document removes it (and its assignments)."""
    with patch("app.ingestion.llm.classify_document", return_value={"leaf_paths": [], "new_leaves": []}):
        created = db_test_client.post("/documents", json={"name": "doc.md", "content": "v1"})
    document_id = created.json()["document"]["id"]

    response = db_test_client.delete(f"/documents/{document_id}")
    assert response.status_code == 204
    assert db_test_client.get("/documents").json() == []


def test_delete_document_not_found(db_test_client):
    """Deleting a non-existent document returns 404."""
    assert db_test_client.delete("/documents/999").status_code == 404
