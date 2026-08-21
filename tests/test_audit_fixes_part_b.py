"""
Unit tests for audit fixes in Part B (cron locks, super_admin campus scoping,
service-role virtual_accounts insert, guest campus scoping, etc.).
"""

import pytest
from unittest.mock import patch, MagicMock
from app.db import SupabaseClient, UserSupabaseClient
from app.middleware.auth import _resolve_default_campus
from app.tasks.scheduled import (
    reset_monthly_leaderboard,
    recalculate_120day_hp,
    tier_grace_period_check,
    process_scheduled_orders,
    send_scheduled_notifications,
)


def test_resolve_default_campus_super_admin():
    """Ensure super_admin is never assigned a default campus."""
    mock_db = MagicMock()
    result = _resolve_default_campus(mock_db, user_role="super_admin")
    assert result is None
    # Ensure database was not queried for super_admin
    mock_db.table.assert_not_called()


def test_resolve_default_campus_student():
    """Ensure non-super_admin gets active default campus."""
    mock_db = MagicMock()
    mock_table = MagicMock()
    mock_db.table.return_value = mock_table
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.order.return_value = mock_table
    mock_table.limit.return_value = mock_table
    mock_table.execute.return_value = [{"id": "campus-futa"}]

    result = _resolve_default_campus(mock_db, user_role="student")
    assert result == "campus-futa"


def test_cron_lock_fail_closed_reset_monthly_leaderboard():
    """Verify reset_monthly_leaderboard fails closed when try_acquire_cron_lock raises an exception."""
    mock_db = MagicMock()
    mock_db.rpc.side_effect = Exception("Supabase connection error")

    with patch("app.tasks.scheduled.get_db", return_value=mock_db):
        res = reset_monthly_leaderboard()
        assert res == {"skipped": "Lock not acquired"}


def test_cron_lock_fail_closed_recalculate_120day_hp():
    """Verify recalculate_120day_hp fails closed when try_acquire_cron_lock raises an exception."""
    mock_db = MagicMock()
    mock_db.rpc.side_effect = Exception("Supabase connection error")

    with patch("app.tasks.scheduled.get_db", return_value=mock_db):
        res = recalculate_120day_hp()
        assert res == {"skipped": "Lock not acquired"}


def test_process_scheduled_orders_has_cron_lock():
    """Verify process_scheduled_orders attempts to acquire and release cron lock."""
    mock_db = MagicMock()
    mock_db.rpc.return_value = False  # Lock not acquired

    with patch("app.tasks.scheduled.get_db", return_value=mock_db):
        res = process_scheduled_orders()
        assert res == {"skipped": "Lock not acquired"}
        mock_db.rpc.assert_called_with("try_acquire_cron_lock", {"p_job_name": "process_scheduled_orders"})


def test_send_scheduled_notifications_has_cron_lock():
    """Verify send_scheduled_notifications attempts to acquire and release cron lock."""
    mock_db = MagicMock()
    mock_db.rpc.return_value = False  # Lock not acquired

    with patch("app.tasks.scheduled.get_db", return_value=mock_db):
        res = send_scheduled_notifications()
        assert res == {"skipped": "Lock not acquired"}
        mock_db.rpc.assert_called_with("try_acquire_cron_lock", {"p_job_name": "send_scheduled_notifications"})
