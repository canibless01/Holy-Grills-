"""Free-side promises must be quoted from persisted selections and fail closed."""
import copy
import inspect
import unittest
from unittest.mock import MagicMock, patch
from flask import Flask, g
from app.services.free_side_checkout import quote_free_sides
from app.routes import free_sides
from app.services.notification_templates import render_notification_template
from app.services.notification_service import default_action_url, _is_throttled

class Query:
    def __init__(self,db,table):self.db,self.table,self.one=db,table,False
    def select(self,*a):return self
    def eq(self,*a):return self
    def is_(self,*a):return self
    def gt(self,*a):return self
    def gte(self,*a):return self
    def or_(self,*a):return self
    def order(self,*a):return self
    def single(self):self.one=True;return self
    def execute(self):
        if self.table in self.db.fail:raise RuntimeError('unavailable')
        rows=copy.deepcopy(self.db.rows.get(self.table,[]))
        return rows[0] if rows and self.one else None if self.one else rows
class Db:
    def __init__(self):
        self.fail=set();self.rows={'feature_flags':[{'is_active':True}], 'cart_free_side_selections':[{'id':'selection','campus_id':'campus','free_side_items':{'id':'side','name':'Grilled slaw','is_active':True,'campus_id':'campus'}}], 'free_side_credits':[{'credits_remaining':1}]}
    def table(self,t):return Query(self,t)

class FreeSideQuoteTests(unittest.TestCase):
    def setUp(self):self.db=Db()
    def test_quote_reads_the_persisted_choice_without_spending(self):
        before=copy.deepcopy(self.db.rows);result=quote_free_sides(self.db,'student','campus')
        self.assertEqual(result['items'],[{'selection_id':'selection','free_side_item_id':'side','name':'Grilled slaw'}]);self.assertEqual(self.db.rows,before)
    def test_guest_or_disabled_feature_has_no_credit_claim(self):
        self.assertEqual(quote_free_sides(None,None,'campus')['items'],[])
        self.db.rows['feature_flags'][0]['is_active']=False
        self.assertEqual(quote_free_sides(self.db,'student','campus'),{'enabled':False,'items':[]})
        self.assertEqual(len(self.db.rows['cart_free_side_selections']),1)
    def test_inactive_foreign_or_missing_item_requires_review(self):
        for change in [{'is_active':False},{'campus_id':'foreign'},{}]:
            self.db=Db();self.db.rows['cart_free_side_selections'][0]['free_side_items']=change
            with self.subTest(change=change),self.assertRaises(ValueError):quote_free_sides(self.db,'student','campus')
    def test_expired_or_missing_credit_cannot_promise_free_side(self):
        self.db.rows['free_side_credits']=[]
        with self.assertRaises(ValueError):quote_free_sides(self.db,'student','campus')
    def test_outage_does_not_silently_drop_the_selected_reward(self):
        for table in ['feature_flags','cart_free_side_selections','free_side_credits']:
            self.db.fail={table}
            with self.subTest(table=table),self.assertRaises(RuntimeError):quote_free_sides(self.db,'student','campus')

class FreeSideControlTests(unittest.TestCase):
    def setUp(self):self.app=Flask(__name__)
    def test_bad_grant_counts_are_rejected_before_writes(self):
        body={'user_id':'b9860c43-e26d-4959-aa2c-3fa56e25a2dd','intent_key':'1e079348-73ed-4966-88f1-54d4e1d1e76d','validity_days':7}
        for value in [True,1.5,'1.5',0,21,None]:
            with self.subTest(value=value),self.app.test_request_context(json={**body,'credits':value}),patch.object(free_sides,'get_db') as db:
                _,status=inspect.unwrap(free_sides.admin_grant_free_side_credits)();self.assertEqual(status,400);db.assert_not_called()
    def test_grant_replay_does_not_repeat_notification(self):
        body={'user_id':'b9860c43-e26d-4959-aa2c-3fa56e25a2dd','intent_key':'1e079348-73ed-4966-88f1-54d4e1d1e76d','validity_days':7,'credits':1}
        db=MagicMock();db.rpc.return_value={'idempotent':True,'expires_at':'2026-11-14T00:00:00Z'}
        with self.app.test_request_context(json=body),patch.object(free_sides,'get_db',return_value=db),patch('app.middleware.auth.fetch_or_403',return_value=({'id':body['user_id'],'campus_id':'campus'},None)),patch('app.services.notification_service.send_notification') as notify:
            g.user_id='admin';_,status=inspect.unwrap(free_sides.admin_grant_free_side_credits)();self.assertEqual(status,200);notify.assert_not_called()
    def test_credit_and_spin_grant_notifications_render_and_link_to_rewards(self):
        with self.app.app_context():
            for kind,data in [('free_side_credits_granted',{'credits':2}),('exclusive_spin_granted',{'spins':2})]:
                payload={**data,'name':'Audit Student','expires_at':'2026-11-14'}
                rendered=render_notification_template(kind,payload)
                self.assertIsNotNone(rendered);self.assertIn('2',rendered[1]);self.assertEqual(default_action_url(kind,payload),'/rewards')
    def test_independent_grant_receipts_are_not_marketing_throttled(self):
        db=MagicMock()
        for kind in ('free_side_credits_granted','exclusive_spin_granted'):
            self.assertFalse(_is_throttled(db,'student',kind))
        db.table.assert_not_called()
