"""
Unit tests for PART A features (A1 - A7).
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from app import create_app
from app.db import SupabaseClient


@pytest.fixture
def app():
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_a1_get_hp_balance_tier_grace_fields():
    from app.services.hp_service import get_hp_balance

    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = {
        "hp_balance": 1500,
        "hp_earned_120day": 3000,
        "tier_grace_ends_at": "2026-09-15T00:00:00+00:00",
        "tier_grace_started_at": "2026-09-08T00:00:00+00:00",
    }
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = []

    with patch("app.services.hp_service.get_user_client", return_value=mock_db), \
         patch("app.services.hp_service.get_user_tier", return_value={"tier": {"earn_multiplier": 1.08}}):
        res = get_hp_balance("user-100")
        assert res["tier_grace_ends_at"] == "2026-09-15T00:00:00+00:00"
        assert res["tier_grace_started_at"] == "2026-09-08T00:00:00+00:00"


def test_a2_rider_location_update(client):
    with patch("app.routes.riders.get_user_client") as mock_get_client, \
         patch("app.middleware.auth.get_db") as mock_auth_db, \
         patch("app.db.get_user_client") as mock_db_client, \
         patch("app.db.get_db") as mock_get_db, \
         patch.object(SupabaseClient, "auth_get_user", return_value={"id": "rider1"}):

        mock_db = MagicMock()
        mock_get_client.return_value = mock_db
        mock_auth_db.return_value = mock_db
        mock_db_client.return_value = mock_db
        mock_get_db.return_value = mock_db

        mock_db.auth_get_user.return_value = {"id": "rider1"}
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = {
            "id": "rider1", "role": "rider", "is_active": True
        }

        res = client.post(
            "/api/riders/location-update",
            headers={"Authorization": "Bearer ridertoken"},
            json={"location_lat": 7.2985, "location_lng": 5.1421},
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data["location_lat"] == 7.2985
        assert data["location_lng"] == 5.1421


def test_a3_admin_webhook_events(client):
    with patch("app.routes.admin.get_db") as mock_get_db, \
         patch("app.middleware.auth.get_db") as mock_auth_db, \
         patch("app.db.get_user_client") as mock_db_client, \
         patch.object(SupabaseClient, "auth_get_user", return_value={"id": "admin1"}):

        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_auth_db.return_value = mock_db
        mock_db_client.return_value = mock_db

        mock_db.auth_get_user.return_value = {"id": "admin1"}
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = {
            "id": "admin1", "role": "admin", "is_active": True
        }

        mock_db.table.return_value.select.return_value.order.return_value.limit.return_value.offset.return_value.execute.return_value = [
            {"id": "we1", "provider": "paystack", "status": "processed"}
        ]

        res = client.get("/api/admin/webhook-events", headers={"Authorization": "Bearer admintoken"})
        assert res.status_code == 200
        data = res.get_json()
        assert data["count"] == 1
        assert data["webhook_events"][0]["provider"] == "paystack"


def test_a4_public_config_delivery_radius(client):
    with patch("app.routes.storefront.get_user_client") as mock_get_client:
        mock_db = MagicMock()
        mock_get_client.return_value = mock_db

        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = [
            {"key": "whatsapp_link", "value": "https://wa.me/12345"}
        ]

        res = client.get("/api/storefront/config/public")
        assert res.status_code == 200
        data = res.get_json()
        assert "max_delivery_radius_km" in data
        assert "campus_lat" in data
        assert "campus_lon" in data


def test_a5_admin_update_redemption_fulfilled_by(client):
    with patch("app.routes.rewards.get_user_client") as mock_get_client, \
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
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = [
            {"id": "admin1", "role": "admin", "is_active": True},  # auth
            {"id": "red1", "status": "pending", "user_id": "u1", "reward_id": "r1", "hp_cost_snapshot": 100},  # redemption
            {"name": "T-Shirt"},  # reward
        ]

        mock_db.table.return_value.eq.return_value.update.return_value = [{"id": "red1", "status": "fulfilled", "fulfilled_by": "admin1"}]

        res = client.patch(
            "/api/rewards/admin/redemptions/red1",
            headers={"Authorization": "Bearer admintoken"},
            json={"status": "fulfilled"},
        )
        assert res.status_code == 200


def test_a6_order_streak_hp_capped_at_week_12():
    from app.services.streak_service import _award_order_streak_hp

    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = {
        "hp_awarded": 350
    }

    with patch("app.services.hp_service.award_active_hp") as mock_award, \
         patch("app.services.notification_service.send_notification"):

        hp = _award_order_streak_hp(mock_db, "user-1", 15)  # Week 15 -> capped to 12
        assert hp == 350
        # Check query passed weeks=12
        call_args = mock_db.table.return_value.select.return_value.eq.call_args_list
        assert any(c[0] == ("weeks", 12) for c in call_args)


def test_a7_update_catering_request_email_notification(client):
    with patch("app.routes.events.get_user_client") as mock_get_client, \
         patch("app.middleware.auth.get_db") as mock_auth_db, \
         patch("app.db.get_user_client") as mock_db_client, \
         patch("app.db.get_db") as mock_get_db, \
         patch.object(SupabaseClient, "auth_get_user", return_value={"id": "admin1"}), \
         patch("app.utils.email.send_email_raw") as mock_email:

        mock_db = MagicMock()
        mock_get_client.return_value = mock_db
        mock_auth_db.return_value = mock_db
        mock_db_client.return_value = mock_db
        mock_get_db.return_value = mock_db

        mock_db.auth_get_user.return_value = {"id": "admin1"}
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = [
            {"id": "admin1", "role": "admin", "is_active": True},  # auth
            {"id": "cat1", "organizer_name": "Event Org", "email": "org@event.com"},  # catering request
        ]

        mock_db.table.return_value.eq.return_value.update.return_value = [{"id": "cat1", "status": "quoted"}]

        res = client.patch(
            "/api/events/catering-requests/cat1",
            headers={"Authorization": "Bearer admintoken"},
            json={"status": "quoted", "quoted_amount": 50000},
        )
        assert res.status_code == 200
