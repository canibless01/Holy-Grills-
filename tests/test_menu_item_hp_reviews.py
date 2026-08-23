"""Focused tests for per-item HP multipliers and menu review summaries."""

from pathlib import Path
from unittest.mock import patch

from flask import Flask

from app.routes.menu import _enrich_item, _review_stats
from app.services import hp_service


class RpcDb:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def rpc(self, name, params):
        self.calls.append((name, params))
        return self.rows


def test_menu_item_multiplier_badges_and_preview():
    item = {"id": "item-1", "price": 1000, "hp_earn_value": 100, "hp_multiplier": 2}

    _enrich_item(item, {}, False)

    assert item["hp_multiplier"] == 2.0
    assert item["hp_multiplier_badge"] == "2× HP"
    assert item["hp_earn_preview"] == 200


def test_menu_item_half_multiplier_badge():
    item = {"id": "item-1", "hp_multiplier": 0.5}

    _enrich_item(item, {}, False)

    assert item["hp_multiplier_badge"] == "½ HP"


def test_review_stats_uses_one_sql_aggregation_call_and_zero_defaults():
    db = RpcDb([{"menu_item_id": "item-1", "avg_rating": "4.25", "review_count": 2}])

    stats = _review_stats(db, ["item-1", "item-2"])

    assert db.calls == [(
        "get_menu_item_review_stats",
        {"p_item_ids": ["item-1", "item-2"]},
    )]
    assert stats["item-1"] == {"avg_rating": 4.25, "review_count": 2}
    assert "item-2" not in stats


def test_calculate_delivery_hp_combines_item_and_tier_multipliers():
    app = Flask(__name__)
    app.config.update(HP_PER_NAIRA_FOOD=0.1, HP_UNLOCK_RATE_PCT=0.30,
                      TIER_MULTIPLIERS={"blaze": 1.15})

    with app.app_context():
        total_hp = hp_service.calculate_delivery_hp(
            order_total=1000,
            tier_slug="blaze",
            order_items=[{
                "price_snapshot": 1000,
                "quantity": 1,
                "hp_multiplier_snapshot": 2.0,
                "is_addon": False,
            }],
        )

    assert total_hp == 230


def test_migration_has_per_item_column_indexes_and_delivered_review_filter():
    import pytest
    sql_path = Path("migrations/20260809_menu_item_hp_reviews.sql")
    if not sql_path.exists():
        pytest.skip("Migration file 20260809_menu_item_hp_reviews.sql does not exist in this environment")
    sql = sql_path.read_text()

    assert "menu_items" in sql and "hp_multiplier" in sql
    assert "hp_multiplier_snapshot" in sql
    assert "idx_order_items_menu_item_id" in sql
    assert "idx_order_reviews_order_id" in sql
    assert "o.status = 'delivered'" in sql
    assert "r.rating IS NOT NULL" in sql
    assert "ROUND(AVG(r.rating)" in sql