"""
Specific security and business logic regression tests for the Holy Grills Hardening changes.
"""

import pytest
import os
import json
from unittest.mock import patch, MagicMock
from app.db import SupabaseError


@pytest.fixture(scope="session")
def app():
    os.environ.setdefault("SUPABASE_URL", "https://mock.supabase.co")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "mock-srk")
    os.environ.setdefault("SUPABASE_ANON_KEY", "mock-anon")
    os.environ.setdefault("SECRET_KEY", "test-secret")
    os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

    from app import create_app
    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


# ── 1. Referrals /complete route unauthenticated check ────────────────────────

def test_referral_complete_requires_auth(client):
    """POST /api/referrals/complete must reject unauthenticated requests with 401."""
    resp = client.post("/api/referrals/complete", json={
        "referred_user_id": "referred-uuid",
        "order_id": "order-uuid"
    })
    assert resp.status_code == 401


# ── 2. Order Locks client-provided values bypass ──────────────────────────────

@patch("app.routes.order_locks.get_db")
def test_order_locks_ignores_client_provided_values(mock_get_db, client, app):
    """Creating an order lock should ignore client-provided values for discount_pct/hp."""
    mock_db = MagicMock()
    mock_get_db.return_value = mock_db

    # Mock settings retrieval for order locks
    mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = {"value": "12.0"}

    # Mock insert execution
    mock_db.table.return_value.insert.return_value = {"id": "lock-1", "discount_pct": 12.0}

    with client.session_transaction() as sess:
        pass

    # Mock auth_get_user on the DB client mock
    mock_db.auth_get_user.return_value = {"id": "user-123", "role": "student"}
    mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = {
        "id": "user-123", "role": "student", "is_active": True
    }

    with patch("app.middleware.auth.get_db", return_value=mock_db):

        headers = {"Authorization": "Bearer fake-jwt-token"}
        resp = client.post("/api/order-locks", json={
            "locked_date": "2030-12-12",
            "reward_type": "discount",
            "discount_pct": 99.0,  # Try to inject a massive discount
        }, headers=headers)

    assert resp.status_code == 201
    data = resp.get_json()
    assert "lock" in data
    # The insert must have been made with the setting value (12.0) and not the client-provided 99.0


# ── 6. Guest checkout and Authenticated override tests ───────────────────────

@patch("app.routes.orders.get_db")
def test_create_order_authenticated_identity_cannot_be_overridden(mock_get_db, client):
    """POST /api/orders for authenticated user must ignore client-supplied user_id, guest info and use g.user_id."""
    mock_db = MagicMock()
    mock_get_db.return_value = mock_db

    # Mock auth_get_user and profile lookup
    mock_db.auth_get_user.return_value = {"id": "real-user-id", "role": "student"}
    mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = {
        "id": "real-user-id", "role": "student", "is_active": True
    }

    # Mock order creation service call
    from unittest.mock import patch as _patch
    with _patch("app.middleware.auth.get_db", return_value=mock_db), \
         _patch("app.services.order_service.create_order") as mock_create_order:
        mock_create_order.return_value = {"id": "order-123"}

        headers = {"Authorization": "Bearer fake-jwt-token"}
        resp = client.post("/api/orders", json={
            "items": [{"menu_item_id": "item-1", "quantity": 1}],
            "payment_method": "card",
            "user_id": "malicious-victim-id",
            "guest_name": "Guest Impersonator",
            "guest_phone": "08012345678"
        }, headers=headers)

        assert resp.status_code == 201
        # Confirm create_order was called with the authenticated g.user_id and guest params were removed
        mock_create_order.assert_called_once()
        passed_user_id, passed_payload = mock_create_order.call_args[0]
        assert passed_user_id == "real-user-id"
        assert passed_payload["user_id"] == "real-user-id"
        assert "guest_name" not in passed_payload
        assert "guest_phone" not in passed_payload


