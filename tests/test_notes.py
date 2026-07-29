"""Analyst notes routes tests."""

from app.auth import AuthenticatedUser
from app.dependencies.auth import get_current_user


def test_create_standalone_note(db_test_client):
    """A note can be created without any topic link."""
    response = db_test_client.post("/notes", json={"title": "Idea suelta", "content": "Revisar tarifas de equipaje"})
    assert response.status_code == 201
    body = response.json()
    assert body["topic_id"] is None
    assert body["created_by"] == "test-admin"
    assert body["updated_by"] == "test-admin"


def test_create_note_linked_to_topic_snapshots_leaf_path(db_test_client):
    """Creating a note linked to a topic snapshots its current leaf_path."""
    leaf = db_test_client.post("/topics", json={"parent_id": None, "name": "Tarifas", "type": "leaf"}).json()

    response = db_test_client.post(
        "/notes",
        json={
            "title": "Causa de no resueltos",
            "content": "El bot no tiene tarifas actualizadas",
            "topic_id": leaf["id"],
            "resolution": "unresolved",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["leaf_path"] == "Tarifas"
    assert body["resolution"] == "unresolved"


def test_create_note_snapshots_active_filter(db_test_client):
    """The channel/date-range filter active when a note is saved is stored alongside it."""
    response = db_test_client.post(
        "/notes",
        json={
            "title": "Causa de parciales",
            "content": "Faltan datos del usuario",
            "filter_source": "channel-manager-widget",
            "filter_from": "2026-07-01T00:00:00",
            "filter_to": "2026-07-15T23:59:59",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["filter_source"] == "channel-manager-widget"
    assert body["filter_from"].startswith("2026-07-01T00:00:00")
    assert body["filter_to"].startswith("2026-07-15T23:59:59")


def test_create_note_unknown_topic_404(db_test_client):
    """Linking a note to a non-existent topic 404s."""
    response = db_test_client.post("/notes", json={"title": "x", "content": "y", "topic_id": 999})
    assert response.status_code == 404


def test_list_notes_filters_by_topic(db_test_client):
    """GET /notes?topic_id= only returns notes linked to that topic."""
    leaf = db_test_client.post("/topics", json={"parent_id": None, "name": "Tarifas", "type": "leaf"}).json()
    db_test_client.post("/notes", json={"title": "Ligada", "content": "c", "topic_id": leaf["id"]})
    db_test_client.post("/notes", json={"title": "Suelta", "content": "c"})

    filtered = db_test_client.get(f"/notes?topic_id={leaf['id']}").json()
    assert [n["title"] for n in filtered] == ["Ligada"]

    unfiltered = db_test_client.get("/notes").json()
    assert len(unfiltered) == 2


def test_update_note_tracks_updated_by(db_test_client):
    """Editing a note updates its content and who last touched it, even if it's not the creator."""
    from app.main import app

    created = db_test_client.post("/notes", json={"title": "Original", "content": "v1"}).json()

    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(username="ed", role="editor")
    try:
        updated = db_test_client.put(f"/notes/{created['id']}", json={"title": "Editado", "content": "v2"})
    finally:
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(username="test-admin", role="admin")

    assert updated.status_code == 200
    body = updated.json()
    assert body["title"] == "Editado"
    assert body["created_by"] == "test-admin"
    assert body["updated_by"] == "ed"


def test_delete_note(db_test_client):
    """Any authenticated user can delete any note, not just their own."""
    from app.main import app

    created = db_test_client.post("/notes", json={"title": "Para borrar", "content": "c"}).json()

    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(username="an", role="analyst")
    try:
        response = db_test_client.delete(f"/notes/{created['id']}")
    finally:
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(username="test-admin", role="admin")

    assert response.status_code == 204
    assert db_test_client.get("/notes").json() == []


def test_update_note_not_found(db_test_client):
    """Editing a non-existent note 404s."""
    response = db_test_client.put("/notes/999", json={"title": "x", "content": "y"})
    assert response.status_code == 404
