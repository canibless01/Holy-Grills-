import pytest
from unittest.mock import MagicMock, patch
from app import create_app
from app.db import SupabaseError


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_reset_password_confirm_missing_fields(client):
    res = client.post("/api/auth/reset-password/confirm", json={})
    assert res.status_code == 400
    assert "access_token and new_password are required" in res.get_json()["error"]

    res2 = client.post("/api/auth/reset-password/confirm", json={"access_token": "token123"})
    assert res2.status_code == 400
    assert "access_token and new_password are required" in res2.get_json()["error"]


def test_reset_password_confirm_short_password(client):
    res = client.post("/api/auth/reset-password/confirm", json={"access_token": "token123", "new_password": "short"})
    assert res.status_code == 400
    assert "Password must be at least 8 characters" in res.get_json()["error"]


@patch("app.routes.auth.get_db")
def test_reset_password_confirm_success(mock_get_db, client):
    mock_db = MagicMock()
    mock_db.auth_update_user.return_value = {"id": "user_123", "email": "test@example.com"}
    mock_get_db.return_value = mock_db

    res = client.post("/api/auth/reset-password/confirm", json={"access_token": "valid_token", "new_password": "newsecretpassword"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["message"] == "Password changed successfully"
    mock_db.auth_update_user.assert_called_once_with("valid_token", {"password": "newsecretpassword"})


@patch("app.routes.auth.get_db")
def test_reset_password_confirm_supabase_error(mock_get_db, client):
    mock_db = MagicMock()
    mock_db.auth_update_user.side_effect = SupabaseError("Invalid or expired token", status_code=400, details={"code": "token_expired"})
    mock_get_db.return_value = mock_db

    res = client.post("/api/auth/reset-password/confirm", json={"access_token": "expired_token", "new_password": "newsecretpassword"})
    assert res.status_code == 400
    data = res.get_json()
    assert "Invalid or expired token" in data["error"]
