import copy
import unittest
from unittest.mock import patch, MagicMock
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
    def in_(self, key, values):
        self.filters.append(lambda row: row.get(key) in values)
        return self
    def is_(self, key, value):
        assert value == 'null'
        self.filters.append(lambda row: row.get(key) is None)
        return self
    def single(self):
        self.one = True
        return self
    def order(self, *_args, **_kwargs): return self
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
                                  'metadata': {'menu_item_id': '00000000-0000-4000-8000-000000000099'}, 'campus_id': 'campus', 'reward_type': 'food'}],
                     'menu_items': [{'id': '00000000-0000-4000-8000-000000000099', 'campus_id': 'campus', 'is_available': True}]}
    def table(self, table): return Query(self, table)


class RewardCheckoutTests(unittest.TestCase):
    def setUp(self): self.db = DB()
    def plan(self, **kw): return reward_checkout_plan(self.db, 'owner', 'campus', **kw)
    def test_catalog_edits_do_not_replace_an_earned_reward(self):
        original = copy.deepcopy(self.db.rows['rewards'][0])
        self.db.rows['reward_redemptions'][0]['reward_snapshot'] = {**original, 'version': 1}
        self.db.rows['rewards'][0].update(name='Replacement dish', metadata={})
        plan = self.plan(redemption_id=RID, include_next_order=False)
        self.assertEqual(plan['items'][0]['name_snapshot'], 'Free lunch')
        self.assertEqual(plan['items'][0]['menu_item_id'], original['metadata']['menu_item_id'])
        self.assertEqual(plan['items'][0]['price_snapshot'], 0)

    def test_earned_snapshot_does_not_need_a_visible_catalog_row(self):
        original = copy.deepcopy(self.db.rows['rewards'][0])
        self.db.rows['reward_redemptions'][0]['reward_snapshot'] = {**original, 'version': 1}
        self.db.rows['rewards'] = []
        self.assertEqual(self.plan(redemption_id=RID)['claims'], [RID])

    def test_original_dish_unavailability_does_not_substitute_new_catalog_dish(self):
        original = copy.deepcopy(self.db.rows['rewards'][0])
        self.db.rows['reward_redemptions'][0]['reward_snapshot'] = {**original, 'version': 1}
        self.db.rows['menu_items'][0]['is_available'] = False
        self.db.rows['rewards'][0]['metadata'] = {}
        with self.assertRaises(ValueError): self.plan(redemption_id=RID)

    def test_bad_snapshot_cannot_silently_fall_back_to_new_catalog(self):
        self.db.rows['reward_redemptions'][0]['reward_snapshot'] = {'version': 1, 'id': 'other', 'name': 'Wrong'}
        with self.assertRaises(ValueError): self.plan(redemption_id=RID)
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
        self.db.rows['rewards'][0].update(fulfillment_type='simple', metadata={})
        self.assertIsNone(self.plan(redemption_id=RID)['items'][0]['menu_item_id'])
    def test_automatic_claims_are_sorted_deduplicated_and_can_be_excluded(self):
        first = self.db.rows['reward_redemptions'][0]
        first['delivery_mode'] = 'next_order'
        self.db.rows['reward_redemptions'].insert(0, dict(first, id=RID2))
        self.assertEqual(self.plan(redemption_id=RID)['claims'], [RID, RID2])
        self.assertEqual(self.plan(redemption_id=RID, include_next_order=False)['claims'], [RID])
    def test_malformed_optional_link_waits_automatically_but_explicit_fails(self):
        self.db.rows['rewards'][0]['metadata']['menu_item_id'] = 'not-a-uuid'
        self.db.rows['reward_redemptions'][0]['delivery_mode'] = 'next_order'
        self.assertEqual(self.plan(), {'items': [], 'claims': []})
        with self.assertRaises(ValueError): self.plan(redemption_id=RID)
    def test_unlinked_food_reward_is_its_own_named_kitchen_line(self):
        self.db.rows['rewards'][0]['metadata'] = {}
        self.assertIsNone(self.plan(redemption_id=RID)['items'][0]['menu_item_id'])
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


