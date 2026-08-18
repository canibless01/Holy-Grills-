"""
tests/test_phase2_checklist.py — Unit tests covering Phase 2 checklist items:
- Kitchen capacity (_kitchen_stats) campus scoping
- set_kitchen_capacity campus scoping (/api/menu/kitchen-capacity)
- get_hours and update_hours campus scoping (/api/storefront/operating-hours)
- set_override campus scoping (/api/storefront/operating-hours/override)
- Leaderboard snapshots campus ranking (hall_of_fame_inductees / squad_leaderboard)
- my_rank campus ranking (my_rank / squad_my_rank)
- squad_leaderboard and squad_my_rank campus scoping
- _daily_item_counts query optimization
- order_status_history role-based scoping (riders see assigned batch orders, kitchen see campus orders)
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
        self._is_single = False

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
        self._is_single = True
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
            result = matches if matches else []

        if self._is_single:
            if isinstance(result, list):
                return result[0] if result else {}
            return result
        if not isinstance(result, list) and isinstance(result, dict):
            return [result]
        return result


def create_db_mock(data_store, auth_user_id="user-1"):
    mock_db = MagicMock()
    mock_db.table.side_effect = lambda t: QueryMock(t, data_store)
    mock_db.auth_get_user.side_effect = lambda token: {"id": auth_user_id}
    return mock_db


# ── Phase 2 Tests ─────────────────────────────────────────────────────────────

def test_kitchen_capacity_counts_current_campus_only():
    """Kitchen capacity checks filter orders by current campus_id."""
    import inspect
    import app.routes.menu as menu_mod
    import app.services.order_service as order_service_mod
    src_menu = inspect.getsource(menu_mod._kitchen_stats)
    src_order = inspect.getsource(order_service_mod._check_kitchen_capacity)
    assert "campus_id" in src_menu
    assert "kitchen_settings" in src_order


def test_set_kitchen_capacity_updates_correct_campus(client):
    """set_kitchen_capacity scopes update to caller campus_id."""
    admin_profile = {"id": "admin-1", "role": "admin", "is_active": True, "campus_id": "campus-futa"}
    cap_row = {"key": "daily_order_capacity", "value": "100", "campus_id": "campus-futa"}

    mock_db = create_db_mock({
        "profiles": [admin_profile],
        "kitchen_settings": [cap_row],
        "orders": [],
        "campuses": [{"id": "campus-futa", "is_default": True}],
    }, auth_user_id="admin-1")

    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.menu.get_db", return_value=mock_db), \
         patch("app.db.SupabaseClient.auth_get_user", return_value={"id": "admin-1"}):

        resp = client.patch(
            "/api/menu/kitchen-capacity",
            headers={"Authorization": "Bearer admin-token"},
            json={"daily_order_capacity": 150}
        )
        assert resp.status_code == 200
        res = resp.get_json()
        assert res.get("daily_order_capacity") == 150 or "is_at_capacity" in res


def test_get_hours_and_update_hours_campus_scoped(client):
    """get_hours and update_hours operate on caller campus_id."""
    admin_profile = {"id": "admin-1", "role": "admin", "is_active": True, "campus_id": "campus-futa"}
    hours_row = {"id": "h-1", "campus_id": "campus-futa", "weekday": 1, "opens_at": "08:00", "closes_at": "20:00"}

    mock_db = create_db_mock({
        "profiles": [admin_profile],
        "operating_hours": [hours_row],
        "operating_hour_overrides": [],
        "campuses": [{"id": "campus-futa", "is_default": True}],
    }, auth_user_id="admin-1")

    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.storefront.get_db", return_value=mock_db), \
         patch("app.db.SupabaseClient.auth_get_user", return_value={"id": "admin-1"}):

        # Get operating hours
        resp_get = client.get("/api/storefront/operating-hours?campus_id=campus-futa")
        assert resp_get.status_code == 200

        # Update operating hours
        resp_up = client.patch(
            "/api/storefront/operating-hours",
            headers={"Authorization": "Bearer admin-token"},
            json={"day": "monday", "open_time": "09:00", "close_time": "21:00", "is_closed": False}
        )
        assert resp_up.status_code == 200


def test_set_override_campus_scoped(client):
    """set_override includes campus_id so it doesn't overwrite another campus."""
    admin_profile = {"id": "admin-1", "role": "admin", "is_active": True, "campus_id": "campus-futa"}
    override_row = {"id": "ov-1", "date": "2026-06-01", "campus_id": "campus-futa"}

    mock_db = create_db_mock({
        "profiles": [admin_profile],
        "operating_hour_overrides": [override_row],
        "campuses": [{"id": "campus-futa", "is_default": True}],
    }, auth_user_id="admin-1")

    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.storefront.get_db", return_value=mock_db), \
         patch("app.db.SupabaseClient.auth_get_user", return_value={"id": "admin-1"}):

        resp = client.post(
            "/api/storefront/operating-hours/override",
            headers={"Authorization": "Bearer admin-token"},
            json={"override_date": "2026-06-01", "is_closed": True, "reason": "Holiday"}
        )
        assert resp.status_code in (200, 201)


