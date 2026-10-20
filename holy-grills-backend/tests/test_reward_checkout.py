import copy
import unittest
from unittest.mock import patch
from flask import Flask, g
from app.services.reward_checkout import reward_checkout_plan

RID = '00000000-0000-4000-8000-000000000001'
RID2 = '00000000-0000-4000-8000-000000000002'


class Query:
    def __init__(self, db, table):
        self.db, self.name, self.filters, self.one = db, table, [], False
    def select(self, *_): return self
    def eq(self, key, value):
        self.filters.append(lambda row: row.get(key) == value)
        return self
    def is_(self, key, value):
        assert value == 'null'
        self.filters.append(lambda row: row.get(key) is None)
        return self
    def single(self):
        self.one = True
        return self
    def execute(self):
        rows = [copy.deepcopy(row) for row in self.db.rows.get(self.name, []) if all(f(row) for f in self.filters)]
        return (rows[0] if rows else None) if self.one else rows
    def update(self, changes):
        rows = [row for row in self.db.rows.get(self.name, []) if all(f(row) for f in self.filters)]
        for row in rows: row.update(changes)
        return rows


class DB:
    def __init__(self):
        self.rows = {'reward_redemptions': [{'id': RID, 'user_id': 'owner', 'campus_id': 'campus',
                     'reward_id': 'reward', 'status': 'fulfilled', 'delivery_mode': 'instant',
                     'attached_order_id': None, 'used_at': None}],
                     'rewards': [{'id': 'reward', 'name': 'Free lunch', 'fulfillment_type': 'menu_item',
                                  'menu_item_id': 'menu', 'campus_id': 'campus', 'reward_type': 'food'}],
                     'menu_items': [{'id': 'menu', 'campus_id': 'campus', 'is_available': True}]}
    def table(self, table): return Query(self, table)


class RewardCheckoutTests(unittest.TestCase):
    def setUp(self): self.db = DB()
    def plan(self, **kw): return reward_checkout_plan(self.db, 'owner', 'campus', **kw)
    def test_explicit_reward_is_server_priced_without_food_hp(self):
        plan = self.plan(redemption_id=RID, include_next_order=False)
        self.assertEqual(plan['claims'], [RID])
        self.assertEqual(plan['items'][0]['price_snapshot'], 0)
        self.assertEqual(plan['items'][0]['hp_earn_snapshot'], 0)
        self.assertEqual(plan['items'][0]['options_snapshot']['reward_redemption_id'], RID)
    def test_foreign_used_pending_and_cross_campus_fail_explicitly(self):
        for changed in ({'user_id': 'attacker'}, {'status': 'pending'}, {'attached_order_id': 'order'},
                        {'used_at': 'yesterday'}, {'campus_id': 'other'}):
            with self.subTest(changed=changed):
                db = DB(); db.rows['reward_redemptions'][0].update(changed)
                with self.assertRaises(ValueError):
                    reward_checkout_plan(db, 'owner', 'campus', RID)
    def test_automatic_reward_waits_when_menu_unavailable(self):
        self.db.rows['reward_redemptions'][0]['delivery_mode'] = 'next_order'
        self.db.rows['menu_items'][0]['is_available'] = False
        self.assertEqual(self.plan(), {'items': [], 'claims': []})
        with self.assertRaises(ValueError): self.plan(redemption_id=RID)
    def test_simple_physical_reward_has_nullable_menu_and_zero_price(self):
        self.db.rows['rewards'][0].update(fulfillment_type='simple', menu_item_id=None)
        self.assertIsNone(self.plan(redemption_id=RID)['items'][0]['menu_item_id'])
    def test_automatic_claims_are_sorted_deduplicated_and_can_be_excluded(self):
        first = self.db.rows['reward_redemptions'][0]
        first['delivery_mode'] = 'next_order'
        self.db.rows['reward_redemptions'].insert(0, dict(first, id=RID2))
        self.assertEqual(self.plan(redemption_id=RID)['claims'], [RID, RID2])
        self.assertEqual(self.plan(redemption_id=RID, include_next_order=False)['claims'], [RID])
    def test_guest_has_no_automatic_claims(self):
        self.assertEqual(reward_checkout_plan(self.db, None, 'campus'), {'items': [], 'claims': []})
        with self.assertRaises(ValueError): reward_checkout_plan(self.db, None, 'campus', RID)


class DeliveryChoiceTests(unittest.TestCase):
    def test_lost_response_retry_and_change_choice_are_safe_until_claimed(self):
        from app.routes.rewards import choose_redemption_delivery
        db = DB()
        app = Flask(__name__)
        for mode in ('next_order', 'next_order', 'instant'):
            with app.test_request_context(json={'delivery_mode': mode}), \
                 patch('app.routes.rewards.get_user_client', return_value=db), \
                 patch('app.routes.rewards.get_db', return_value=db):
                g.user_id = 'owner'
                response, status = choose_redemption_delivery.__wrapped__(RID)
                self.assertEqual(status, 200)
                self.assertEqual(response.json['delivery_mode'], mode)
        db.rows['reward_redemptions'][0]['attached_order_id'] = 'order'
        with app.test_request_context(json={'delivery_mode': 'instant'}), \
             patch('app.routes.rewards.get_user_client', return_value=db):
            g.user_id = 'owner'
            self.assertEqual(choose_redemption_delivery.__wrapped__(RID)[1], 400)
