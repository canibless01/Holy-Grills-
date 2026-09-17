"""
Tests for Part 1 — Ingredient / Stock Tracking (General Store Model).
"""

import pytest
from app import create_app
from unittest.mock import MagicMock, patch
from app.db import SupabaseClient


@pytest.fixture
def app():
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_measurement_units(client):
    with patch("app.routes.kitchen.get_user_client") as mock_get_client, \
         patch("app.middleware.auth.get_db") as mock_auth_db, \
         patch("app.db.get_user_client") as mock_db_client, \
         patch("app.db.get_db") as mock_get_db, \
         patch.object(SupabaseClient, "auth_get_user", return_value={"id": "user1"}):

        mock_db = MagicMock()
        mock_get_client.return_value = mock_db
        mock_auth_db.return_value = mock_db
        mock_db_client.return_value = mock_db
        mock_get_db.return_value = mock_db

        mock_db.auth_get_user.return_value = {"id": "user1"}

        mock_db.table.return_value.select.return_value.order.return_value.execute.return_value = [
            {"id": "u1", "name": "spoon"},
            {"id": "u2", "name": "sachet"},
            {"id": "u3", "name": "bag"},
        ]

        # Auth mock profile
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = {
            "id": "user1", "role": "student", "is_active": True
        }

        res = client.get("/api/measurement-units", headers={"Authorization": "Bearer token123"})
        assert res.status_code == 200
        data = res.get_json()
        assert len(data) == 3
        assert data[0]["name"] == "spoon"


def test_create_and_list_stock_items(client):
    with patch("app.routes.kitchen.get_user_client") as mock_get_client, \
         patch("app.middleware.auth.get_db") as mock_auth_db, \
         patch("app.db.get_user_client") as mock_db_client, \
         patch("app.db.get_db") as mock_get_db, \
         patch.object(SupabaseClient, "auth_get_user", return_value={"id": "admin1"}):

        mock_db = MagicMock()
        mock_get_client.return_value = mock_db
        mock_auth_db.return_value = mock_db
        mock_db_client.return_value = mock_db
        mock_get_db.return_value = mock_db

        mock_db.auth_get_user.return_value = {"id": "admin1"}

        # Mock admin profile for auth
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = {
            "id": "admin1", "role": "admin", "is_active": True, "campus_id": "c1"
        }

        # Mock stock item insert
        created_item = {
            "id": "item1",
            "name": "Salt",
            "purchase_unit_id": "u2",
            "usage_unit_id": "u1",
            "conversion_factor": 40.0,
            "low_stock_threshold": 50.0,
            "current_balance": 0.0,
            "campus_id": "c1",
        }
        mock_db.table.return_value.insert.return_value.execute.return_value = [created_item]

        res = client.post(
            "/api/admin/stock-items",
            headers={"Authorization": "Bearer admintoken"},
            json={
                "name": "Salt",
                "purchase_unit_id": "u2",
                "usage_unit_id": "u1",
                "conversion_factor": 40,
                "low_stock_threshold": 50,
            },
        )
        assert res.status_code == 201
        data = res.get_json()
        assert data["name"] == "Salt"

        # Mock list stock items
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = [
            {**created_item, "current_balance": 30.0}
        ]
        mock_db.table.return_value.select.return_value.order.return_value.execute.return_value = [
            {**created_item, "current_balance": 30.0}
        ]

        res2 = client.get("/api/admin/stock-items", headers={"Authorization": "Bearer admintoken"})
        assert res2.status_code == 200
        items = res2.get_json()
        assert len(items) == 1
        assert items[0]["is_low_stock"] is True  # 30 < 50


def test_stock_purchase_and_usage(client):
    with patch("app.routes.kitchen.get_user_client") as mock_get_client, \
         patch("app.middleware.auth.get_db") as mock_auth_db, \
         patch("app.db.get_user_client") as mock_db_client, \
         patch("app.db.get_db") as mock_get_db, \
         patch.object(SupabaseClient, "auth_get_user", return_value={"id": "admin1"}), \
         patch("app.services.notification_service.send_notification") as mock_notify:

        mock_db = MagicMock()
        mock_get_client.return_value = mock_db
        mock_auth_db.return_value = mock_db
        mock_db_client.return_value = mock_db
        mock_get_db.return_value = mock_db

        mock_db.auth_get_user.return_value = {"id": "admin1"}

        # Auth
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = {
            "id": "admin1", "role": "admin", "is_active": True, "campus_id": "c1"
        }

        # Mock stock item lookup
        stock_item = {
            "id": "item1",
            "name": "Salt",
            "purchase_unit_id": "u2",
            "usage_unit_id": "u1",
            "conversion_factor": 40.0,
            "low_stock_threshold": 50.0,
            "current_balance": 10.0,
            "campus_id": "c1",
        }
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = [stock_item]

        # 1. Purchase 3 sachets = 120 usage units -> new balance = 130
        res = client.post(
            "/api/admin/stock-items/item1/purchase",
            headers={"Authorization": "Bearer admintoken"},
            json={"quantity": 3, "cost": 1500, "notes": "Bought 3 sachets"},
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data["current_balance"] == 130.0
        assert data["added_usage_units"] == 120.0

        # 2. Usage log 90 spoons -> new balance = 40 (which is < 50 threshold -> triggers low stock alert)
        stock_item["current_balance"] = 130.0
        mock_db.table.return_value.select.return_value.in_.return_value.eq.return_value.execute.return_value = [
            {"id": "admin1", "campus_id": "c1"}
        ]

        res2 = client.post(
            "/api/admin/stock-items/item1/usage",
            headers={"Authorization": "Bearer admintoken"},
            json={"quantity": 90, "type": "usage", "notes": "End of day prep"},
        )
        assert res2.status_code == 200
        data2 = res2.get_json()
        assert data2["current_balance"] == 40.0
        assert data2["is_low_stock"] is True


def test_stock_ledger_history(client):
    with patch("app.routes.kitchen.get_user_client") as mock_get_client, \
         patch("app.middleware.auth.get_db") as mock_auth_db, \
         patch("app.db.get_user_client") as mock_db_client, \
         patch("app.db.get_db") as mock_get_db, \
         patch.object(SupabaseClient, "auth_get_user", return_value={"id": "admin1"}):

        mock_db = MagicMock()
        mock_get_client.return_value = mock_db
        mock_auth_db.return_value = mock_db
        mock_db_client.return_value = mock_db
        mock_get_db.return_value = mock_db

        mock_db.auth_get_user.return_value = {"id": "admin1"}

        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = {
            "id": "admin1", "role": "admin", "is_active": True
        }

        # Item exists check
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = [{"id": "item1"}]

        # Ledger query
        ledger_entries = [
            {"id": "l2", "type": "usage", "quantity_entered": 90.0, "quantity_in_usage_units": 90.0},
            {"id": "l1", "type": "purchase", "quantity_entered": 3.0, "quantity_in_usage_units": 120.0},
        ]
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = ledger_entries

        res = client.get("/api/admin/stock-items/item1/ledger", headers={"Authorization": "Bearer admintoken"})
        assert res.status_code == 200
        data = res.get_json()
        assert data["count"] == 2
        assert len(data["ledger"]) == 2
