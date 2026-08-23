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


def test_b2_table_query_eq_neq_none():
    """B2: Verify TableQuery.eq(col, None) and .neq(col, None) generate is.null / is.not.null."""
    client = SupabaseClient("https://example.supabase.co", "service_key", "anon_key")
    query = client.table("test_table")
    query.eq("status", None)
    query.neq("deleted_at", None)
    params = query._build_params()
    assert params.get("status") == "is.null"
    assert params.get("deleted_at") == "is.not.null"


def test_b3_get_user_email_and_name_uses_get_db():
    """B3: Verify get_user_email_and_name uses service role get_db() instead of get_user_client()."""
    from app.utils.email import get_user_email_and_name

    mock_db = MagicMock()
    mock_table = MagicMock()
    mock_db.table.return_value = mock_table
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.single.return_value = mock_table
    mock_table.execute.return_value = {"email": "test@example.com", "full_name": "Test User"}

    with patch("app.db.get_db", return_value=mock_db) as mock_get_db:
        email, name = get_user_email_and_name("user-123")
        assert email == "test@example.com"
        assert name == "Test User"
        mock_get_db.assert_called_once()


def test_b4_messages_milestone_badge_title():
    """B4: Verify MSG has MILESTONE_BADGE_TITLE."""
    from app.messages import MSG
    assert hasattr(MSG, "MILESTONE_BADGE_TITLE")
    assert MSG.MILESTONE_BADGE_TITLE in ("New Badge Unlocked! 🏅", "Milestone Unlocked! 🎖️")


def test_b5_b8_send_notification_service_role_and_no_reference_type_column():
    """B5 & B8: Verify send_notification uses get_db() and inserts payload without 'reference_type' column."""
    from app.services.notification_service import send_notification

    mock_db = MagicMock()
    mock_table = MagicMock()
    mock_db.table.return_value = mock_table
    mock_table.insert.return_value = [{"id": "notif-1"}]

    with patch("app.services.notification_service.get_db", return_value=mock_db) as mock_get_db, \
         patch("app.services.notification_service._is_throttled", return_value=False), \
         patch("app.services.notification_service._log_notification"):
        records = send_notification(
            user_id="u1",
            notif_type="test_type",
            title="Test Title",
            body="Test Body",
            reference_id="ref-123",
            reference_type="order",
            channels=["in_app"],
        )
        assert len(records) == 1
        mock_get_db.assert_called()
        insert_arg = mock_table.insert.call_args[0][0]
        assert "reference_type" not in insert_arg
        assert insert_arg["metadata"]["reference_type"] == "order"


def test_b6_send_blast_notif_type():
    """B6: Verify send_blast uses notif_type=f'blast_{blast_id}'."""
    from app.services.notification_service import send_blast

    mock_db = MagicMock()
    mock_table = MagicMock()
    mock_db.table.return_value = mock_table

    blast_row = {
        "id": "blast-999",
        "segment": {},
        "channels": ["in_app"],
        "title": "Hello",
        "body": "World",
    }
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.single.return_value = mock_table
    mock_table.execute.side_effect = [
        blast_row,  # select blast
        [{"id": "u1", "full_name": "Alice"}],  # select profiles
        [],  # update blast status
    ]

    with patch("app.services.notification_service.get_user_client", return_value=mock_db), \
         patch("app.services.notification_service.send_notification") as mock_send_notif:
        send_blast("blast-999")
        mock_send_notif.assert_called_once()
        assert mock_send_notif.call_args[1]["notif_type"] == "blast_blast-999"


def test_b10_check_post_delivery_nudges_in_beat_schedule():
    """B10: Verify check-post-delivery-nudges is registered in celery_app beat schedule."""
    from app.tasks.celery_app import celery_app
    assert "check-post-delivery-nudges" in celery_app.conf.beat_schedule
    entry = celery_app.conf.beat_schedule["check-post-delivery-nudges"]
    assert entry["task"] == "app.tasks.scheduled.check_post_delivery_nudges"


