"""
Tests for CORS configuration, OPTIONS preflight handling, and origin restriction.
"""

import json
from unittest.mock import MagicMock, patch
import pytest
from app import create_app
from app.config import Config


class TestConfig(Config):
    TESTING = True
    CORS_ORIGINS = ["http://localhost:3000", "https://app.holygrills.ng"]


@pytest.fixture
def cors_app():
    app = create_app(TestConfig)
    return app


@pytest.fixture
def cors_client(cors_app):
    return cors_app.test_client()


def test_options_preflight_allowed_origin(cors_client):
    """
    1. OPTIONS preflight request to protected route from allowed origin.
    Should return 200/204 with Access-Control-Allow-Origin header, no auth required.
    """
    mock_db = MagicMock()
    with patch("app.middleware.auth.get_db", return_value=mock_db):
        response = cors_client.open(
            "/api/orders/delivery-windows/status",
            method="OPTIONS",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization, Content-Type",
            },
        )
        assert response.status_code in (200, 204)
        assert response.headers.get("Access-Control-Allow-Origin") == "http://localhost:3000"


def test_post_login_allowed_origin(cors_client):
    """
    2. POST login request from allowed origin.
    Should succeed and return 200 with user/token data and CORS header.
    """
    mock_db = MagicMock()
    mock_db.auth_sign_in.return_value = {
        "access_token": "mock-access-token",
        "user": {"id": "user-123", "email": "test@example.com"},
    }
    mock_db.table().select().eq().single().execute.return_value = {
        "id": "user-123",
        "full_name": "Test User",
        "role": "student",
        "is_active": True,
    }

    with patch("app.services.auth_service.get_db", return_value=mock_db), \
         patch("app.routes.auth.get_db", return_value=mock_db), \
         patch("app.middleware.auth.get_db", return_value=mock_db):
        response = cors_client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "password123"},
            headers={"Origin": "http://localhost:3000"},
        )
        assert response.status_code == 200
        assert response.headers.get("Access-Control-Allow-Origin") == "http://localhost:3000"
        data = response.get_json()
        assert "token" in data or "access_token" in data or "user" in data


def test_get_menu_items_with_auth_allowed_origin(cors_client):
    """
    3. GET request to menu items endpoint with valid auth token from allowed origin.
    Should return menu data with Access-Control-Allow-Origin header.
    """
    mock_db = MagicMock()
    mock_db.auth_get_user.return_value = {"id": "user-123"}
    mock_db.table().select().eq().single().execute.return_value = {
        "id": "user-123",
        "role": "student",
        "is_active": True,
    }
    # Mock menu query
    mock_db.table().select().is_().order().execute.return_value = [
        {"id": "item-1", "name": "Jollof Rice", "price": 1500, "is_available": True}
    ]

    with patch("app.routes.menu.get_user_client", return_value=mock_db), \
         patch("app.middleware.auth.get_db", return_value=mock_db):
        response = cors_client.get(
            "/api/menu/items",
            headers={
                "Origin": "http://localhost:3000",
                "Authorization": "Bearer mock-token",
            },
        )
        assert response.status_code == 200
        assert response.headers.get("Access-Control-Allow-Origin") == "http://localhost:3000"
        data = response.get_json()
        assert "items" in data or isinstance(data, list)


def test_cors_disallowed_origin(cors_client):
    """
    4. Request from a disallowed origin when specific origins are configured.
    Access-Control-Allow-Origin header should not match the disallowed origin.
    """
    response = cors_client.open(
        "/api/menu/items",
        method="OPTIONS",
        headers={
            "Origin": "http://malicious-site.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers.get("Access-Control-Allow-Origin") != "http://malicious-site.com"