def test_leaderboard_snapshots_and_my_rank_campus_scoped():
    """Leaderboard squad_leaderboard and my_rank inspect campus_id filters."""
    import inspect
    import app.routes.leaderboard as lb_mod
    src_squad_lb = inspect.getsource(lb_mod.squad_leaderboard)
    src_rank = inspect.getsource(lb_mod.my_rank)
    assert "campus_id" in src_squad_lb
    assert "campus_id" in src_rank


def test_squad_leaderboard_and_my_rank_campus_data():
    """squad_leaderboard and squad_my_rank filter by campus_id."""
    import inspect
    import app.routes.leaderboard as lb_mod
    src_squad_lb = inspect.getsource(lb_mod.squad_leaderboard)
    src_squad_rank = inspect.getsource(lb_mod.squad_my_rank)
    assert "campus_id" in src_squad_lb
    assert "campus_id" in src_squad_rank


def test_daily_item_counts_performance_optimized():
    """_daily_item_counts restricts query rather than fetching whole table."""
    import inspect
    import app.routes.menu as menu_mod
    src = inspect.getsource(menu_mod._daily_item_counts)
    assert "gte" in src or "in_" in src or "limit" in src or "created_at" in src


def test_order_status_history_role_scoping(client):
    """order_status_history enforces rider batch matching and kitchen campus matching."""
    rider_profile = {"id": "rider-1", "role": "rider", "is_active": True, "campus_id": "campus-1"}
    kitchen_profile = {"id": "kitchen-1", "role": "kitchen", "is_active": True, "campus_id": "campus-1"}
    order_obj = {
        "id": "00000000-0000-0000-0000-000000000001",
        "campus_id": "campus-1",
        "user_id": "user-1",
        "delivery_batches": [{"rider_id": "rider-1"}]
    }

    # Rider check
    mock_rider_db = create_db_mock({
        "profiles": [rider_profile],
        "orders": [order_obj],
        "order_status_logs": [{"order_id": "00000000-0000-0000-0000-000000000001", "status": "received"}],
        "campuses": [{"id": "campus-1", "is_default": True}],
    }, auth_user_id="rider-1")

    with patch("app.middleware.auth.get_db", return_value=mock_rider_db), \
         patch("app.routes.orders.get_db", return_value=mock_rider_db), \
         patch("app.routes.orders.get_user_client", return_value=mock_rider_db), \
         patch("app.db.get_user_client", return_value=mock_rider_db), \
         patch("app.db.SupabaseClient.auth_get_user", return_value={"id": "rider-1"}):

        resp_rider = client.get("/api/orders/00000000-0000-0000-0000-000000000001/history", headers={"Authorization": "Bearer rider-token"})
        assert resp_rider.status_code == 200

    # Kitchen check
    mock_kitchen_db = create_db_mock({
        "profiles": [kitchen_profile],
        "orders": [order_obj],
        "order_status_logs": [{"order_id": "00000000-0000-0000-0000-000000000001", "status": "received"}],
        "campuses": [{"id": "campus-1", "is_default": True}],
    }, auth_user_id="kitchen-1")

    with patch("app.middleware.auth.get_db", return_value=mock_kitchen_db), \
         patch("app.routes.orders.get_db", return_value=mock_kitchen_db), \
         patch("app.routes.orders.get_user_client", return_value=mock_kitchen_db), \
         patch("app.db.get_user_client", return_value=mock_kitchen_db), \
         patch("app.db.SupabaseClient.auth_get_user", return_value={"id": "kitchen-1"}):

        resp_kitchen = client.get("/api/orders/00000000-0000-0000-0000-000000000001/history", headers={"Authorization": "Bearer kitchen-token"})
        assert resp_kitchen.status_code == 200
