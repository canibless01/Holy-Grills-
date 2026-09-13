"""
Tests for Stage 1 + 2: Nickname & Squad fixes.
"""
import pytest
from unittest.mock import MagicMock, patch
from app import create_app
from app.services.squad_service import (
    resolve_display_name,
    resolve_leaderboard_name,
    resolve_display_names_batch,
    resolve_leaderboard_names_batch,
    distribute_squad_hp,
)


def test_resolve_display_name_nickname_first():
    profile = {
        "id": "u1",
        "nickname": "Speedy",
        "full_name": "John Doe",
        "email": "john@example.com",
        "department": "Computer Science",
        "campus_id": "c1",
    }
    with patch("app.services.squad_service.get_db") as mock_get_db:
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.table.return_value.select.return_value.eq.return_value.neq.return_value.eq.return_value.limit.return_value.execute.return_value = []
        name = resolve_display_name(profile=profile)
        assert name == "Speedy"


def test_resolve_display_name_nickname_dedup():
    profile = {
        "id": "u1",
        "nickname": "Speedy",
        "full_name": "John Doe",
        "email": "john@example.com",
        "department": "Computer Science",
        "campus_id": "c1",
    }
    with patch("app.services.squad_service.get_db") as mock_get_db:
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.table.return_value.select.return_value.eq.return_value.neq.return_value.eq.return_value.limit.return_value.execute.return_value = [{"id": "u2"}]
        name = resolve_display_name(profile=profile)
        assert name == "Speedy (Computer Science)"


def test_resolve_display_name_fallbacks():
    # Full name fallback
    p_full = {"id": "u1", "nickname": "", "full_name": "Jane Smith", "email": "jane@example.com"}
    assert resolve_display_name(profile=p_full) == "Jane Smith"

    # Email prefix fallback
    p_email = {"id": "u2", "nickname": None, "full_name": "   ", "email": "alex_p@example.com"}
    assert resolve_display_name(profile=p_email) == "alex_p"

    # Guest fallback
    assert resolve_display_name(profile={}) == "Guest"
    assert resolve_display_name(profile=None) == "Guest"


def test_resolve_leaderboard_name_opt_in():
    profile_opted_in = {
        "id": "u1",
        "nickname": "Speedy",
        "full_name": "John Doe",
        "email": "john@example.com",
        "leaderboard_show_full_name": True,
    }
    assert resolve_leaderboard_name(profile_opted_in) == "John Doe"

    profile_opted_out = {
        "id": "u1",
        "nickname": "Speedy",
        "full_name": "John Doe",
        "email": "john@example.com",
        "leaderboard_show_full_name": False,
    }
    with patch("app.services.squad_service.get_db") as mock_get_db:
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.table.return_value.select.return_value.eq.return_value.neq.return_value.limit.return_value.execute.return_value = []
        assert resolve_leaderboard_name(profile_opted_out) == "Speedy"


def test_resolve_display_names_batch():
    profiles = [
        {"id": "u1", "nickname": "Flash", "full_name": "A A", "campus_id": "c1", "department": "EE"},
        {"id": "u2", "nickname": "Flash", "full_name": "B B", "campus_id": "c1", "department": "ME"},
        {"id": "u3", "nickname": "Sonic", "full_name": "C C", "campus_id": "c1", "department": "CS"},
        {"id": "u4", "nickname": "", "full_name": "David", "campus_id": "c1", "email": "david@ex.com"},
    ]
    res = resolve_display_names_batch(profiles)
    assert res["u1"] == "Flash (EE)"
    assert res["u2"] == "Flash (ME)"
    assert res["u3"] == "Sonic"
    assert res["u4"] == "David"


def test_distribute_squad_hp():
    order_id = "ord12345"
    organizer_id = "org_1"
    members = [
        {"id": "sm1", "user_id": "org_1", "email": "org@example.com", "is_registered": True},
        {"id": "sm2", "user_id": "u2", "email": "u2@example.com", "is_registered": True},
        {"id": "sm3", "user_id": None, "email": "unregistered@example.com", "is_registered": False},
    ]

    with patch("app.services.squad_service.get_db") as mock_get_db, \
         patch("app.services.hp_service.award_active_hp") as mock_award:
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = members

        distribute_squad_hp(order_id, 300, organizer_id, campus_id="c1")

        # 3 participants (2 registered + 1 unregistered) -> share = 100
        assert mock_award.call_count == 2
        mock_db.table.return_value.insert.assert_called_once_with({
            "email": "unregistered@example.com",
            "order_id": order_id,
            "hp_amount": 100,
            "campus_id": "c1",
            "status": "pending",
        })
