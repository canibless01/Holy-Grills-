"""
Tests for Part 2 — Scheduled Marketing.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta
from app import create_app
from app.tasks.scheduled import send_scheduled_blasts
from app.db import SupabaseClient


@pytest.fixture
def app():
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_create_scheduled_blast_endpoint(client):
    with patch("app.routes.notifications.get_user_client") as mock_get_client, \
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

        # Auth profile
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = {
            "id": "admin1", "role": "admin", "is_active": True, "campus_id": "c1"
        }

        # Blast insert mock
        future_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        inserted_blast = {
            "id": "blast-100",
            "title": "Scheduled Post",
            "body": "This goes out in 2 hours",
            "channels": ["in_app"],
            "scheduled_at": future_time,
            "status": "scheduled",
            "created_by": "admin1",
            "campus_id": "c1",
        }
        mock_db.table.return_value.insert.return_value.execute.return_value = [inserted_blast]

        res = client.post(
            "/api/notifications/blasts",
            headers={"Authorization": "Bearer admintoken"},
            json={
                "title": "Scheduled Post",
                "body": "This goes out in 2 hours",
                "channels": ["in_app"],
                "send_at": future_time,
            },
        )
        assert res.status_code == 201
        data = res.get_json()
        assert data["message"] == "Blast scheduled"
        assert data["blast"]["status"] == "scheduled"


def test_send_scheduled_blasts_task():
    mock_db = MagicMock()
    # Acquire lock returns True
    mock_db.rpc.return_value = True

    past_time = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    scheduled_blasts_rows = [
        {"id": "blast-100", "status": "scheduled", "scheduled_at": past_time}
    ]

    mock_table = MagicMock()
    mock_db.table.return_value = mock_table
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.lte.return_value = mock_table
    mock_table.execute.return_value = scheduled_blasts_rows

    with patch("app.tasks.scheduled.get_db", return_value=mock_db), \
         patch("app.services.notification_service.send_blast") as mock_send_blast:

        res = send_scheduled_blasts()
        assert res["processed"] == 1
        mock_send_blast.assert_called_once_with("blast-100")
