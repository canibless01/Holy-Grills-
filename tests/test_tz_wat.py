"""Tests for WAT timezone module, CORS configuration, and login streak refresh trigger."""

from datetime import datetime, timezone, timedelta, date
from unittest.mock import patch
import pytest
from app import create_app
from app.utils.tz import today_wat, WAT_OFFSET


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_today_wat_offset():
    """Verify today_wat() calculates date in WAT (UTC+1)."""
    assert WAT_OFFSET == timedelta(hours=1)
    now_utc = datetime.now(timezone.utc)
    expected_date = (now_utc + timedelta(hours=1)).date()
    assert today_wat() == expected_date


def test_today_wat_boundary():
    """Verify boundary condition where UTC date differs from WAT date at 23:30 UTC."""
    mock_utc_now = datetime(2026, 3, 31, 23, 30, 0, tzinfo=timezone.utc)
    with patch("app.utils.tz.datetime") as mock_datetime:
        mock_datetime.now.return_value = mock_utc_now
        result = today_wat()
        assert result == date(2026, 4, 1)


def test_auth_refresh_triggers_login_streak(client):
    """Verify POST /api/auth/refresh invokes process_login_streak upon success."""
    fake_refresh_response = {
        "access_token": "new_access_token",
        "refresh_token": "new_refresh_token",
        "user": {"id": "user_123_abc"}
    }

    with patch("app.routes.auth.auth_service.refresh_token", return_value=fake_refresh_response), \
         patch("app.routes.auth.streak_service.process_login_streak") as mock_pls:

        res = client.post("/api/auth/refresh", json={"refresh_token": "valid_refresh_token"})
        assert res.status_code == 200
        data = res.get_json()
        assert data["rotated"] is True
        assert data["access_token"] == "new_access_token"
        mock_pls.assert_called_once_with("user_123_abc", None)


def test_cors_options_preflight(client):
    """Verify OPTIONS preflight returns 204 with CORS headers for allowed origin."""
    res = client.options(
        "/api/orders",
        headers={
            "Origin": "https://holy-grill-copy-copy-copy-cop-f435c07e.base44.app",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization, Content-Type"
        }
    )
    assert res.status_code == 204
    assert res.headers.get("Access-Control-Allow-Origin") == "https://holy-grill-copy-copy-copy-cop-f435c07e.base44.app"
