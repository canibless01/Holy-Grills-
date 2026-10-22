import unittest,copy
from unittest.mock import patch,MagicMock
from flask import Flask
from app.db import SupabaseError
from app.services import notification_service as service
from app.services.notification_preferences import effective_preferences,permitted_channels,category_for_notification

class Query:
    def __init__(self,db,table):self.db,self.table,self.filters=db,table,{}
    def select(self,*args):return self
    def eq(self,k,v):self.filters[k]=v;return self
    def single(self):return self
    def execute(self):
        if self.table in self.db.fail:raise RuntimeError('unavailable')
        rows=self.db.rows.get(self.table,[])
        return next((copy.deepcopy(r) for r in rows if all(r.get(k)==v for k,v in self.filters.items())),None)
    def insert(self,row):
        rows=self.db.rows.setdefault(self.table,[])
        if row.get('id') and any(r.get('id')==row['id'] for r in rows):raise SupabaseError('duplicate',409,{'code':'23505'})
        row=copy.deepcopy(row);row.setdefault('id',str(len(rows)+1));rows.append(row);return row
class Db:
    def __init__(self):self.fail=set();self.rows={'profiles':[{'id':'user','campus_id':'campus','push_enabled':True,'email_notifications':True}], 'notification_preferences':[{'user_id':'user'}]}
    def table(self,name):return Query(self,name)

class NotificationDeliveryTests(unittest.TestCase):
    def setUp(self):self.db=Db();self.app=Flask(__name__)
    def test_either_legacy_or_canonical_channel_opt_out_is_honored(self):
        self.db.rows['profiles'][0]['push_enabled']=False
        self.db.rows['notification_preferences'][0]['email_enabled']=False
        prefs=effective_preferences(self.db,'user')
        self.assertEqual(permitted_channels('order_confirmed',['push','email','in_app'],prefs),['in_app'])
    def test_categories_suppress_their_actual_channels_only(self):
        for kind,category in [('order_confirmed','order_updates'),('order_out_for_delivery','delivery_updates'),('free_side_credits_granted','hp_updates'),('blast','promotions')]:
            with self.subTest(kind=kind):
                self.assertEqual(category_for_notification(kind),category)
                self.assertEqual(permitted_channels(kind,['push','email','in_app'],{category:False}),[])
        self.assertEqual(permitted_channels('order_confirmed',['in_app'],{'delivery_updates':False}),['in_app'])
        self.assertEqual(permitted_channels('password_reset',['in_app'],{'promotions':False}),['in_app'])
    def test_category_opt_out_prevents_row_and_external_dispatch(self):
        self.db.rows['notification_preferences'][0]['order_updates']=False
        with self.app.app_context(),patch.object(service,'get_db',return_value=self.db),patch.object(service.threading,'Thread') as dispatch:
            self.assertEqual(service.send_notification('user','order_confirmed',title='receipt',body='body',channels=['push','email','in_app']),[])
            dispatch.assert_not_called();self.assertNotIn('notifications',self.db.rows)
    def test_preference_outage_does_not_send_against_unknown_opt_out(self):
        self.db.fail={'notification_preferences'}
        with self.app.app_context(),patch.object(service,'get_db',return_value=self.db),patch.object(service.threading,'Thread') as dispatch:
            self.assertEqual(service.send_notification('user','order_confirmed',title='receipt',body='body'),[])
            dispatch.assert_not_called();self.assertNotIn('notifications',self.db.rows)
    def test_request_receipts_deduplicate_per_request_and_channel(self):
        with self.app.app_context(),patch.object(service,'get_db',return_value=self.db),patch.object(service.threading,'Thread') as dispatch:
            for ref in ('request1','request1','request2'):
                rows=service.send_notification('user','catering_request',title='receipt',body='body',reference_id=ref,reference_type='catering_request',channels=['push','email','in_app'])
                self.assertEqual(len(rows),3)
            self.assertEqual(len(self.db.rows['notifications']),6)
            self.assertEqual(len(self.db.rows['notification_log']),2)
            self.assertEqual(dispatch.call_count,4)
            self.assertFalse(service._is_throttled(MagicMock(),'user','marketplace_request'))
    def test_order_saved_template_creates_honest_receipt_and_avoids_marketing_throttle(self):
        with self.app.app_context(), patch.object(service,'get_db',return_value=self.db), patch.object(service.threading,'Thread'):
            rows=service.send_notification('user','order_placed',template_data={'order_id':'ABCD1234','name':'Student'},action_url='/orders/full-id',channels=['in_app'])
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['title'],'Order saved')
        self.assertIn('ABCD1234',rows[0]['body'])
        self.assertIn('check payment',rows[0]['body'])
        self.assertEqual(rows[0]['action_url'],'/orders/full-id')
        self.assertFalse(service._is_throttled(MagicMock(),'user','order_placed'))
