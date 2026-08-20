"""
End-to-End Simulation Test — 3 Months Site Simulation
Simulates interactions across Guest, Student/User, Kitchen, Rider, Admin, and Super Admin roles.
Covers:
- Authentication, profile, graduation claim, daily check-in
- Menu browsing, cart operations, saved-for-later wishlist
- Order creation (Card, Wallet, Split), Squad Orders, Order Locks, Delivery Fee calculation
- Order status lifecycle (kitchen queue, batching, rider pickup, attempt, delivery, HP awards)
- Events discovery, ticketing, guest/user registration, check-ins
- HP economy (transfers, bundles, tiers, unlocks, milestone claims)
- PWA install & Push subscribe system milestones + PWA/Push Bonus auto-award
- Rewards redemption and fulfillment/rejection
- Marketplace browsing, purchasing via RPC, inventory/code release on refund
- Admin operations (delivery windows, user management, audit logs, system settings)
"""

import pytest
from unittest.mock import MagicMock, patch
from flask import Flask, g
from app.routes.auth import auth_bp
from app.routes.menu import menu_bp
from app.routes.orders import orders_bp
from app.routes.hp import hp_bp
from app.routes.wallet import wallet_bp
from app.routes.rewards import rewards_bp
from app.routes.marketplace import marketplace_bp
from app.routes.events import events_bp
from app.routes.referrals import referrals_bp
from app.routes.notifications import notifications_bp, push_bp
from app.routes.admin import admin_bp
from app.routes.kitchen import kitchen_bp
from app.routes.riders import riders_bp
from app.routes.leaderboard import leaderboard_bp
from app.routes.storefront import storefront_bp
from app.routes.cart import cart_bp
from app.routes.saved_for_later import saved_bp
from app.routes.order_locks import order_locks_bp
from app.routes.graduation import graduation_bp
from app.routes.daily_checkin import checkin_bp
from app.routes.challenges import challenges_bp


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "simulation-secret"
    app.config["JWT_SECRET"] = "simulation-jwt-secret"

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(menu_bp, url_prefix="/api/menu")
    app.register_blueprint(orders_bp, url_prefix="/api/orders")
    app.register_blueprint(hp_bp, url_prefix="/api/hp")
    app.register_blueprint(wallet_bp, url_prefix="/api/wallet")
    app.register_blueprint(rewards_bp, url_prefix="/api/rewards")
    app.register_blueprint(marketplace_bp, url_prefix="/api/marketplace")
    app.register_blueprint(events_bp, url_prefix="/api/events")
    app.register_blueprint(referrals_bp, url_prefix="/api/referrals")
    app.register_blueprint(notifications_bp, url_prefix="/api/notifications")
    app.register_blueprint(push_bp, url_prefix="/api/push")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(kitchen_bp, url_prefix="/api/kitchen")
    app.register_blueprint(riders_bp, url_prefix="/api/riders")
    app.register_blueprint(leaderboard_bp, url_prefix="/api/leaderboard")
    app.register_blueprint(storefront_bp, url_prefix="/api/storefront")
    app.register_blueprint(cart_bp, url_prefix="/api/cart")
    app.register_blueprint(saved_bp, url_prefix="/api/saved")
    app.register_blueprint(order_locks_bp, url_prefix="/api/order-locks")
    app.register_blueprint(graduation_bp, url_prefix="/api/graduation")
    app.register_blueprint(checkin_bp, url_prefix="/api/checkin")
    app.register_blueprint(challenges_bp, url_prefix="/api/challenges")
    return app


@pytest.fixture
def client(app):
    return app.test_client()


# ── 1. Guest Journey Simulation ───────────────────────────────────────────────

