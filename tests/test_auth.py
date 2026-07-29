"""Login, user management, audit log, and role-enforcement tests."""

from app.auth import AuthenticatedUser
from app.dependencies.auth import get_current_user


def test_login_success(db_test_client):
    """Correct admin credentials (from settings.auth) return a token and role."""
    response = db_test_client.post("/auth/login", json={"username": "test-admin-user", "password": "test-admin-pw"})
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "admin"
    assert body["username"] == "test-admin-user"
    assert body["access_token"]


def test_login_wrong_password(db_test_client):
    """Wrong password is rejected with 401, regardless of username."""
    response = db_test_client.post("/auth/login", json={"username": "test-admin-user", "password": "not-the-password"})
    assert response.status_code == 401


def test_login_unknown_username(db_test_client):
    """A username that's neither the admin nor a DB user is rejected with 401."""
    response = db_test_client.post("/auth/login", json={"username": "ghost", "password": "whatever"})
    assert response.status_code == 401


def test_create_list_update_delete_user(db_test_client):
    """Full CRUD cycle for an editor/analyst account."""
    created = db_test_client.post("/users", json={"username": "ana", "password": "supersecret", "role": "editor"})
    assert created.status_code == 201
    user_id = created.json()["id"]
    assert created.json()["role"] == "editor"

    listed = db_test_client.get("/users")
    assert any(u["username"] == "ana" for u in listed.json())

    updated = db_test_client.put(f"/users/{user_id}", json={"role": "analyst"})
    assert updated.status_code == 200
    assert updated.json()["role"] == "analyst"

    deleted = db_test_client.delete(f"/users/{user_id}")
    assert deleted.status_code == 204
    assert all(u["username"] != "ana" for u in db_test_client.get("/users").json())


def test_create_user_duplicate_username_conflicts(db_test_client):
    """Creating two accounts with the same username 409s instead of erroring."""
    db_test_client.post("/users", json={"username": "dup", "password": "supersecret", "role": "editor"})
    response = db_test_client.post("/users", json={"username": "dup", "password": "anotherpassword", "role": "analyst"})
    assert response.status_code == 409


def test_create_user_reserved_admin_username_conflicts(db_test_client):
    """Creating an account with the admin's own username is rejected."""
    response = db_test_client.post(
        "/users", json={"username": "test-admin-user", "password": "supersecret", "role": "editor"}
    )
    assert response.status_code == 409


def test_users_and_audit_require_admin(db_test_client):
    """Editors and analysts get 403 from /users and /audit, even though they're authenticated."""
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(username="ed", role="editor")
    try:
        assert db_test_client.get("/users").status_code == 403
        assert db_test_client.get("/audit").status_code == 403
    finally:
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(username="test-admin", role="admin")


def test_analyst_cannot_trigger_ingestion_or_manage_documents(db_test_client):
    """Analysts can read stats/topics/conversations but not write to editor-only routes."""
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(username="an", role="analyst")
    try:
        assert db_test_client.get("/stats/overview").status_code == 200
        assert db_test_client.get("/topics/tree").status_code == 200
        assert db_test_client.post("/documents", json={"name": "x.md", "content": "y"}).status_code == 403
        assert db_test_client.post("/ingestion/update").status_code == 403
    finally:
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(username="test-admin", role="admin")


def test_login_is_recorded_in_audit_log(db_test_client):
    """Both successful and failed logins show up in the audit log."""
    db_test_client.post("/auth/login", json={"username": "test-admin-user", "password": "test-admin-pw"})
    db_test_client.post("/auth/login", json={"username": "test-admin-user", "password": "wrong"})

    entries = db_test_client.get("/audit").json()
    actions = [e["action"] for e in entries]
    assert "login" in actions
    assert "login_failed" in actions


def test_unauthenticated_request_is_rejected(db_test_client):
    """No Authorization header at all is a 401, not a 403 or 500."""
    from app.main import app

    app.dependency_overrides.pop(get_current_user, None)
    try:
        response = db_test_client.get("/stats/overview")
    finally:
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(username="test-admin", role="admin")
    assert response.status_code == 401
