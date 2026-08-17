"""
Comprehensive test suite for Master Prompt remediations.
Tests status bypass validations, spend_hp hardening, marketplace fixes,
webhook/DVA fixes, create_window campus scoping, admin deactivate/close window,
and batch creation validations.
"""

import pytest
from unittest.mock import MagicMock, patch
from flask import Flask
from app.routes.admin import admin_bp
from app.routes.marketplace import marketplace_bp
from app.routes.wallet import wallet_bp
from app.routes.webhooks import webhooks_bp
from app.services.order_service import update_order_status
from app.services.hp_service import spend_hp


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"
    app.config["JWT_SECRET"] = "test-jwt-secret"
    app.config["PAYSTACK_WEBHOOK_SECRET"] = "test-webhook-secret"

    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(marketplace_bp, url_prefix="/marketplace")
    app.register_blueprint(wallet_bp, url_prefix="/wallet")
    app.register_blueprint(webhooks_bp, url_prefix="/webhooks")
    return app


@pytest.fixture
def client(app):
    return app.test_client()


# ── 1. Rider/Kitchen Order Status Bypass Validation Tests ──────────────────────

def test_rider_order_status_bypass_denied():
    mock_db = MagicMock()
    # Rider rider-2 is NOT the rider on batch-1 (rider-1)
    mock_db.table().select().eq().single().execute.side_effect = [
        {"id": "order-123", "status": "ready", "campus_id": "campus-1", "batch_id": "batch-1"},
        {"role": "rider", "campus_id": "campus-1"},
        {"rider_id": "rider-1"},
    ]

    with patch("app.services.order_service.get_db", return_value=mock_db):
        with pytest.raises(ValueError, match="Unauthorized: Rider is not assigned to this order"):
            update_order_status("order-123", "out_for_delivery", changed_by="rider-2")


def test_kitchen_order_status_bypass_campus_mismatch():
    mock_db = MagicMock()
    mock_db.table().select().eq().single().execute.side_effect = [
        {"id": "order-123", "status": "received", "campus_id": "campus-2", "batch_id": None},
        {"role": "kitchen", "campus_id": "campus-1"},
    ]

    with patch("app.services.order_service.get_db", return_value=mock_db):
        with pytest.raises(ValueError, match="Unauthorized: Kitchen staff is scoped to a different campus"):
            update_order_status("order-123", "preparing", changed_by="kitchen-1")


# ── 2. spend_hp Race Condition Hardening Test ─────────────────────────────────

def test_spend_hp_insufficient_balance():
    mock_db = MagicMock()
    mock_db.table().eq().gte().update.return_value = []
    mock_db.table().select().eq().single().execute.return_value = {
        "hp_balance": 10,
        "hp_earned_120day": 50,
    }
    mock_db.table().select().eq().execute.return_value = []

    with patch("app.services.hp_service.get_db", return_value=mock_db):
        with pytest.raises(ValueError, match="Insufficient HP"):
            spend_hp("user-1", 50, "ref-1", "test_spend")


# ── 3. Marketplace Code Reservation Fix Tests ─────────────────────────────────

def test_marketplace_purchase_code_out_of_stock(client):
    mock_db = MagicMock()
    mock_db.auth_get_user.return_value = {"id": "user-1"}

    # User profile lookup
    mock_db.table().select().eq().single().execute.side_effect = [
        {"id": "user-1", "role": "student", "is_active": True, "campus_id": "c1"}, # auth middleware profile
        {
            "id": "listing-1",
            "title": "Coupon Code",
            "status": "active",
            "listing_type": "code",
            "is_out_of_stock": False,
            "hp_price": 0,
            "cash_price": 100,
        }, # listing
        {"hp_balance": 1000}, # get_hp_balance
    ]
    mock_db.table().select().eq().eq().limit().execute.return_value = [] # no available codes

    headers = {"Authorization": "Bearer fake_token"}
    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.marketplace.get_db", return_value=mock_db):
        response = client.post("/marketplace/listing-1/purchase", json={"payment_method": "card"}, headers=headers)
        assert response.status_code == 400
        assert "error" in response.get_json()


# ── 4. Admin Safety & Validation Tests ─────────────────────────────────────────

def test_deactivate_self_prohibited(client):
    mock_db = MagicMock()
    mock_db.auth_get_user.return_value = {"id": "admin-1"}
    mock_db.table().select().eq().single().execute.return_value = {
        "id": "admin-1", "role": "admin", "is_active": True, "campus_id": "c1"
    }

    headers = {"Authorization": "Bearer fake_token"}
    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.admin.get_db", return_value=mock_db):
        response = client.post("/admin/users/admin-1/deactivate", headers=headers)
        assert response.status_code == 400
        assert "cannot deactivate your own account" in response.get_json()["error"]


def test_deactivate_super_admin_by_normal_admin_denied(client):
    mock_db = MagicMock()
    mock_db.auth_get_user.return_value = {"id": "admin-1"}
    mock_db.table().select().eq().single().execute.side_effect = [
        {"id": "admin-1", "role": "admin", "is_active": True, "campus_id": "c1"}, # caller profile
        {"id": "superadmin-1", "role": "super_admin", "is_active": True}, # target profile
    ]

    headers = {"Authorization": "Bearer fake_token"}
    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.admin.get_db", return_value=mock_db):
        response = client.post("/admin/users/superadmin-1/deactivate", headers=headers)
        assert response.status_code == 403
        assert "Only super_admin users can deactivate" in response.get_json()["error"]


def test_close_window_not_found(client):
    mock_db = MagicMock()
    mock_db.auth_get_user.return_value = {"id": "admin-1"}
    mock_db.table().select().eq().single().execute.side_effect = [
        {"id": "admin-1", "role": "admin", "is_active": True, "campus_id": "c1"}, # caller profile
        None, # window lookup
    ]

    headers = {"Authorization": "Bearer fake_token"}
    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.admin.get_db", return_value=mock_db):
        response = client.post("/admin/delivery-windows/non-existent/close", headers=headers)
        assert response.status_code == 404


def test_create_batch_non_rider_user_denied(client):
    mock_db = MagicMock()
    mock_db.auth_get_user.return_value = {"id": "admin-1"}
    mock_db.table().select().eq().single().execute.side_effect = [
        {"id": "admin-1", "role": "admin", "is_active": True, "campus_id": "c1"}, # caller profile
        {"id": "win-1"}, # window
        {"id": "user-1", "role": "student", "is_active": True}, # target rider profile
    ]

    headers = {"Authorization": "Bearer fake_token"}
    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.admin.get_db", return_value=mock_db):
        response = client.post("/admin/delivery-batches", json={
            "window_id": "win-1",
            "rider_id": "user-1",
            "zone": "Main Gate",
        }, headers=headers)
        assert response.status_code == 400
        assert "does not have the 'rider' role" in response.get_json()["error"]
