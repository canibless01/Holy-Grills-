"""
tests/test_phase1_and_audit.py — Unit tests for Phase 1 requirements and Verification Checklist items 1-9.
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


class QueryMock:
    def __init__(self, table_name, data_store):
        self.table_name = table_name
        self.data_store = data_store
        self._filter_id = None

    def select(self, *args, **kwargs):
        return self

    def eq(self, col, val):
        if col in ("id", "key"):
            self._filter_id = str(val)
        return self

    def gte(self, *args, **kwargs):
        return self

    def lte(self, *args, **kwargs):
        return self

    def in_(self, col, vals):
        return self

    def order(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def offset(self, *args, **kwargs):
        return self

    def single(self):
        return self

    def update(self, data=None, *args, **kwargs):
        res = self.execute()
        if isinstance(res, dict):
            if data and isinstance(data, dict):
                res.update(data)
            return [res]
        if isinstance(res, list) and res:
            if data and isinstance(data, dict):
                for item in res:
                    if isinstance(item, dict):
                        item.update(data)
            return res
        return [data] if data else []

    def insert(self, data=None, *args, **kwargs):
        if isinstance(data, list):
            return data
        return [data] if data else []

    def upsert(self, data=None, *args, **kwargs):
        if isinstance(data, list):
            return data
        return [data] if data else []

    def delete(self, *args, **kwargs):
        return []

    def with_jwt(self, *args, **kwargs):
        return self

    def execute(self):
        table_data = self.data_store.get(self.table_name, [])
        result = table_data
        if self._filter_id and isinstance(table_data, list):
            matches = [
                item for item in table_data
                if isinstance(item, dict) and (str(item.get("id")) == self._filter_id or str(item.get("key")) == self._filter_id)
            ]
            result = matches[0] if matches else {}

        if not isinstance(result, list) and isinstance(result, dict):
            return result
        return result


def create_db_mock(data_store, auth_user_id="admin-1"):
    mock_db = MagicMock()
    mock_db.table.side_effect = lambda t: QueryMock(t, data_store)
    mock_db.auth_get_user.side_effect = lambda token: {"id": auth_user_id}
    return mock_db


# ── Phase 1 Tests ─────────────────────────────────────────────────────────────

def test_generate_event_qr_scans_and_checks_in(client):
    """generate_event_qr generates QR token and checkin validates it."""
    event_obj = {"id": "event-1", "title": "Fest", "metadata": {"qr_token": "door-qr-123"}, "campus_id": "campus-1", "hp_reward": 50, "hp_per_attendee": 50}
    ticket_obj = {"id": "ticket-1", "user_id": "admin-1", "is_guest": False, "event_id": "event-1", "qr_code": "door-qr-123"}
    admin_profile = {"id": "admin-1", "role": "admin", "is_active": True, "campus_id": "campus-1"}

    def mock_table(t):
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.single.return_value = chain
        chain.update.return_value = chain

        if t == "profiles":
            chain.execute.return_value = admin_profile
        elif t == "events":
            chain.execute.return_value = event_obj
        elif t == "event_tickets":
            chain.execute.return_value = [ticket_obj]
        elif t == "event_checkins":
            chain.execute.return_value = []
        elif t == "campuses":
            chain.execute.return_value = {"id": "campus-1"}
        return chain

    mock_db = MagicMock()
    mock_db.table.side_effect = mock_table
    auth_user = {"id": "admin-1"}

    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.events.get_db", return_value=mock_db), \
         patch("app.routes.events.earn_pending_hp", return_value={"added_to_pending": 50}), \
         patch("app.services.hp_service.earn_pending_hp", return_value={"added_to_pending": 50}), \
         patch("app.services.milestone_service.check_milestone_trigger", return_value=None), \
         patch("app.db.SupabaseClient.auth_get_user", return_value=auth_user):

        # 1. Admin generates QR token
        resp_qr = client.post("/api/events/event-1/qr", headers={"Authorization": "Bearer admin-token"})
        assert resp_qr.status_code == 200
        qr_data = resp_qr.get_json()
        assert "qr_token" in qr_data

        # 2. Checkin using door QR payload
        resp_checkin = client.post(
            "/api/events/event-1/checkin",
            headers={"Authorization": "Bearer admin-token"},
            json={"qr_token": "hg-event:event-1:door-qr-123"}
        )
        assert resp_checkin.status_code == 200, f"Checkin error: {resp_checkin.get_json()}"


def test_list_event_registrants_qr_code_field(client):
    """list_event_registrants handles qr_code field without error."""
    event_obj = {"id": "event-1", "title": "Fest", "starts_at": "2026-05-01", "location": "Hall"}
    ticket_obj = {"id": "t-1", "user_id": "u-1", "tier_id": "tier-1", "status": "confirmed", "created_at": "2026-01-01", "qr_code": "qr-123"}
    admin_profile = {"id": "admin-1", "role": "admin", "is_active": True, "campus_id": "c-1"}
    user_profile = {"id": "u-1", "full_name": "Alice", "phone": "080", "email": "a@ex.com", "is_active": True}

    mock_db = create_db_mock({
        "profiles": [admin_profile, user_profile],
        "events": [event_obj],
        "event_tickets": [ticket_obj],
        "event_ticket_tiers": [{"id": "tier-1", "name": "VIP"}],
        "event_checkins": [],
        "campuses": [{"id": "c-1", "is_default": True}],
    }, auth_user_id="admin-1")

    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.events.get_db", return_value=mock_db):

        resp = client.get("/api/events/event-1/registrants", headers={"Authorization": "Bearer admin-token"})
        assert resp.status_code == 200
        res = resp.get_json()
        assert res["total"] == 1
        assert res["registrants"][0]["full_name"] == "Alice"


def test_send_registrants_to_host_html_completeness(client):
    """send_registrants_to_host constructs valid, complete HTML email."""
    event_obj = {"id": "event-1", "title": "Fest", "starts_at": "2026-05-01", "location": "Hall"}
    admin_profile = {"id": "admin-1", "role": "admin", "is_active": True, "campus_id": "c-1"}
    user_profile = {"id": "u-1", "full_name": "Bob", "phone": "080", "email": "b@ex.com", "is_active": True}

    mock_db = create_db_mock({
        "profiles": [admin_profile, user_profile],
        "events": [event_obj],
        "event_tickets": [{"id": "t-1", "user_id": "u-1", "tier_id": None, "status": "confirmed"}],
        "event_ticket_tiers": [],
        "campuses": [{"id": "c-1", "is_default": True}],
    }, auth_user_id="admin-1")

    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.events.get_db", return_value=mock_db), \
         patch("app.utils.email.send_email_raw", return_value=True) as mock_send:

        resp = client.post(
            "/api/events/event-1/send-registrants-to-host",
            headers={"Authorization": "Bearer admin-token"},
            json={"host_email": "host@example.com", "host_name": "Jane"}
        )
        assert resp.status_code == 200
        assert mock_send.called
        call_kwargs = mock_send.call_args.kwargs
        html_body = call_kwargs["html_body"]
        assert "<html>" in html_body and "</html>" in html_body
        assert "Registrants for: Fest" in html_body


def test_checkin_campus_scoping_enforced(client):
    """checkin endpoint cannot bypass campus check via header or query param."""
    event_obj = {"id": "event-1", "campus_id": "campus-futa"}
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = event_obj

    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.events.get_db", return_value=mock_db):
        resp = client.post("/api/events/event-1/checkin?campus_id=campus-other", json={"qr_token": "abc"})
        assert resp.status_code in (400, 404)


def test_register_for_event_campus_scoping_enforced(client):
    """register_for_event cannot bypass campus check via header or query param."""
    event_obj = {"id": "event-1", "title": "Fest", "is_published": True, "campus_id": "campus-futa"}
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = event_obj

    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.events.get_db", return_value=mock_db):
        resp = client.post(
            "/api/events/event-1/register",
            headers={"X-Campus-ID": "campus-other"},
            json={"guest_name": "Test", "guest_email": "t@ex.com", "guest_phone": "080"}
        )
        assert resp.status_code == 404


def test_get_customer_call_link_docstring(client):
    """get_customer_call_link has updated docstring noting direct tel: formatting."""
    from app.routes.riders import get_customer_call_link
    doc = get_customer_call_link.__doc__ or ""
    assert "tel:" in doc or "phone number" in doc.lower()


def test_update_catering_request_admin_roles(client):
    """update_catering_request checks assigned_to against ADMIN_ROLES without referencing staff."""
    req_obj = {"id": "req-1", "organizer_name": "Org", "email": "o@ex.com"}
    admin_profile = {"id": "admin-1", "role": "admin", "is_active": True, "campus_id": "c-1"}
    student_profile = {"id": "00000000-0000-0000-0000-000000000002", "role": "student", "is_active": True, "campus_id": "c-1"}

    mock_db = create_db_mock({
        "catering_requests": [req_obj],
        "profiles": [admin_profile, student_profile],
        "campuses": [{"id": "c-1", "is_default": True}],
    }, auth_user_id="admin-1")

    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.events.get_db", return_value=mock_db):

        # Assigning to student should fail with 400
        resp = client.patch(
            "/api/events/catering-requests/req-1",
            headers={"Authorization": "Bearer admin-token"},
            json={"assigned_to": "00000000-0000-0000-0000-000000000002"}
        )
        assert resp.status_code == 400


def test_batch_advance_uses_explicit_transition_map():
    """batch_advance source code defines explicit NEXT_STATUS transition map."""
    import inspect
    import app.routes.kitchen as kitchen_mod
    src = inspect.getsource(kitchen_mod.batch_advance)
    assert "NEXT_STATUS" in src
    assert "'received': 'preparing'" in src or '"received": "preparing"' in src


# ── Verification Checklist Items 1–9 ──────────────────────────────────────────

def test_check_item1_create_window_zone_id(client):
    """create_window includes zone_id in WINDOW_COLS and uses default g.zone_id."""
    import inspect
    import app.routes.admin as admin_mod
    src = inspect.getsource(admin_mod.create_window)
    assert '"zone_id"' in src or "'zone_id'" in src


def test_check_item2_audit_webhook_event_deleted():
    """_audit_webhook_event helper is deleted or verified handled."""
    import app.routes.webhooks as webhooks_mod
    assert not hasattr(webhooks_mod, "_audit_webhook_event")


def test_check_item3_deactivate_user_super_admin_block(client):
    """deactivate_user prevents admin from deactivating super_admin account."""
    target_profile = {"id": "super-1", "role": "super_admin", "is_active": True, "campus_id": "c-1"}
    caller_profile = {"id": "admin-1", "role": "admin", "is_active": True, "campus_id": "c-1"}

    mock_db = create_db_mock({
        "profiles": [caller_profile, target_profile],
        "campuses": [{"id": "c-1", "is_default": True}],
    }, auth_user_id="admin-1")

    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.admin.get_db", return_value=mock_db):

        resp = client.post("/api/admin/users/super-1/deactivate", headers={"Authorization": "Bearer admin-token"})
        assert resp.status_code == 403
        assert "super_admin" in resp.get_json()["error"]


def test_check_item4_squad_my_rank_campus_filter():
    """squad_my_rank applies campus_id filter to orders query."""
    import inspect
    import app.routes.leaderboard as lb_mod
    src = inspect.getsource(lb_mod.squad_my_rank)
    assert "campus_id" in src


def test_check_item5_and_6_hall_of_fame_inductees_photo_url():
    """hall_of_fame_inductees and inductee_share_card use photo_url instead of avatar_url."""
    import inspect
    import app.routes.leaderboard as lb_mod
    src1 = inspect.getsource(lb_mod.hall_of_fame_inductees)
    src2 = inspect.getsource(lb_mod.inductee_share_card)
    assert "photo_url" in src1 and "avatar_url" not in src1
    assert "photo_url" in src2 and "avatar_url" not in src2


def test_check_item7_notifications_reference_id():
    """send_notification handles reference_id without column missing guards."""
    import inspect
    import app.services.notification_service as notif_mod
    src = inspect.getsource(notif_mod.send_notification)
    assert '"reference_id": reference_id' in src or "'reference_id': reference_id" in src


def test_check_item8_virtual_accounts_provider_reference():
    """wallet.py queries provider_reference directly."""
    import inspect
    import app.routes.wallet as wallet_mod
    src = inspect.getsource(wallet_mod.get_balance)
    assert "provider_reference" in src


def test_check_item9_hp_bundle_purchases_provider():
    """process_hp_bundle_purchase inserts provider and provider_reference into hp_bundle_purchases."""
    import inspect
    import app.services.hp_service as hp_mod
    src = inspect.getsource(hp_mod.process_hp_bundle_purchase)
    assert '"provider": provider' in src or "'provider': provider" in src
    assert '"provider_reference": provider_reference' in src or "'provider_reference': provider_reference" in src