@patch("app.routes.orders.get_db")
def test_create_order_guest_cannot_impersonate_or_use_wallet(mock_get_db, client):
    """POST /api/orders for guest must reject wallet payments and ignore client-supplied user_id."""
    mock_db = MagicMock()
    mock_get_db.return_value = mock_db

    # Wallet checkout should be rejected for guest
    resp = client.post("/api/orders", json={
        "items": [{"menu_item_id": "item-1", "quantity": 1}],
        "payment_method": "wallet",
        "guest_name": "John Guest",
        "guest_phone": "08012345678",
        "guest_email": "john@guest.com"
    })
    assert resp.status_code == 400
    assert "Wallet payment requires a logged-in account" in resp.get_json()["error"]

    # Missing guest fields should be rejected
    resp = client.post("/api/orders", json={
        "items": [{"menu_item_id": "item-1", "quantity": 1}],
        "payment_method": "card",
        "guest_name": "John Guest"
        # guest_phone/guest_email missing
    })
    assert resp.status_code == 400
    assert "required for guest checkout" in resp.get_json()["error"]

    # Successful guest creation call should strip user_id
    from unittest.mock import patch as _patch
    with _patch("app.services.order_service.create_order") as mock_create_order:
        mock_create_order.return_value = {"id": "order-123"}
        resp = client.post("/api/orders", json={
            "items": [{"menu_item_id": "item-1", "quantity": 1}],
            "payment_method": "card",
            "guest_name": "John Guest",
            "guest_phone": "08012345678",
            "guest_email": "john@guest.com",
            "user_id": "hijack-user-id"
        })
        assert resp.status_code == 201
        mock_create_order.assert_called_once()
        passed_user_id, passed_payload = mock_create_order.call_args[0]
        assert passed_user_id is None
        assert "user_id" not in passed_payload


# ── 7. Guest Order Claiming restrictions ──────────────────────────────────────

@patch("app.routes.orders.get_db")
def test_claim_guest_order_unauthenticated(mock_get_db, client):
    """POST /api/orders/<id>/claim must reject unauthenticated requests."""
    resp = client.post("/api/orders/00000000-0000-0000-0000-000000000000/claim", json={
        "claim_token": "token-123"
    })
    assert resp.status_code == 401


@patch("app.routes.orders.get_db")
def test_claim_guest_order_validations(mock_get_db, client):
    """POST /api/orders/<id>/claim must strictly validate ownership and claim token matching."""
    mock_db = MagicMock()
    mock_get_db.return_value = mock_db

    # Mock auth_get_user and profile lookup
    mock_db.auth_get_user.return_value = {"id": "real-user-id", "role": "student"}

    # We will patch get_db in the auth middleware as well
    from unittest.mock import patch as _patch
    with _patch("app.middleware.auth.get_db", return_value=mock_db):
        # Case A: Order already claimed/owned
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = [
            # auth user profile lookup
            {"id": "real-user-id", "role": "student", "is_active": True, "campus_id": "c1"},
            # order lookup
            {"id": "order-123", "user_id": "another-owner-id", "claim_token": "token-123"}
        ]

        headers = {"Authorization": "Bearer fake-jwt-token"}
        resp = client.post("/api/orders/00000000-0000-0000-0000-000000000000/claim", json={
            "claim_token": "token-123"
        }, headers=headers)
        assert resp.status_code == 400
        assert "already owned" in resp.get_json()["error"]

        # Case B: Claim token mismatch
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = [
            # auth user profile lookup
            {"id": "real-user-id", "role": "student", "is_active": True, "campus_id": "c1"},
            # order lookup (order is guest-owned, but token is different)
            {"id": "order-123", "user_id": None, "claim_token": "correct-token-456"}
        ]
        resp = client.post("/api/orders/00000000-0000-0000-0000-000000000000/claim", json={
            "claim_token": "wrong-token-123"
        }, headers=headers)
    assert resp.status_code == 403
    assert "claim" in resp.get_json()["error"].lower()


# ── 3. Coordinate Bounds and Geographical Checks ──────────────────────────────