class RedemptionHistoryTests(unittest.TestCase):
    def test_success_reports_actual_spent_hp_and_saved_name(self):
        from app.routes import rewards
        user_db=DB(); user_db.rows['rewards'][0]['hp_cost']=100
        service=DB(); service.rpc=MagicMock(return_value={'id':RID,'hp_cost_snapshot':25,'status':'fulfilled'})
        service.rows['reward_redemptions'][0]['reward_snapshot']={'version':1,'id':'reward','name':'Earned meal'}
        with Flask(__name__).test_request_context(method='POST'), \
             patch.object(rewards,'get_user_client',return_value=user_db), \
             patch.object(rewards,'get_db',return_value=service),patch.object(rewards,'send_notification') as notify:
            g.user_id='owner'
            response,status=rewards.redeem_reward.__wrapped__('reward')
        self.assertEqual(status,201)
        self.assertEqual(response.json['hp_spent'],25)
        self.assertEqual(notify.call_args.kwargs['template_data'],{'name':'Earned meal','hp':25})

    def test_post_commit_display_outage_does_not_instruct_redemption_retry(self):
        from app.routes import rewards
        user_db=DB(); user_db.rows['rewards'][0]['hp_cost']=100
        service=MagicMock(); service.rpc.return_value={'id':RID,'hp_cost_snapshot':25,'status':'fulfilled'}
        service.table.side_effect=RuntimeError('temporary lookup failure')
        with Flask(__name__).test_request_context(method='POST'), \
             patch.object(rewards,'get_user_client',return_value=user_db), \
             patch.object(rewards,'get_db',return_value=service),patch.object(rewards,'send_notification'):
            g.user_id='owner'
            response,status=rewards.redeem_reward.__wrapped__('reward')
        self.assertEqual(status,201)
        self.assertEqual(response.json['hp_spent'],25)

    def test_history_uses_earned_name_image_and_hp_cost(self):
        from app.services.reward_promises import display_earned_reward
        row={'reward_id':'reward','hp_cost_snapshot':25,'rewards':{'name':'New name','hp_cost':100},
             'reward_snapshot':{'version':1,'id':'reward','name':'Earned meal','image_url':'saved-image','reward_type':'food'}}
        display=display_earned_reward(row)['rewards']
        self.assertEqual(display['name'],'Earned meal')
        self.assertEqual(display['image_url'],'saved-image')
        self.assertEqual(display['hp_cost'],25)

    def test_hidden_catalog_name_is_loaded_only_for_owned_history(self):
        from app.routes.rewards import my_redemptions
        db = DB()
        db.rows['reward_redemptions'].append(dict(db.rows['reward_redemptions'][0], id=RID2,
                                                user_id='someone-else', reward_id='private-reward'))
        db.rows['rewards'].append({'id': 'private-reward', 'name': 'Foreign history'})
        service = DB()
        with Flask(__name__).test_request_context(), \
             patch('app.routes.rewards.get_user_client', return_value=db), \
             patch('app.routes.rewards.get_db', return_value=service):
            g.user_id = 'owner'
            response, status = my_redemptions.__wrapped__()
        self.assertEqual(status, 200)
        self.assertEqual(len(response.json), 1)
        self.assertEqual(response.json[0]['rewards']['name'], 'Free lunch')
        self.assertEqual(response.json[0]['user_id'], 'owner')


class RewardOnlyAdmissionTests(unittest.TestCase):
    def test_empty_cart_requires_explicit_reward_and_still_reaches_server_validation(self):
        import inspect
        from app.routes.orders import create_order
        route = inspect.unwrap(create_order)
        app = Flask(__name__)
        for body, expected in (({'items': [], 'redemption_id': RID}, 201),
                               ({'items': []}, 400),
                               ({'items': 'invalid', 'redemption_id': RID}, 400)):
            with self.subTest(body=body), app.test_request_context(json={**body, 'payment_method': 'wallet'}), \
                 patch('app.routes.orders.order_service.create_order', return_value={'id': 'saved'}) as service:
                g.user_id = 'owner'
                _, status = route()
                self.assertEqual(status, expected)
                if expected == 201:
                    service.assert_called_once()
                    self.assertEqual(service.call_args.args[0], 'owner')
                else:
                    service.assert_not_called()
