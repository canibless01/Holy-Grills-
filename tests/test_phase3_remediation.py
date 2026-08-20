"""
Tests for Phase 3 Medium/Low severity remediation fixes.
"""

import pytest
from flask import Flask, jsonify, g
from unittest.mock import MagicMock, patch
from app.services.order_service import create_order_apply_rpc_total
from app.routes.admin_gifts import require_super_admin_for_settings_write
from app.tasks.scheduled import with_cron_logging, _log_cron_execution
from app.db import TableQuery, SupabaseClient
from app.routes.challenges import MILESTONE_ALLOWED_FIELDS
from app.routes.events import my_tickets


def test_create_order_apply_rpc_total():
    rpc_result = {
        "total_amount": 1500.0,
        "order_lock_discount_applied": True,
    }
    total, discount_applied = create_order_apply_rpc_total(rpc_result, 2000.0)
    assert total == 1500.0
    assert discount_applied is True

    # Fallback when keys missing
    total_fb, discount_fb = create_order_apply_rpc_total({}, 2000.0)
    assert total_fb == 2000.0
    assert discount_fb is False


def test_require_super_admin_for_settings_write():
    app = Flask(__name__)
    with app.test_request_context():
        g.user_role = "admin"
        res = require_super_admin_for_settings_write(g, jsonify)
        assert res is not None
        assert res[1] == 403

        g.user_role = "super_admin"
        res2 = require_super_admin_for_settings_write(g, jsonify)
        assert res2 is None


def test_table_query_count_exact():
    client = SupabaseClient("http://dummy", "service_key", "anon_key")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [{"id": "1"}, {"id": "2"}]
    mock_resp.headers = {"Content-Range": "0-1/42"}
    client._session.get = MagicMock(return_value=mock_resp)

    q = TableQuery(client, "profiles").select("id", count="exact")
    res = q.execute()

    assert isinstance(res, dict)
    assert res.get("count") == 42


def test_milestone_allowed_fields_contains_campus_id():
    assert "campus_id" in MILESTONE_ALLOWED_FIELDS


def test_with_cron_logging():
    dummy_db = MagicMock()
    dummy_db.table.return_value.insert.return_value.execute.return_value = []

    @with_cron_logging("test-job")
    def dummy_task():
        return {"status": "ok"}

    with patch("app.tasks.scheduled.get_db", return_value=dummy_db):
        res = dummy_task()
        assert res == {"status": "ok"}
        dummy_db.table.assert_called_with("admin_audit_logs")
        insert_args = dummy_db.table.return_value.insert.call_args[0][0]
        assert insert_args["actor_id"] is None
        assert insert_args["actor_role"] == "system"
        assert insert_args["entity_type"] == "cron_jobs"
        assert insert_args["entity_id"] == "test-job"
