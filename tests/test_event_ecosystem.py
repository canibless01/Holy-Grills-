"""
tests/test_event_ecosystem.py — Unit tests for Event Ecosystem Upgrade & Campus Awareness.
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


def _mock_db():
    mock_db = MagicMock()
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.gte.return_value = chain
    chain.order.return_value = chain
    chain.in_.return_value = chain
    chain.limit.return_value = chain
    chain.single.return_value = chain
    chain.insert.return_value = [{"id": "ticket-123"}]
    chain.update.return_value = [{"id": "tier-123"}]
    chain.execute.return_value = []
    mock_db.table.return_value = chain
    return mock_db


# 1. Guest Registration Validation
def test_guest_registration_missing_fields(client):
    mock_db = _mock_db()
    event_obj = {"id": "event-1", "title": "Tech Fest", "is_published": True, "campus_id": "campus-1"}

    event_chain = MagicMock()
    event_chain.select.return_value = event_chain
    event_chain.eq.return_value = event_chain
    event_chain.single.return_value = event_chain
    event_chain.execute.return_value = event_obj

    mock_db.table.side_effect = lambda t: event_chain if t == "events" else _mock_db().table(t)

    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.events.get_db", return_value=mock_db):
        resp = client.post("/api/events/event-1/register", json={"guest_name": "John"})
        assert resp.status_code == 400
        assert "Email is required" in resp.get_json()["error"]


def test_guest_registration_custom_field_required(client):
    mock_db = _mock_db()
    event_obj = {
        "id": "event-1",
        "title": "Tech Fest",
        "is_published": True,
        "campus_id": "campus-1",
        "registration_fields": [
            {"name": "tshirt_size", "label": "T-Shirt Size", "type": "select", "required": True, "options": ["S", "M", "L"]}
        ]
    }

    event_chain = MagicMock()
    event_chain.select.return_value = event_chain
    event_chain.eq.return_value = event_chain
    event_chain.single.return_value = event_chain
    event_chain.execute.return_value = event_obj

    mock_db.table.side_effect = lambda t: event_chain if t == "events" else _mock_db().table(t)

    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.events.get_db", return_value=mock_db):
        resp = client.post(
            "/api/events/event-1/register",
            json={
                "guest_name": "John Doe",
                "guest_email": "john@example.com",
                "guest_phone": "08012345678",
                "answers": {}
            }
        )
        assert resp.status_code == 400
        assert "T-Shirt Size is required" in resp.get_json()["error"]


def test_guest_registration_success(client):
    mock_db = _mock_db()
    event_obj = {
        "id": "event-1",
        "title": "Tech Fest",
        "is_published": True,
        "campus_id": "campus-1",
        "starts_at": "2026-05-01T10:00:00Z",
        "location": "Main Hall",
        "registration_fields": []
    }

    def table_mock(t):
        if t == "events":
            c = MagicMock()
            c.select.return_value = c
            c.eq.return_value = c
            c.single.return_value = c
            c.execute.return_value = event_obj
            return c
        if t == "profiles":
            c = MagicMock()
            c.select.return_value = c
            c.eq.return_value = c
            c.execute.return_value = []
            return c
        if t == "event_tickets":
            c = MagicMock()
            c.select.return_value = c
            c.eq.return_value = c
            c.execute.return_value = []
            c.insert.return_value = [{"id": "t-999"}]
            return c
        return _mock_db().table(t)

    mock_db.table.side_effect = table_mock

    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.events.get_db", return_value=mock_db), \
         patch("app.routes.events.send_qr_ticket_email", return_value=True) as mock_email:
        resp = client.post(
            "/api/events/event-1/register",
            json={
                "guest_name": "Guest User",
                "guest_email": "guest@example.com",
                "guest_phone": "08099998888",
            }
        )
        assert resp.status_code == 201
        res_json = resp.get_json()
        assert res_json["is_guest"] is True
        assert res_json["ticket_id"] == "t-999"
        assert "prompt_create_account" in res_json
        assert mock_email.called


# 2. Tier Comparison & Detail
def test_tier_comparison_endpoint(client):
    mock_db = _mock_db()
    event_obj = {"id": "event-1", "title": "Tech Fest", "campus_id": "campus-1"}
    tiers_data = [
        {"id": "tier-1", "name": "VIP", "price_naira": 5000, "capacity": 10, "sold_count": 2, "features": ["Front Row", "Free Drink"], "terms": ["No refunds"], "color": "#FF0000", "icon": "⭐", "is_early_bird": False},
        {"id": "tier-2", "name": "Regular", "price_naira": 2000, "capacity": 50, "sold_count": 50, "features": ["General Admission"], "terms": [], "color": "#00FF00", "icon": "🎟️", "is_early_bird": True, "early_bird_deadline": "2026-04-01T00:00:00Z"},
    ]

    def table_mock(t):
        c = MagicMock()
        c.select.return_value = c
        c.eq.return_value = c
        c.order.return_value = c
        c.single.return_value = c
        if t == "events":
            c.execute.return_value = event_obj
        elif t == "event_ticket_tiers":
            c.execute.return_value = tiers_data
        return c

    mock_db.table.side_effect = table_mock

    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.events.get_db", return_value=mock_db):
        resp = client.get("/api/events/event-1/tiers/comparison")
        assert resp.status_code == 200
        res = resp.get_json()
        assert len(res["tiers"]) == 2
        assert res["tiers"][0]["available"] == 8
        assert res["tiers"][0]["is_sold_out"] is False
        assert res["tiers"][1]["available"] == 0
        assert res["tiers"][1]["is_sold_out"] is True


def test_tier_detail_endpoint(client):
    mock_db = _mock_db()
    event_data = {"id": "event-1", "title": "Tech Fest", "campus_id": "campus-1"}
    tier_data = {"id": "tier-1", "event_id": "event-1", "name": "VIP", "capacity": 20, "sold_count": 5, "features": ["VIP Pass"], "events": event_data}

    def table_mock(t):
        c = MagicMock()
        c.select.return_value = c
        c.eq.return_value = c
        c.single.return_value = c
        if t == "event_ticket_tiers":
            c.execute.return_value = tier_data
        elif t == "events":
            c.execute.return_value = event_data
        return c

    mock_db.table.side_effect = table_mock

    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.events.get_db", return_value=mock_db):
        resp = client.get("/api/events/tiers/tier-1/detail")
        assert resp.status_code == 200
        res = resp.get_json()
        assert res["id"] == "tier-1"
        assert res["available"] == 15
        assert res["event"]["title"] == "Tech Fest"


# 3. Campus Awareness Tests
def test_campus_filtering_list_events_guest(client):
    mock_db = _mock_db()

    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.events.get_db", return_value=mock_db):
        resp = client.get("/api/events?campus_id=campus-futa")
        assert resp.status_code == 200

        resp_header = client.get("/api/events", headers={"X-Campus-ID": "campus-futa"})
        assert resp_header.status_code == 200


def test_campus_filtering_mismatch_event_404(client):
    mock_db = _mock_db()
    event_obj = {"id": "event-1", "title": "Tech Fest", "is_published": True, "campus_id": "campus-futa"}

    event_chain = MagicMock()
    event_chain.select.return_value = event_chain
    event_chain.eq.return_value = event_chain
    event_chain.single.return_value = event_chain
    event_chain.execute.return_value = event_obj

    mock_db.table.side_effect = lambda t: event_chain if t == "events" else _mock_db().table(t)

    with patch("app.middleware.auth.get_db", return_value=mock_db), \
         patch("app.routes.events.get_db", return_value=mock_db):
        # Mismatched campus query param
        resp = client.get("/api/events/event-1?campus_id=campus-other")
        assert resp.status_code == 404

        # Mismatched campus header on guest registration
        resp_reg = client.post(
            "/api/events/event-1/register",
            headers={"X-Campus-ID": "campus-other"},
            json={"guest_name": "Test", "guest_email": "t@ex.com", "guest_phone": "080"}
        )
        assert resp_reg.status_code == 404