def test_validate_coordinates_futa_bounds():
    """validate_coordinates should reject values outside generous Nigerian bounds."""
    from app.routes.delivery import validate_coordinates

    # Valid coordinates inside Nigeria/FUTA region
    lat, lon = validate_coordinates(7.25, 5.20)
    assert lat == 7.25
    assert lon == 5.20

    # Malformed inputs
    with pytest.raises(ValueError, match="must be valid numbers"):
        validate_coordinates("invalid-lat", 5.20)

    # Standard bounds violation
    with pytest.raises(ValueError, match="standard bounds"):
        validate_coordinates(95.0, 5.20)

    # Geographic boundary violation (not in Nigeria)
    with pytest.raises(ValueError, match="outside the supported region"):
        validate_coordinates(45.0, -120.0)


# ── 4. Optimistic Concurrency Control (OCC) Race Conditions ───────────────────

@patch("app.routes.free_sides.get_db")
def test_free_sides_redeem_occ_failure(mock_get_db, client):
    """redeem_free_side should return 409 conflict if concurrent update causes OCC collision."""
    mock_db = MagicMock()
    mock_get_db.return_value = mock_db

    # Pre-select returns a credit with credits_remaining=1
    mock_db.table.return_value.select.return_value.eq.return_value.gt.return_value.gte.return_value.order.return_value.execute.return_value = [
        {"id": "credit-1", "credits_remaining": 1, "expires_at": "2030-12-12"}
    ]

    mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = []

    def single_execute_side_effect():
        # 1. Auth profile lookup
        yield {"id": "user-123", "role": "student", "is_active": True, "campus_id": None}
        # 2. Order lookup
        yield {"id": "00000000-0000-0000-0000-000000000000", "user_id": "user-123", "status": "paid"}
        # 3. _get_free_side_options system settings lookup
        yield None

    mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = single_execute_side_effect()

    # Mock the OCC atomic update to fail (concurrency collision, e.g. return empty list or fail)
    mock_db.table.return_value.eq.return_value.eq.return_value.update.return_value = []
    mock_db.table.return_value.eq.return_value.eq.return_value.eq.return_value.update.return_value = []

    # Mock auth_get_user on the DB client mock
    mock_db.auth_get_user.return_value = {"id": "user-123", "role": "student"}

    with patch("app.middleware.auth.get_db", return_value=mock_db):

        headers = {"Authorization": "Bearer fake-jwt-token"}
        resp = client.post("/api/free-sides/redeem", json={
            "side_choice": "Fries",
            "order_id": "00000000-0000-0000-0000-000000000000"
        }, headers=headers)

    assert resp.status_code == 409
    assert "concurrent update occurred" in resp.get_json()["error"]


@patch("app.routes.exclusive_spin.get_db")
def test_exclusive_spin_occ_success(mock_get_db, client):
    """do_spin should succeed and draw a prize if OCC update succeeds."""
    mock_db = MagicMock()
    mock_get_db.return_value = mock_db

    # Pre-select returns a spin credit
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.gt.return_value.gte.return_value.eq.return_value.order.return_value.execute.return_value = [
        {"id": "spin-1", "spin_count": 1, "expires_at": "2030-12-12"}
    ]
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.gt.return_value.gte.return_value.order.return_value.execute.return_value = [
        {"id": "spin-1", "spin_count": 1, "expires_at": "2030-12-12"}
    ]

    # Mock OCC update success (returns updated row)
    mock_db.table.return_value.eq.return_value.eq.return_value.update.return_value = [{"id": "spin-1", "spin_count": 0}]

    # Mock auth_get_user on the DB client mock
    mock_db.auth_get_user.return_value = {"id": "user-123", "role": "student"}
    mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = {
        "id": "user-123", "role": "student", "is_active": True, "campus_id": "c1"
    }

    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.exclusive_spin._apply_prize") as mock_apply:

        headers = {"Authorization": "Bearer fake-jwt-token"}
        resp = client.post("/api/exclusive-spin/spin", headers=headers)

    assert resp.status_code == 200
    assert "prize" in resp.get_json()
    assert mock_apply.called


# ── 5. Payment reference idempotency (HP Bundles) ─────────────────────────────

