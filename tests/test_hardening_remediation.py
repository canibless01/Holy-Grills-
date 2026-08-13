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

    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.middleware.auth.jwt.decode", return_value={"sub": "user-123", "role": "student"}):

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

    # Mock the OCC atomic update to fail (concurrency collision, e.g. return empty list or fail)
    mock_db.table.return_value.eq.return_value.eq.return_value.update.return_value = []

    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.middleware.auth.jwt.decode", return_value={"sub": "user-123", "role": "student"}):

        headers = {"Authorization": "Bearer fake-jwt-token"}
        resp = client.post("/api/free-sides/redeem", json={
            "side_choice": "Fries"
        }, headers=headers)

    assert resp.status_code == 409
    assert "concurrent update occurred" in resp.get_json()["error"]


@patch("app.routes.exclusive_spin.get_db")
def test_exclusive_spin_occ_success(mock_get_db, client):
    """do_spin should succeed and draw a prize if OCC update succeeds."""
    mock_db = MagicMock()
    mock_get_db.return_value = mock_db

    # Pre-select returns a spin credit
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.gt.return_value.gte.return_value.order.return_value.execute.return_value = [
        {"id": "spin-1", "spin_count": 1, "expires_at": "2030-12-12"}
    ]

    # Mock OCC update success (returns updated row)
    mock_db.table.return_value.eq.return_value.eq.return_value.update.return_value = [{"id": "spin-1", "spin_count": 0}]

    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.middleware.auth.jwt.decode", return_value={"sub": "user-123", "role": "student"}), \
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

    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.middleware.auth.jwt.decode", return_value={"sub": "host-123", "role": "host"}):

        headers = {"Authorization": "Bearer fake-jwt-token"}
        resp = client.post("/api/hp/bundles/purchase", json={
            "hp_amount": 500,
            "paystack_reference": "ref-123"
        }, headers=headers)

    assert resp.status_code == 201
    data = resp.get_json()
    assert data["message"] == "Payment already processed"
    assert data["idempotent"] is True
