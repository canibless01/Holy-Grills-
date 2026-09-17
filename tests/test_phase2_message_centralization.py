import pytest
from unittest.mock import patch, MagicMock
from app import create_app
from app.messages import MSG

@pytest.fixture
def app():
    app = create_app()
    app.config["TESTING"] = True
    app.config["CLOUDINARY_API_KEY"] = "fake-key"
    app.config["CLOUDINARY_API_SECRET"] = "fake-secret"
    app.config["CLOUDINARY_CLOUD_NAME"] = "fake-cloud"
    return app

@pytest.fixture
def client(app):
    return app.test_client()

def test_messages_constants_exist():
    # Phase 2
    assert MSG.REGISTER_SUCCESS == "Welcome to {platform}! Your account is ready."
    assert MSG.LOGIN_SUCCESS == "Welcome back!"
    assert MSG.SESSION_REFRESHED == "Session refreshed"
    assert MSG.PROFILE_PHOTO_UPDATED == "Profile photo updated"
    assert MSG.PROFILE_UPDATED == "Profile updated"
    assert MSG.ADDRESS_ADDED == "Address saved"
    assert MSG.ADDRESS_UPDATED == "Address updated"
    assert MSG.VERIFICATION_EMAIL_SENT == "Verification email sent — check your inbox"
    assert MSG.PASSWORD_RESET_SENT == "If that email exists, a reset link is on its way"
    assert MSG.PWA_INSTALL_RECORDED == "Thanks for installing the app!"
    assert MSG.PUSH_SUBSCRIBED == "Push notifications enabled"
    assert MSG.DELIVERY_FEE_CALCULATED == "Delivery fee calculated"
    assert MSG.FLASH_REWARD_REDEEMED == "Flash reward redeemed!"
    assert MSG.MARKETPLACE_PURCHASE_SUCCESS == "Purchase complete!"
    assert MSG.NOTIFICATION_MARKED_READ == "Marked as read"
    assert MSG.NOTIFICATION_PREFERENCES_UPDATED == "Notification preferences updated"
    assert MSG.ORDER_PLACED == "Order placed! We'll keep you posted."
    assert MSG.REVIEW_IMAGES_UPLOADED == "Photos added to your review"
    assert MSG.REVIEW_SUBMITTED == "Thanks for your review!"
    assert MSG.ORDER_CLAIMED == "Order linked to your account"
    assert MSG.PROMO_CODE_VALID == "Promo code applied"
    assert MSG.UPLOAD_SIGNATURE_ISSUED == "Ready to upload"
    assert MSG.WALLET_CARD_FUNDING_INITIATED == "Redirecting you to complete payment"
    assert MSG.WALLET_BANK_TRANSFER_INITIATED == "Transfer details ready"

    # Phase 1b
    assert MSG.PHONE_FORMAT_INVALID == "Invalid phone number format. Use international format e.g. +2348012345678."
    assert MSG.DOB_FORMAT_INVALID == "Invalid date of birth. Use YYYY-MM-DD format."
    assert MSG.REGISTER_EMAIL_AMBIGUOUS == "If this email can be registered, you'll receive a confirmation shortly. If you already have an account, try logging in or resetting your password."
    assert MSG.REGISTER_FAILED_RETRY == "Registration failed. Please try again."
    assert MSG.NO_VALID_FIELDS_TO_UPDATE == "No valid fields to update"
    assert MSG.MILESTONE_NOT_FOUND == "Milestone not found or inactive"
    assert MSG.MILESTONE_ADMIN_ONLY == "This milestone is awarded by admins only"
    assert MSG.DELIVERY_TYPE_VALUE_INVALID == "Invalid delivery type"
    assert MSG.ADDRESS_ACCESS_UNAUTHORIZED == "This isn't one of your saved addresses"
    assert MSG.GUEST_NO_WALLET_PAYMENTS == "Guest orders cannot use wallet payments."
    assert MSG.GUEST_DETAILS_REQUIRED == "Guest orders require your name, phone, and email."
    assert MSG.PROMO_CODE_MAX_USES == "You've already used this promo code the maximum number of times"
    assert MSG.COORDINATES_INVALID == "Latitude and longitude must be valid numbers"
    assert MSG.COORDINATES_OUT_OF_BOUNDS == "Latitude and longitude must be within standard bounds"
    assert MSG.COORDINATES_UNSUPPORTED_REGION == "This location is outside our supported delivery region"
    assert MSG.ACCOUNT_DEACTIVATED == "Your account has been deactivated. Contact support if you think this is a mistake."
    assert MSG.SESSION_INVALID == "Your session has expired — please log in again"
    assert MSG.SESSION_MALFORMED == "Please log in again"
    assert MSG.DELIVERY_OUTSIDE_AREA == "This location is outside our delivery area."

def test_validate_promo_returns_message(client):
    with patch("app.services.order_service._apply_promo") as mock_apply:
        mock_apply.return_value = {"discount": 500, "promo_code_id": "p123"}
        resp = client.post("/api/orders/validate-promo", json={"code": "SAVE500", "order_subtotal": 2000})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["valid"] is True
        assert data["message"] == MSG.PROMO_CODE_VALID

def test_upload_signature_returns_message(client):
    mock_db = MagicMock()
    mock_db.auth_get_user.return_value = {"id": "user-123", "role": "student"}
    mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = {
        "id": "user-123", "role": "student", "is_active": True
    }
    with patch("app.middleware.auth.get_db", return_value=mock_db):
        resp = client.post("/api/upload/signature", json={"type": "profile_photo"}, headers={"Authorization": "Bearer fake-token"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert "signature" in data
        assert data["message"] == MSG.UPLOAD_SIGNATURE_ISSUED

def test_admin_academic_calendar_crud(client):
    mock_db = MagicMock()
    mock_db.auth_get_user.return_value = {"id": "admin-1", "role": "admin"}
    mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = {
        "id": "admin-1", "role": "admin", "is_active": True
    }
    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.academic_calendar.get_user_client", return_value=mock_db):
        mock_db.table.return_value.insert.return_value = [{"id": "cal-1", "name": "First Semester 2024/2025"}]
        resp = client.post(
            "/api/admin/academic-calendar",
            headers={"Authorization": "Bearer fake-token"},
            json={
                "period_type": "semester",
                "name": "First Semester 2024/2025",
                "start_date": "2024-11-01",
                "end_date": "2025-03-01",
                "academic_year": "2024/2025"
            }
        )
        assert resp.status_code == 201
        assert resp.get_json()["id"] == "cal-1"

        mock_db.table.return_value.select.return_value.order.return_value.execute.return_value = [{"id": "cal-1"}]
        resp_list = client.get("/api/admin/academic-calendar", headers={"Authorization": "Bearer fake-token"})
        assert resp_list.status_code == 200
        assert resp_list.get_json()["count"] == 1

        mock_db.table.return_value.eq.return_value.update.return_value = [{"id": "cal-1", "is_active": False}]
        resp_patch = client.patch(
            "/api/admin/academic-calendar/cal-1",
            headers={"Authorization": "Bearer fake-token"},
            json={"is_active": False}
        )
        assert resp_patch.status_code == 200