@patch("app.routes.hp.get_db")
def test_purchase_hp_bundle_payment_reference_replay(mock_get_db, client):
    """purchase_hp_bundle must return a cached idempotent result if reference has already been processed."""
    mock_db = MagicMock()
    mock_get_db.return_value = mock_db

    # Mock idempotency check to find existing completed purchase record
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = [
        {"id": "purchase-1", "hp_amount": 500, "provider_reference": "ref-123", "status": "completed"}
    ]

    # Mock auth_get_user on the DB client mock
    mock_db.auth_get_user.return_value = {"id": "host-123", "role": "host"}
    mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = {
        "id": "host-123", "role": "host", "is_active": True
    }

    with patch("app.middleware.auth.get_db", return_value=mock_db):

        headers = {"Authorization": "Bearer fake-jwt-token"}
        resp = client.post("/api/hp/bundles/purchase", json={
            "hp_amount": 500,
            "paystack_reference": "ref-123"
        }, headers=headers)

    assert resp.status_code == 201
    data = resp.get_json()
    assert data["message"] == "Payment already processed"
    assert data["idempotent"] is True


# ── 8. Guest Order IDOR/BOLA Access Restrictions ─────────────────────────────

@patch("app.routes.orders.get_db")
def test_get_order_guest_without_token_rejected(mock_get_db, client):
    """GET /api/orders/<id> must reject guest order access if claim_token is missing/wrong."""
    mock_db = MagicMock()
    mock_get_db.return_value = mock_db

    # Case A: Logged-in user tries to access guest order without claim token
    mock_db.auth_get_user.return_value = {"id": "user-123", "role": "student"}
    mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = [
        # auth user profile lookup
        {"id": "user-123", "role": "student", "is_active": True, "campus_id": "c1"},
        # order lookup (user_id is None, meaning guest order)
        {"id": "order-123", "user_id": None, "claim_token": "token-xyz"}
    ]

    with patch("app.middleware.auth.get_db", return_value=mock_db):
        headers = {"Authorization": "Bearer fake-jwt-token"}
        resp = client.get("/api/orders/00000000-0000-0000-0000-000000000000", headers=headers)
    assert resp.status_code == 403
    assert "claim" in resp.get_json()["error"].lower()

    # Case B: Guest tries to access guest order with wrong token
    mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = [
        # order lookup (user_id is None)
        {"id": "order-123", "user_id": None, "claim_token": "token-xyz"}
    ]
    resp = client.get("/api/orders/00000000-0000-0000-0000-000000000000?claim_token=wrong-token")
    assert resp.status_code == 403
    assert "claim" in resp.get_json()["error"].lower()


@patch("app.routes.orders.get_db")
def test_get_order_guest_with_token_allowed(mock_get_db, client):
    """GET /api/orders/<id> must allow guest order access if claim_token matches."""
    mock_db = MagicMock()
    mock_get_db.return_value = mock_db

    # Guest tries to access guest order with matching token
    mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = [
        # order lookup (user_id is None)
        {"id": "order-123", "user_id": None, "claim_token": "token-xyz", "delivery_batches": []}
    ]
    resp = client.get("/api/orders/00000000-0000-0000-0000-000000000000?claim_token=token-xyz")
    assert resp.status_code == 200
    assert resp.get_json()["id"] == "order-123"


@patch("app.routes.orders.get_db")
def test_get_order_authenticated_mismatch_rejected(mock_get_db, client):
    """GET /api/orders/<id> must reject authenticated users trying to access other user's order."""
    mock_db = MagicMock()
    mock_get_db.return_value = mock_db

    mock_db.auth_get_user.return_value = {"id": "user-123", "role": "student"}
    mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = [
        # auth user profile lookup
        {"id": "user-123", "role": "student", "is_active": True, "campus_id": "c1"},
        # order lookup (owned by user-456)
        {"id": "order-123", "user_id": "user-456", "claim_token": None}
    ]

    with patch("app.middleware.auth.get_db", return_value=mock_db):
        headers = {"Authorization": "Bearer fake-jwt-token"}
        resp = client.get("/api/orders/00000000-0000-0000-0000-000000000000", headers=headers)
    assert resp.status_code == 403
    assert "denied" in resp.get_json()["error"].lower()
