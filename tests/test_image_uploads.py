"""
tests/test_image_uploads.py — Unit tests for all 9 image upload endpoints.
"""

import pytest
import os
from unittest.mock import patch, MagicMock


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


def _mock_auth_user(user_id="user-123", role="admin"):
    """Helper to mock db.auth_get_user and profiles/table queries."""
    mock_db = MagicMock()
    mock_db.auth_get_user.return_value = {"id": user_id, "email": "test@example.com"}

    def table_mock(tname):
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.single.return_value = chain
        chain.update.return_value = chain
        chain.insert.return_value = chain

        if tname == "profiles":
            chain.execute.return_value = {
                "id": user_id,
                "full_name": "Test User",
                "role": role,
                "is_active": True,
                "campus_id": "campus-1",
            }
        elif tname == "campuses":
            chain.execute.return_value = {"id": "campus-1"}
        elif tname == "storefront_sections":
            chain.execute.return_value = {"id": "sec-123", "content": {}}
        elif tname == "events":
            chain.execute.return_value = {"id": "event-123", "campus_id": "campus-1"}
        else:
            chain.execute.return_value = {"id": "res-123"}
        return chain

    mock_db.table.side_effect = table_mock
    return mock_db


# 1. USER PROFILE PHOTO
def test_profile_photo_upload_success(client):
    mock_db = _mock_auth_user(user_id="user-123", role="student")
    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.auth.get_db", return_value=mock_db):
        resp = client.post(
            "/api/auth/profile/photo",
            headers={"Authorization": "Bearer valid-token"},
            json={"photo_url": "https://cloudinary.com/user.jpg"},
        )
        assert resp.status_code == 200
        assert resp.get_json() == {"photo_url": "https://cloudinary.com/user.jpg"}


def test_profile_photo_upload_missing_param(client):
    mock_db = _mock_auth_user(user_id="user-123", role="student")
    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.auth.get_db", return_value=mock_db):
        resp = client.post(
            "/api/auth/profile/photo",
            headers={"Authorization": "Bearer valid-token"},
            json={},
        )
        assert resp.status_code == 400
        assert "photo_url is required" in resp.get_json()["error"]


# 2. MENU ITEMS
def test_menu_item_image_upload_success(client):
    mock_db = _mock_auth_user(role="admin")
    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.menu.get_db", return_value=mock_db):
        resp = client.post(
            "/api/menu/items/item-123/image",
            headers={"Authorization": "Bearer admin-token"},
            json={"image_url": "https://cloudinary.com/menu.jpg"},
        )
        assert resp.status_code == 200
        assert resp.get_json() == {"image_url": "https://cloudinary.com/menu.jpg"}


def test_menu_item_image_upload_missing_param(client):
    mock_db = _mock_auth_user(role="admin")
    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.menu.get_db", return_value=mock_db):
        resp = client.post(
            "/api/menu/items/item-123/image",
            headers={"Authorization": "Bearer admin-token"},
            json={},
        )
        assert resp.status_code == 400
        assert "image_url is required" in resp.get_json()["error"]


# 3. EVENT IMAGES
def test_event_image_upload_success(client):
    mock_db = _mock_auth_user(role="admin")
    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.events.get_db", return_value=mock_db):
        resp = client.post(
            "/api/events/event-123/image",
            headers={"Authorization": "Bearer admin-token"},
            json={"image_url": "https://cloudinary.com/event.jpg"},
        )
        assert resp.status_code == 200
        assert resp.get_json() == {"image_url": "https://cloudinary.com/event.jpg"}


def test_event_image_upload_missing_param(client):
    mock_db = _mock_auth_user(role="admin")
    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.events.get_db", return_value=mock_db):
        resp = client.post(
            "/api/events/event-123/image",
            headers={"Authorization": "Bearer admin-token"},
            json={},
        )
        assert resp.status_code == 400
        assert "image_url is required" in resp.get_json()["error"]


# 4. BANNERS
def test_banner_image_upload_success(client):
    mock_db = _mock_auth_user(role="admin")
    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.storefront.get_db", return_value=mock_db):
        resp = client.post(
            "/api/storefront/banners/banner-123/image",
            headers={"Authorization": "Bearer admin-token"},
            json={"image_url": "https://cloudinary.com/banner.jpg", "mobile_image_url": "https://cloudinary.com/mobile_banner.jpg"},
        )
        assert resp.status_code == 200
        assert resp.get_json() == {"image_url": "https://cloudinary.com/banner.jpg"}


def test_banner_image_upload_missing_param(client):
    mock_db = _mock_auth_user(role="admin")
    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.storefront.get_db", return_value=mock_db):
        resp = client.post(
            "/api/storefront/banners/banner-123/image",
            headers={"Authorization": "Bearer admin-token"},
            json={},
        )
        assert resp.status_code == 400
        assert "image_url is required" in resp.get_json()["error"]