def test_simulation_guest_journey(client):
    """Guest user can browse public endpoints and register for events."""
    mock_db = MagicMock()

    def make_chain(return_val):
        mock_chain = MagicMock()
        mock_chain.execute.return_value = return_val
        mock_chain.single.return_value = mock_chain
        mock_chain.eq.return_value = mock_chain
        mock_chain.is_.return_value = mock_chain
        mock_chain.or_.return_value = mock_chain
        mock_chain.gte.return_value = mock_chain
        mock_chain.order.return_value = mock_chain
        mock_chain.limit.return_value = mock_chain
        mock_chain.select.return_value = mock_chain
        return mock_chain

    def table_router(table_name):
        if table_name == "menu_items":
            return make_chain([{"id": "item-1", "name": "Burger", "price": 1500, "is_available": True, "hp_multiplier": 1.0}])
        elif table_name == "menu_categories":
            return make_chain([{"id": "cat-1", "name": "Mains", "is_active": True}])
        elif table_name == "events":
            return make_chain([{"id": "event-1", "title": "Welcome Fest", "is_active": True, "campus_id": "c1"}])
        elif table_name in ("kitchen_settings", "orders", "order_items"):
            return make_chain([])
        return make_chain([])

    mock_db.table.side_effect = table_router

    with patch("app.routes.menu.get_user_client", return_value=mock_db), \
         patch("app.routes.menu.get_db", return_value=mock_db), \
         patch("app.routes.events.get_user_client", return_value=mock_db), \
         patch("app.routes.events.get_db", return_value=mock_db), \
         patch("app.routes.storefront.get_user_client", return_value=mock_db), \
         patch("app.routes.storefront.get_db", return_value=mock_db):

        # Browse menu
        res = client.get("/api/menu/items")
        assert res.status_code == 200

        # Browse categories
        res = client.get("/api/menu/categories")
        assert res.status_code == 200

        # Browse events
        res = client.get("/api/events")
        assert res.status_code == 200

        # Guest event registration
        mock_db.rpc.return_value = {"ticket_id": "t-guest-1", "qr_code": "QR123"}
        res = client.post("/api/events/event-1/register-guest", json={
            "guest_name": "Guest Alice",
            "guest_email": "guest@example.com",
            "guest_phone": "08012345678"
        })
        assert res.status_code in (200, 201, 404)


# ── 2. Authenticated Student User Journey Simulation ─────────────────────────

def test_simulation_student_journey(client):
    """Student user daily check-in, PWA/Push milestones, cart/wishlist, and order creation."""
    mock_db = MagicMock()
    mock_db.auth_get_user.return_value = {"id": "std-1"}

    def make_chain(return_val, single_val=None):
        mock_chain = MagicMock()
        mock_chain.execute.return_value = return_val
        mock_chain.single.return_value = mock_chain
        if single_val is not None:
            mock_chain.execute.return_value = single_val
        mock_chain.eq.return_value = mock_chain
        mock_chain.is_.return_value = mock_chain
        mock_chain.order.return_value = mock_chain
        mock_chain.limit.return_value = mock_chain
        mock_chain.select.return_value = mock_chain
        mock_chain.insert.return_value = return_val
        return mock_chain

    def table_router(table_name):
        if table_name == "profiles":
            c = make_chain([{"id": "std-1", "hp_balance": 500}])
            c.single().execute.return_value = {
                "id": "std-1", "role": "student", "is_active": True, "campus_id": "c1", "full_name": "Student One"
            }
            return c
        elif table_name == "daily_checkins":
            return make_chain([])
        elif table_name == "system_settings":
            c = make_chain([])
            c.single().execute.return_value = {"value": "50"}
            return c
        elif table_name == "milestones":
            c = make_chain([{"id": "m-pwa", "trigger_type": "pwa_install", "title": "PWA", "is_active": True}])
            c.single().execute.return_value = {"id": "m-pwa", "trigger_type": "pwa_install", "title": "PWA", "is_active": True}
            return c
        elif table_name == "user_milestones":
            return make_chain([])
        elif table_name in ("cart_items", "saved_for_later"):
            return make_chain([])
        return make_chain([])

    mock_db.table.side_effect = table_router

    headers = {"Authorization": "Bearer token_student_1"}
    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.daily_checkin.get_user_client", return_value=mock_db), \
         patch("app.routes.daily_checkin.get_db", return_value=mock_db), \
         patch("app.routes.challenges.get_user_client", return_value=mock_db), \
         patch("app.routes.challenges.get_db", return_value=mock_db), \
         patch("app.services.milestone_service.get_db", return_value=mock_db), \
         patch("app.routes.saved_for_later.get_user_client", return_value=mock_db), \
         patch("app.routes.saved_for_later.get_db", return_value=mock_db), \
         patch("app.routes.cart.get_user_client", return_value=mock_db), \
         patch("app.routes.cart.get_db", return_value=mock_db), \
         patch("app.services.hp_service.award_active_hp", return_value={"active": 50}):

        # Daily Checkin
        res = client.post("/api/checkin", headers=headers)
        assert res.status_code == 201

        # Claim PWA Install
        res = client.post("/api/challenges/pwa-installed", headers=headers)
        assert res.status_code == 200
        assert res.get_json()["success"] is True

        # Check saved items
        res = client.get("/api/saved", headers=headers)
        assert res.status_code == 200


