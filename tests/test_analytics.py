"""
Tests for Part 3 — Analytics & Data Infrastructure.
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


def test_payment_methods_4_branches(client):
    with patch("app.routes.analytics.get_user_client") as mock_get_client, \
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

        # Mock 4 orders representing each branch
        orders = [
            {"id": "o1", "wallet_amount_used": 500, "card_amount_used": 500, "total_amount": 1000},  # split
            {"id": "o2", "wallet_amount_used": 1200, "card_amount_used": 0, "total_amount": 1200},  # wallet
            {"id": "o3", "wallet_amount_used": 0, "card_amount_used": 1500, "total_amount": 1500},  # card
            {"id": "o4", "wallet_amount_used": 0, "card_amount_used": 0, "total_amount": 0},         # hp_or_free
        ]
        mock_db.table.return_value.select.return_value.gte.return_value.lte.return_value.neq.return_value.execute.return_value = orders

        res = client.get("/api/analytics/payment-methods", headers={"Authorization": "Bearer admintoken"})
        assert res.status_code == 200
        data = res.get_json()
        assert data["counts"]["split"] == 1
        assert data["counts"]["wallet"] == 1
        assert data["counts"]["card"] == 1
        assert data["counts"]["hp_or_free"] == 1


def test_addon_acceptance_and_demographics(client):
    with patch("app.routes.analytics.get_user_client") as mock_get_client, \
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

        # Addon test
        addon_orders = [
            {
                "id": "o1",
                "order_items": [
                    {
                        "is_addon": False,
                        "_addon_selections": [
                            {"name_snapshot": "Extra Cheese", "quantity": 1, "price_delta_snapshot": 200}
                        ]
                    }
                ]
            }
        ]
        mock_db.table.return_value.select.return_value.gte.return_value.lte.return_value.neq.return_value.execute.return_value = addon_orders

        res = client.get("/api/analytics/addon-acceptance", headers={"Authorization": "Bearer admintoken"})
        assert res.status_code == 200
        data = res.get_json()
        assert data["attachment_rate"] == 100.0
        assert data["top_addons"][0]["name"] == "Extra Cheese"


def test_hp_ecosystem_4_tiers(client):
    with patch("app.routes.analytics.get_user_client") as mock_get_client, \
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

        # Return 4 tiers
        tiers_list = [
            {"id": "t1", "name": "Ember", "slug": "ember", "min_points": 0},
            {"id": "t2", "name": "Flame", "slug": "flame", "min_points": 2500},
            {"id": "t3", "name": "Blaze", "slug": "blaze", "min_points": 7500},
            {"id": "t4", "name": "Holy", "slug": "holy", "min_points": 20000},
        ]
        mock_db.table.return_value.select.return_value.order.return_value.execute.return_value = tiers_list
        mock_db.table.return_value.select.return_value.gte.return_value.lte.return_value.execute.return_value = []

        res = client.get("/api/analytics/hp-ecosystem", headers={"Authorization": "Bearer admintoken"})
        assert res.status_code == 200
        data = res.get_json()
        assert len(data["tier_distribution"]) == 4
        tier_names = [t["tier"] for t in data["tier_distribution"]]
        assert "Blaze" in tier_names


def test_brand_partnerships_super_admin(client):
    with patch("app.routes.analytics.get_user_client") as mock_get_client, \
         patch("app.middleware.auth.get_db") as mock_auth_db, \
         patch("app.db.get_user_client") as mock_db_client, \
         patch("app.db.get_db") as mock_get_db, \
         patch.object(SupabaseClient, "auth_get_user", return_value={"id": "sadmin1"}):

        mock_db = MagicMock()
        mock_get_client.return_value = mock_db
        mock_auth_db.return_value = mock_db
        mock_db_client.return_value = mock_db
        mock_get_db.return_value = mock_db

        mock_db.auth_get_user.return_value = {"id": "sadmin1"}
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = {
            "id": "sadmin1", "role": "super_admin", "is_active": True
        }

        mock_db.table.return_value.select.return_value.order.return_value.execute.return_value = [
            {"id": "bp1", "brand_name": "Coca Cola", "contact_email": "brand@coca.com", "status": "pending"}
        ]

        res = client.get("/api/analytics/brand-partnerships", headers={"Authorization": "Bearer supertoken"})
        assert res.status_code == 200
        data = res.get_json()
        assert data["count"] == 1
        assert data["brand_partnerships"][0]["brand_name"] == "Coca Cola"
