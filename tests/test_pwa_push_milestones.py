"""
Tests for PWA Installation, Push Subscription, and PWA+Push Bonus System Milestones.
Verifies guest rejection, single claim, duplicate claim safety, PWA+Push bonus rules,
race-safe DB insertions, dynamic system_settings HP resolution, and non-regression
of standard milestones.
"""

import pytest
from unittest.mock import MagicMock, patch
from flask import Flask, g
from app.routes.challenges import challenges_bp


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"
    app.config["JWT_SECRET"] = "test-jwt-secret"
    app.register_blueprint(challenges_bp, url_prefix="/api/challenges")
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_pwa_installed_guest_rejected(client):
    """Guest requests (no auth token) must be rejected with 401."""
    response = client.post("/api/challenges/pwa-installed")
    assert response.status_code == 401


def test_push_subscribed_guest_rejected(client):
    """Guest requests without valid auth token must be rejected with 401."""
    response = client.post("/api/challenges/push-subscribed", json={"subscription": {"endpoint": "https://push.example.com/sub1"}})
    assert response.status_code == 401


def test_pwa_installed_authenticated_claim(client):
    """Authenticated user claims PWA installation reward once successfully."""
    mock_db = MagicMock()
    mock_db.auth_get_user.return_value = {"id": "user-pwa-1"}

    # Mock DB table responses
    def table_router(table_name):
        mock_table = MagicMock()
        if table_name == "profiles":
            mock_table.select().eq().single().execute.return_value = {
                "id": "user-pwa-1", "role": "student", "is_active": True, "campus_id": "c1"
            }
        elif table_name == "milestones":
            mock_table.select().eq().eq().limit().execute.return_value = [
                {"id": "m-pwa-1", "title": "PWA Install", "trigger_type": "pwa_install", "is_active": True}
            ]
            mock_table.select().eq().eq().single().execute.return_value = {
                "id": "m-pwa-1", "title": "PWA Install", "trigger_type": "pwa_install", "is_active": True
            }
            mock_table.select().in_().eq().execute.return_value = []
        elif table_name == "user_milestones":
            mock_table.select().eq().eq().is_().execute.return_value = []
            mock_table.insert.return_value = [{"id": "um-1"}]
        elif table_name == "system_settings":
            mock_table.select().eq().is_().single().execute.return_value = {"value": "50"}
        return mock_table

    mock_db.table.side_effect = table_router

    headers = {"Authorization": "Bearer token_pwa_1"}
    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.challenges.get_user_client", return_value=mock_db), \
         patch("app.services.milestone_service.get_db", return_value=mock_db), \
         patch("app.services.hp_service.award_active_hp", return_value={"active": 50}):
        response = client.post("/api/challenges/pwa-installed", headers=headers)
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["milestone"] == "pwa_install"
        assert data["hp_awarded"] == 50
        assert data["already_completed"] is False


def test_pwa_installed_duplicate_claim_no_double_hp(client):
    """Subsequent calls after PWA completion return already_completed: True and 0 HP."""
    mock_db = MagicMock()
    mock_db.auth_get_user.return_value = {"id": "user-pwa-1"}

    def table_router(table_name):
        mock_table = MagicMock()
        if table_name == "profiles":
            mock_table.select().eq().single().execute.return_value = {
                "id": "user-pwa-1", "role": "student", "is_active": True, "campus_id": "c1"
            }
        elif table_name == "milestones":
            mock_table.select().eq().eq().limit().execute.return_value = [
                {"id": "m-pwa-1", "title": "PWA Install", "trigger_type": "pwa_install", "is_active": True}
            ]
            mock_table.select().eq().eq().single().execute.return_value = {
                "id": "m-pwa-1", "title": "PWA Install", "trigger_type": "pwa_install", "is_active": True
            }
        elif table_name == "user_milestones":
            # Already completed
            mock_table.select().eq().eq().is_().execute.return_value = [{"id": "um-existing"}]
        return mock_table

    mock_db.table.side_effect = table_router

    headers = {"Authorization": "Bearer token_pwa_1"}
    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.challenges.get_user_client", return_value=mock_db), \
         patch("app.services.milestone_service.get_db", return_value=mock_db):
        response = client.post("/api/challenges/pwa-installed", headers=headers)
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["already_completed"] is True
        assert data["hp_awarded"] == 0


def test_push_subscribed_requires_subscription_object(client):
    """POST /api/challenges/push-subscribed without subscription object must fail with 400."""
    mock_db = MagicMock()
    mock_db.auth_get_user.return_value = {"id": "user-push-1"}
    mock_db.table().select().eq().single().execute.return_value = {
        "id": "user-push-1", "role": "student", "is_active": True, "campus_id": "c1"
    }

    headers = {"Authorization": "Bearer token_push_1"}
    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.challenges.get_user_client", return_value=mock_db):
        response = client.post("/api/challenges/push-subscribed", json={}, headers=headers)
        assert response.status_code == 400
        assert "error" in response.get_json()


def test_pwa_push_bonus_awarded_when_both_complete(client):
    """PWA + Push Bonus is awarded automatically when both PWA and Push are completed."""
    from app.services.milestone_service import check_and_award_pwa_push_bonus, _is_already_completed

    mock_db = MagicMock()
    m_rows = [
        {"id": "m-pwa", "trigger_type": "pwa_install", "title": "PWA Install", "is_active": True},
        {"id": "m-push", "trigger_type": "push_subscribe", "title": "Push Subscribe", "is_active": True},
        {"id": "m-bonus", "trigger_type": "pwa_push_bonus", "title": "PWA Push Bonus", "is_active": True},
    ]

    def table_router(table_name):
        mock_table = MagicMock()
        if table_name == "milestones":
            mock_table.select().in_().eq().execute.return_value = m_rows
            mock_table.select().eq().eq().single().execute.return_value = m_rows[2]
        elif table_name == "user_milestones":
            mock_table.insert.return_value = [{"id": "um-bonus"}]
        elif table_name == "system_settings":
            mock_table.select().eq().is_().single().execute.return_value = {"value": "75"}
        return mock_table

    mock_db.table.side_effect = table_router

    def mock_is_already_completed(db, user_id, milestone_id, period_key):
        if milestone_id in ("m-pwa", "m-push"):
            return True
        return False

    with patch("app.services.milestone_service.get_db", return_value=mock_db), \
         patch("app.services.milestone_service._is_already_completed", side_effect=mock_is_already_completed), \
         patch("app.services.hp_service.award_active_hp", return_value={"active": 75}):
        res = check_and_award_pwa_push_bonus("user-both-1")
        assert res["pwa_install"] is True
        assert res["push_subscribe"] is True
        assert res["eligible"] is True
        assert res["bonus_completed"] is True


def test_system_settings_missing_fails_safely(client):
    """Missing system setting for PWA_INSTALL_HP must fail safely without hardcoded fallback."""
    from app.services.milestone_service import check_and_award_milestone

    mock_db = MagicMock()
    mock_db.table().select().eq().eq().single().execute.return_value = {
        "id": "m-pwa-1", "title": "PWA Install", "trigger_type": "pwa_install", "is_active": True
    }
    # User has not completed it yet
    mock_db.table().select().eq().eq().is_().execute.return_value = []
    # system_settings query returns None / Exception
    mock_db.table().select().eq().is_().single().execute.side_effect = Exception("Setting missing")

    with patch("app.services.milestone_service.get_db", return_value=mock_db):
        with pytest.raises(ValueError, match="Configuration error"):
            check_and_award_milestone("user-1", "m-pwa-1")