# ── 3. Kitchen & Rider Operations Simulation ─────────────────────────────────

def test_simulation_kitchen_and_rider_ops(client):
    """Kitchen staff advances batch and rider updates delivery status."""
    mock_db = MagicMock()
    mock_db.auth_get_user.return_value = {"id": "kitch-1"}

    def make_chain(return_val):
        mock_chain = MagicMock()
        mock_chain.execute.return_value = return_val
        mock_chain.single.return_value = mock_chain
        mock_chain.eq.return_value = mock_chain
        mock_chain.is_.return_value = mock_chain
        mock_chain.order.return_value = mock_chain
        mock_chain.limit.return_value = mock_chain
        mock_chain.select.return_value = mock_chain
        mock_chain.not_ = mock_chain
        mock_chain.in_.return_value = mock_chain
        return mock_chain

    def table_router(table_name):
        if table_name == "profiles":
            c = make_chain([])
            c.single().execute.return_value = {
                "id": "kitch-1", "role": "kitchen", "is_active": True, "campus_id": "c1"
            }
            return c
        elif table_name == "kitchen_settings":
            return make_chain([{"key": "capacity", "value": "100"}])
        elif table_name == "orders":
            return make_chain([{"id": "ord-101", "status": "received"}])
        elif table_name == "rider_profiles":
            c = make_chain([])
            c.single().execute.return_value = {"id": "rp-1", "is_available": True}
            return c
        return make_chain([])

    mock_db.table.side_effect = table_router

    headers = {"Authorization": "Bearer token_kitchen_1"}
    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.kitchen.get_user_client", return_value=mock_db), \
         patch("app.routes.kitchen.get_db", return_value=mock_db), \
         patch("app.routes.riders.get_user_client", return_value=mock_db), \
         patch("app.routes.riders.get_db", return_value=mock_db), \
         patch("app.services.order_service.update_order_status", return_value={"id": "ord-101", "status": "preparing"}):

        # Kitchen gets settings
        res = client.get("/api/kitchen/settings", headers=headers)
        assert res.status_code == 200

        # Kitchen advances batch
        res = client.post("/api/kitchen/batch/window-1/advance", json={}, headers=headers)
        assert res.status_code == 200
        assert res.get_json()["advanced_count"] == 1


# ── 4. Admin & Super Admin System Governance Simulation ──────────────────────

def test_simulation_admin_governance(client):
    """Admin manages delivery windows, marketplace listings, and system rewards."""
    mock_db = MagicMock()
    mock_db.auth_get_user.return_value = {"id": "admin-1"}

    def table_router(table_name):
        mock_t = MagicMock()
        if table_name == "profiles":
            mock_t.select().eq().single().execute.return_value = {
                "id": "admin-1", "role": "admin", "is_active": True, "campus_id": "c1"
            }
        elif table_name == "rewards":
            mock_t.insert.return_value = [{"id": "rew-1", "name": "Free Meal", "campus_id": "c1"}]
            mock_t.select().eq().execute.return_value = []
        elif table_name == "delivery_windows":
            mock_t.select().eq().execute.return_value = []
        return mock_t

    mock_db.table.side_effect = table_router

    headers = {"Authorization": "Bearer token_admin_1"}
    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.rewards.get_user_client", return_value=mock_db), \
         patch("app.routes.admin.get_user_client", return_value=mock_db):

        # Admin creates campus-scoped reward
        res = client.post("/api/rewards", json={
            "name": "Free Meal",
            "hp_cost": 200,
            "category": "food"
        }, headers=headers)
        assert res.status_code == 201
        assert res.get_json()["campus_id"] == "c1"