# 5. REWARDS
def test_reward_image_upload_success(client):
    mock_db = _mock_auth_user(role="admin")
    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.rewards.get_db", return_value=mock_db):
        resp = client.post(
            "/api/rewards/reward-123/image",
            headers={"Authorization": "Bearer admin-token"},
            json={"image_url": "https://cloudinary.com/reward.jpg"},
        )
        assert resp.status_code == 200
        assert resp.get_json() == {"image_url": "https://cloudinary.com/reward.jpg"}


def test_reward_image_upload_missing_param(client):
    mock_db = _mock_auth_user(role="admin")
    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.rewards.get_db", return_value=mock_db):
        resp = client.post(
            "/api/rewards/reward-123/image",
            headers={"Authorization": "Bearer admin-token"},
            json={},
        )
        assert resp.status_code == 400
        assert "image_url is required" in resp.get_json()["error"]


# 6. MARKETPLACE LISTINGS
def test_marketplace_listing_image_upload_success(client):
    mock_db = _mock_auth_user(role="admin")
    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.marketplace.get_db", return_value=mock_db):
        resp = client.post(
            "/api/marketplace/listings/listing-123/image",
            headers={"Authorization": "Bearer admin-token"},
            json={"image_url": "https://cloudinary.com/listing.jpg"},
        )
        assert resp.status_code == 200
        assert resp.get_json() == {"image_url": "https://cloudinary.com/listing.jpg"}


def test_marketplace_listing_image_upload_missing_param(client):
    mock_db = _mock_auth_user(role="admin")
    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.marketplace.get_db", return_value=mock_db):
        resp = client.post(
            "/api/marketplace/listings/listing-123/image",
            headers={"Authorization": "Bearer admin-token"},
            json={},
        )
        assert resp.status_code == 400
        assert "image_url is required" in resp.get_json()["error"]


# 7. REVIEW IMAGES
def test_review_images_upload_success(client):
    mock_db = _mock_auth_user(user_id="user-123", role="student")
    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.orders.get_db", return_value=mock_db):
        resp = client.post(
            "/api/orders/order-123/review/images",
            headers={"Authorization": "Bearer user-token"},
            json={"image_urls": ["https://cloudinary.com/rev1.jpg", "https://cloudinary.com/rev2.jpg"]},
        )
        assert resp.status_code == 200
        assert resp.get_json() == {"image_urls": ["https://cloudinary.com/rev1.jpg", "https://cloudinary.com/rev2.jpg"]}


def test_review_images_upload_missing_param(client):
    mock_db = _mock_auth_user(user_id="user-123", role="student")
    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.orders.get_db", return_value=mock_db):
        resp = client.post(
            "/api/orders/order-123/review/images",
            headers={"Authorization": "Bearer user-token"},
            json={},
        )
        assert resp.status_code == 400
        assert "image_urls is required" in resp.get_json()["error"]


# 8. STOREFRONT SECTIONS
def test_storefront_section_image_upload_success(client):
    mock_db = _mock_auth_user(role="admin")
    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.storefront.get_db", return_value=mock_db):
        resp = client.post(
            "/api/storefront/sections/sec-123/image",
            headers={"Authorization": "Bearer admin-token"},
            json={"image_url": "https://cloudinary.com/sec.jpg"},
        )
        assert resp.status_code == 200
        assert resp.get_json() == {"image_url": "https://cloudinary.com/sec.jpg"}


def test_storefront_section_image_upload_missing_param(client):
    mock_db = _mock_auth_user(role="admin")
    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.storefront.get_db", return_value=mock_db):
        resp = client.post(
            "/api/storefront/sections/sec-123/image",
            headers={"Authorization": "Bearer admin-token"},
            json={},
        )
        assert resp.status_code == 400
        assert "image_url is required" in resp.get_json()["error"]


# 9. EARLY SUPPORTER PHOTOS
def test_early_supporter_photo_upload_success(client):
    mock_db = _mock_auth_user(role="admin")
    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.storefront.get_db", return_value=mock_db):
        resp = client.post(
            "/api/storefront/early-supporters/sec-123/photo",
            headers={"Authorization": "Bearer admin-token"},
            json={"photo_url": "https://cloudinary.com/supporter.jpg"},
        )
        assert resp.status_code == 200
        assert resp.get_json() == {"photo_url": "https://cloudinary.com/supporter.jpg"}


def test_early_supporter_photo_upload_missing_param(client):
    mock_db = _mock_auth_user(role="admin")
    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.storefront.get_db", return_value=mock_db):
        resp = client.post(
            "/api/storefront/early-supporters/sec-123/photo",
            headers={"Authorization": "Bearer admin-token"},
            json={},
        )
        assert resp.status_code == 400
        assert "photo_url is required" in resp.get_json()["error"]
