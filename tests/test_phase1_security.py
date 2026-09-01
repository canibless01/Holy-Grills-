"""
Unit tests for Phase 1 Security Fixes:
- RLS get_user_client() and TableQuery user JWT header propagation
- squad_leaderboard campus_id scoping
- change_user_role role escalation guards & ADMIN_ROLES
"""

import pytest
from flask import Flask, g
from unittest.mock import MagicMock, patch
from app.db import get_db, get_user_client, UserSupabaseClient, SupabaseClient
from app.middleware.auth import require_role, ADMIN_ROLES
from app.routes.admin import admin_bp
from app.routes.leaderboard import leaderboard_bp


def test_auth_middleware_sets_g_jwt_token_and_get_user_client():
    app = Flask(__name__)

    @app.route("/test-me")
    @require_role("student")
    def test_me():
        client = get_user_client()
        assert isinstance(client, UserSupabaseClient)
        assert getattr(g, "jwt_token", None) == "real-bearer-jwt-999"
        return "ok", 200

    test_client = app.test_client()

    with patch("app.middleware.auth.get_db") as mock_auth_db, \
         patch("app.db.get_db") as mock_db_get_db:
        mock_db = MagicMock()
        mock_auth_db.return_value = mock_db
        mock_db_get_db.return_value = mock_db

        mock_db.auth_get_user.return_value = {"id": "user-student-1"}
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = {
            "id": "user-student-1",
            "role": "student",
            "is_active": True,
            "campus_id": "campus-1",
        }

        resp = test_client.get("/test-me", headers={"Authorization": "Bearer real-bearer-jwt-999"})
        assert resp.status_code == 200


def test_get_user_client_returns_wrapper_when_jwt_in_g():
    app = Flask(__name__)
    with app.test_request_context():
        g.jwt_token = "test-token-123"
        client = get_user_client()
        assert isinstance(client, UserSupabaseClient)
        assert client._jwt_token == "test-token-123"

        # Check table query gets with_jwt
        with patch.object(SupabaseClient, "table") as mock_table:
            query_mock = MagicMock()
            mock_table.return_value = query_mock
            client.table("cart_items")
            mock_table.assert_called_once_with("cart_items")
            query_mock.with_jwt.assert_called_once_with("test-token-123")


def test_get_user_client_returns_db_when_no_jwt():
    app = Flask(__name__)
    with app.test_request_context():
        client = get_user_client()
        assert isinstance(client, UserSupabaseClient)
        assert client._jwt_token is None


def test_require_role_allows_super_admin():
    app = Flask(__name__)

    @app.route("/test-admin")
    @require_role("admin")
    def test_route():
        return "ok", 200

    client = app.test_client()

    with patch("app.middleware.auth.get_db") as mock_get_db:
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.auth_get_user.return_value = {"id": "user-super"}
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = {
            "id": "user-super",
            "role": "super_admin",
            "is_active": True,
            "campus_id": "campus-1",
        }

        resp = client.get("/test-admin", headers={"Authorization": "Bearer token123"})
        assert resp.status_code == 200
        assert resp.get_data(as_text=True) == "ok"


def test_change_user_role_guards():
    app = Flask(__name__)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    client = app.test_client()

    # 1. Prevent self role change
    with patch("app.middleware.auth.get_db") as mock_auth_db, \
         patch("app.routes.admin.get_db") as mock_admin_db:
        mock_db = MagicMock()
        mock_auth_db.return_value = mock_db
        mock_admin_db.return_value = mock_db

        mock_db.auth_get_user.return_value = {"id": "admin-1"}
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = {
            "id": "admin-1",
            "role": "admin",
            "is_active": True,
            "campus_id": "campus-1",
        }

        resp = client.patch(
            "/admin/users/admin-1/role",
            headers={"Authorization": "Bearer token123"},
            json={"role": "student"},
        )
        assert resp.status_code == 403
        assert "Cannot change your own role" in resp.get_data(as_text=True)


def test_change_user_role_super_admin_guard():
    app = Flask(__name__)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    client = app.test_client()

    # 2. Non-super_admin trying to assign super_admin role
    with patch("app.middleware.auth.get_db") as mock_auth_db, \
         patch("app.routes.admin.get_db") as mock_admin_db:
        mock_db = MagicMock()
        mock_auth_db.return_value = mock_db
        mock_admin_db.return_value = mock_db

        mock_db.auth_get_user.return_value = {"id": "admin-1"}
        # Caller is admin (not super_admin)
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = [
            {"id": "admin-1", "role": "admin", "is_active": True, "campus_id": "campus-1"},
            {"id": "target-user", "full_name": "Target User", "role": "student"},
        ]

        resp = client.patch(
            "/admin/users/target-user/role",
            headers={"Authorization": "Bearer token123"},
            json={"role": "super_admin"},
        )
        assert resp.status_code == 403
        assert "Only super_admin can assign super_admin role" in resp.get_data(as_text=True)


def test_change_user_role_super_admin_allowed():
    app = Flask(__name__)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    client = app.test_client()

    # 3. Super_admin assigning super_admin role is allowed
    with patch("app.middleware.auth.get_db") as mock_auth_db, \
         patch("app.routes.admin.get_db") as mock_admin_db:
        mock_db = MagicMock()
        mock_auth_db.return_value = mock_db
        mock_admin_db.return_value = mock_db

        mock_db.auth_get_user.return_value = {"id": "super-1"}
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = [
            {"id": "super-1", "role": "super_admin", "is_active": True, "campus_id": "campus-1"},
            {"id": "target-user", "full_name": "Target User", "role": "student"},
        ]

        mock_db.table.return_value.eq.return_value.update.return_value = [{"id": "target-user", "role": "super_admin"}]

        resp = client.patch(
            "/admin/users/target-user/role",
            headers={"Authorization": "Bearer token123"},
            json={"role": "super_admin"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["role"] == "super_admin"


def test_squad_leaderboard_campus_scoping():
    app = Flask(__name__)
    app.config["LEADERBOARD_DEFAULT_LIMIT"] = 10
    app.register_blueprint(leaderboard_bp, url_prefix="/leaderboard")
    client = app.test_client()

    with patch("app.routes.leaderboard.get_db") as mock_get_db:
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        query_chain = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value = query_chain
        query_chain.eq.return_value = query_chain
        query_chain.execute.return_value = []

        resp = client.get("/leaderboard/squad?campus_id=campus-abc")
        assert resp.status_code == 200
        # Check campus_id filter was applied
        query_chain.eq.assert_called_with("campus_id", "campus-abc")