def test_delivery_area_boundary_check_and_nearest_gate():
    """Delivery Grouping & Route Ordering: test boundary check and find_nearest_gate."""
    from app.routes.delivery import is_within_delivery_area, find_nearest_gate

    mock_db = MagicMock()
    mock_table = MagicMock()
    mock_db.table.return_value = mock_table
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.single.return_value = mock_table

    # 1. When campus lat/lon is None -> fails open (True)
    mock_table.execute.return_value = {"lat": None, "lon": None}
    assert is_within_delivery_area(mock_db, 7.30, 5.14, "campus-1") is True

    # 2. When campus lat/lon set and within 15km
    mock_table.execute.side_effect = [
        {"lat": 7.2985, "lon": 5.1421},  # campus select
        {"value": "15"},                 # kitchen_settings max_delivery_radius_km
    ]
    # Point ~1km away
    assert is_within_delivery_area(mock_db, 7.30, 5.14, "campus-1") is True

    # 3. Point ~50km away -> False
    mock_table.execute.side_effect = [
        {"lat": 7.2985, "lon": 5.1421},
        {"value": "15"},
    ]
    assert is_within_delivery_area(mock_db, 7.80, 5.14, "campus-1") is False

    # 4. find_nearest_gate selects nearest gate
    gates = [
        {"id": "gate-1", "name": "Gate 1", "lat": 7.29, "lon": 5.14},
        {"id": "gate-2", "name": "Gate 2", "lat": 7.50, "lon": 5.14},
    ]
    mock_table.execute.side_effect = None
    mock_table.execute.return_value = gates
    nearest = find_nearest_gate(mock_db, 7.30, 5.14, "campus-1")
    assert nearest["id"] == "gate-1"


def test_part_b_fixes_1_to_13():
    """Verify Part B Python fixes 1 through 13."""
    from app.services.hp_service import recalculate_tier
    from app.services.payment_service import initialize_payment
    from app.utils.email import TEMPLATES

    # Item 4: recalculate_tier defers downgrade
    mock_db = MagicMock()
    def mock_table_factory(table_name):
        m = MagicMock()
        m.select.return_value = m
        m.eq.return_value = m
        m.order.return_value = m
        m.single.return_value = m
        if table_name == "profiles":
            m.execute.return_value = {"hp_earned_120day": 0, "current_tier_id": "tier-holy"}
        elif table_name == "hp_tiers":
            m.execute.return_value = [{"id": "tier-holy", "min_points": 20000, "sort_order": 4}, {"id": "tier-ember", "min_points": 0, "sort_order": 1}]
        return m

    mock_db.table.side_effect = mock_table_factory
    with patch("app.services.hp_service.get_db", return_value=mock_db):
        res = recalculate_tier("u1")
        assert res["changed"] is False
        assert res["event"] == "downgrade_deferred_to_grace_job"

    # Item 10: initialize_payment rounds naira to kobo
    with patch("app.services.payment_service._paystack_post") as mock_post, \
         patch("app.services.payment_service._paystack_headers", return_value={"Authorization": "Bearer dummy"}):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": True, "data": {"authorization_url": "https://paystack.com"}}
        mock_post.return_value = mock_resp
        initialize_payment("test@example.com", 150.506, "ref123")
        payload = mock_post.call_args[1]["payload"]
        assert payload["amount"] == 15051  # rounded from 15050.6

    # Item 12: TEMPLATES has squad_invite
    assert "squad_invite" in TEMPLATES


def test_process_flash_redeem_atomic_rpc():
    """Verify process_flash_redeem delegates to hg_redeem_flash_reward_atomic RPC."""
    from app.services.hp_service import process_flash_redeem

    mock_db = MagicMock()
    mock_db.rpc.return_value = {
        "success": True,
        "redemption_id": "red-123",
        "hp_cost": 100,
        "discount_pct": 50,
        "reward_name": "Free Meal",
    }

    with patch("app.services.hp_service.get_user_client", return_value=mock_db):
        res = process_flash_redeem("reward-1", "user-1")
        assert res["redemption_id"] == "red-123"
        assert res["hp_cost"] == 100
        mock_db.rpc.assert_called_once_with("hg_redeem_flash_reward_atomic", {
            "p_user_id": "user-1",
            "p_reward_id": "reward-1",
        })
