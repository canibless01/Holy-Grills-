import unittest
from unittest.mock import patch
from flask import Flask
from app.services.food_hp_plan import food_hp_lines
from app.services.hp_service import calculate_delivery_hp


class FoodSpendPlanTests(unittest.TestCase):
    def setUp(self):
        self.items = [{'price_snapshot': 1000, 'quantity': 1, 'hp_multiplier_snapshot': 2},
                      {'price_snapshot': 500, 'quantity': 1, 'is_addon': True},
                      {'price_snapshot': 0, 'quantity': 1, 'is_addon': False}]

    def calculate(self, **kwargs):
        with Flask(__name__).app_context(), patch('app.services.hp_service._get_food_earn_rate', return_value=0.1), \
                patch('app.services.hp_service._get_hp_multiplier', return_value=1), \
                patch('app.services.hp_service._get_menu_multiplier', return_value=1), \
                patch('app.services.hp_service._tier_multiplier_for_slug', return_value=1):
            return calculate_delivery_hp(1500, 'ember', self.items, **kwargs)

    def test_global_addons_earn_normal_hp_and_item_multiplier_stays_local(self):
        self.assertEqual(self.calculate(include_addons=True, net_food_spend=1500), 250)
        self.assertEqual(self.calculate(), 200)  # Historical behavior remains explicit.

    def test_food_discount_is_prorated_without_including_delivery(self):
        lines = food_hp_lines(self.items, 0.1, include_addons=True, net_food_spend=900)
        self.assertEqual([r['eligible_spend'] for r in lines], [600, 300])
        self.assertEqual(self.calculate(include_addons=True, net_food_spend=900), 150)
        self.assertEqual(self.calculate(include_addons=True, net_food_spend=0), 0)

    def test_spend_cannot_exceed_paid_lines_and_free_rewards_do_not_earn_hp(self):
        self.assertEqual(self.calculate(include_addons=True, net_food_spend=2000), 250)
        self.assertEqual(food_hp_lines([{'price_snapshot': 0, 'quantity': 1}], 0.1, include_addons=True), [])

    def test_quantity_and_pennies_use_paid_line_value(self):
        rows = food_hp_lines([{'price_snapshot': 99.99, 'quantity': 3, 'is_addon': True}], 0.1, include_addons=True)
        self.assertEqual(rows[0]['base_hp'], 29)
