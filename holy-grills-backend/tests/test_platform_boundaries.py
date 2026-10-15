"""Isolated route regressions; these do not prove live UI/provider delivery."""
import unittest
from unittest.mock import MagicMock, patch
from flask import Flask, g
from werkzeug.exceptions import Forbidden
from app.routes import events, notifications, marketplace, kitchen, delivery
from app.middleware.auth import require_role
from app.routes import departments, academic_levels, academic_calendar, auth

A = 'bbbb0000-0000-4000-8000-000000000001'
B = 'bbbb0000-0000-4000-8000-000000000002'
USER = 'bbbb0000-0000-4000-8000-000000000003'
EVENT = 'bbbb0000-0000-4000-8000-000000000004'
TICKET = 'bbbb0000-0000-4000-8000-000000000005'

class Query:
    def __init__(self, db, table):
        self.db, self.table_name, self.filters, self.one = db, table, {}, False
    def select(self, *a, **kw): return self
    def eq(self, k, v): self.filters[k] = v; return self
    def order(self, *a, **kw): return self
    def limit(self, *a): return self
    def single(self): self.one = True; return self
    def execute(self):
        rows = [r.copy() for r in self.db.rows.get(self.table_name, []) if all(r.get(k) == v for k, v in self.filters.items())]
        return (rows[0] if rows else None) if self.one else rows
    def insert(self, payload):
        self.db.writes.append((self.table_name, payload)); return [payload]

class DB:
    def __init__(self, rows): self.rows, self.writes = rows, []
    def table(self, name): return Query(self, name)

class PlatformBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config['PHONE_REGEX_PATTERN'] = r'^(\+?234|0)[789]\d{9}$'
    def identity(self, role='student', campus=A):
        g.user_id, g.user_role, g.campus_id = USER, role, campus
    def test_profile_photo_clear_persists_null_and_requires_a_saved_row(self):
        for saved, expected in [([{'id': USER, 'photo_url': None}], 200), ([], 503)]:
            db = MagicMock()
            db.table.return_value.eq.return_value.update.return_value = saved
            with self.app.test_request_context(method='POST', json={'photo_url': None}), patch.object(auth, 'get_user_client', return_value=db):
                self.identity()
                _, status = auth.update_profile_photo.__wrapped__()
                self.assertEqual(status, expected)
                self.assertIsNone(db.table.return_value.eq.return_value.update.call_args.args[0]['photo_url'])
    def test_stock_opening_balance_must_go_through_existing_ledger_adjustment(self):
        db = DB({})
        body = {'name': 'Owned ingredient', 'purchase_unit_id': A, 'usage_unit_id': A, 'conversion_factor': 1, 'low_stock_threshold': 0, 'current_balance': 2}
        with self.app.test_request_context(method='POST', json=body), patch.object(kitchen, 'get_user_client', return_value=db):
            self.identity('admin')
            _, status = kitchen.create_stock_item.__wrapped__()
            self.assertEqual(status, 400)
            self.assertEqual(db.writes, [])
    def test_shared_public_reference_scope_preserves_guest_and_super_choices_only(self):
        from app.utils.campus_scope import public_campus
        with self.app.test_request_context():
            self.assertEqual(public_campus(B), B)
            for role in ('student', 'kitchen', 'rider', 'admin'):
                self.identity(role)
                self.assertEqual(public_campus(B), A)
            self.identity('super_admin')
            self.assertEqual(public_campus(B), B)
            self.identity('student', None)
            self.assertIsNone(public_campus(B))
    def test_committed_scan_with_missing_reward_recovers_without_second_checkin(self):
        db = DB({'events': [{'id': EVENT, 'campus_id': A, 'is_published': True, 'hp_per_attendee': 50}],
                 'event_door_tokens': [{'event_id': EVENT, 'qr_token': 'door'}],
                 'event_tickets': [{'id': TICKET, 'event_id': EVENT, 'user_id': USER, 'status': 'confirmed', 'payment_status': 'paid'}],
                 'event_checkins': [{'id': B, 'ticket_id': TICKET}]})
        with self.app.test_request_context(method='POST', json={'qr_token': 'door', 'ticket_id': TICKET}), patch.object(events, 'get_user_client', return_value=db), patch.object(events, 'get_db', return_value=db), patch.object(events, 'award_active_hp', return_value={'awarded': 50, 'replayed': False}) as award, patch('app.services.milestone_service.check_milestone_trigger'):
            self.identity()
            response, status = events.checkin.__wrapped__(EVENT)
            self.assertEqual(status, 200)
            self.assertTrue(response.json['recovered'])
            self.assertEqual(response.json['hp_added_to_active'], 50)
            self.assertEqual(response.json['hp_added_to_pending'], 0)
            self.assertEqual(db.writes, [])
            self.assertEqual(award.call_args.kwargs['reference_id'], EVENT)
    def test_calendar_explicit_global_selection_beats_super_admin_header_only(self):
        payload = {'name': 'Audit term', 'period_type': 'semester', 'academic_year': '2026/2027', 'start_date': '2026-10-14', 'end_date': '2026-10-15', 'campus_id': None}
        for role, expected in [('super_admin', None), ('admin', A)]:
            db = DB({})
            with self.app.test_request_context(method='POST', json=payload, headers={'X-Campus-ID': A}), patch.object(academic_calendar, 'get_user_client', return_value=db):
                self.identity(role)
                _, status = academic_calendar.create_academic_calendar_entry.__wrapped__()
                self.assertEqual(status, 201)
                self.assertEqual(db.writes[0][1]['campus_id'], expected)
    def test_sold_out_purchase_retry_returns_owned_receipt_before_stock_or_reward_calls(self):
        receipt = {'id': TICKET, 'user_id': USER, 'listing_id': EVENT,
                   'payment_reference': 'owned-intent', 'wallet_amount': 25,
                   'card_amount': 5, 'pay_with_hp': True, 'metadata': {'code': 'owned-code'}}
        db = DB({'marketplace_purchases': [receipt]})
        with self.app.test_request_context(method='POST', json={'idempotency_key': 'owned-intent'}), patch.object(marketplace, 'get_user_client', return_value=db), patch.object(marketplace, 'is_feature_enabled', return_value=True), patch.object(marketplace, '_complete_marketplace_purchase') as complete:
            self.identity()
            response, status = marketplace.purchase.__wrapped__(EVENT)
            self.assertEqual(status, 200)
            self.assertEqual(response.json['purchase']['id'], TICKET)
            self.assertEqual(response.json['cash_charged'], 30)
            self.assertTrue(response.json['paid_with_hp'])
            complete.assert_not_called()
    def test_purchase_intent_cannot_return_a_different_listing_receipt(self):
        db = DB({'marketplace_purchases': [{'id': TICKET, 'user_id': USER, 'listing_id': B, 'payment_reference': 'owned-intent'}]})
        with self.app.test_request_context(method='POST', json={'idempotency_key': 'owned-intent'}), patch.object(marketplace, 'get_user_client', return_value=db), patch.object(marketplace, 'is_feature_enabled', return_value=True), patch.object(marketplace, '_complete_marketplace_purchase') as complete:
            self.identity()
            _, status = marketplace.purchase.__wrapped__(EVENT)
            self.assertEqual(status, 409)
            complete.assert_not_called()
    def test_registrants_url_is_bound_to_the_handler(self):
        self.app.register_blueprint(events.events_bp, url_prefix='/events')
        endpoint, _ = self.app.url_map.bind('localhost').match('/events/'+EVENT+'/registrants')
        self.assertEqual(self.app.view_functions[endpoint].__name__, 'list_event_registrants')
    def test_email_or_own_ticket_without_door_qr_cannot_check_in(self):
        db = DB({'event_door_tokens':[{'event_id':EVENT,'qr_token':'door'}], 'events':[{'id':EVENT,'campus_id':A,'is_published':True,'metadata':{}}]})
        for body in ({'guest_email':'audit@example.invalid'}, {'ticket_id':TICKET}, {'qr_token':'wrong'}):
            with self.app.test_request_context(method='POST',json=body), patch.object(events,'get_user_client',return_value=db), patch.object(events,'get_db',return_value=db):
                self.identity()
                _, status = events.checkin.__wrapped__(EVENT)
                self.assertEqual(status,400)
                self.assertEqual(db.writes,[])
    def test_unpaid_cancelled_or_other_event_tickets_are_not_inserted(self):
        for payment,status,event_id in [('pending','pending',EVENT),('paid','cancelled',EVENT),('paid','confirmed',B)]:
            db = DB({'event_door_tokens':[{'event_id':EVENT,'qr_token':'door'}], 'events':[{'id':EVENT,'campus_id':A,'is_published':True,'metadata':{}}],
                     'event_tickets':[{'id':TICKET,'event_id':event_id,'user_id':USER,'status':status,'payment_status':payment}]})
            with self.app.test_request_context(method='POST',json={'qr_token':'door','ticket_id':TICKET}), patch.object(events,'get_user_client',return_value=db), patch.object(events,'get_db',return_value=db):
                self.identity()
                _, response_status = events.checkin.__wrapped__(EVENT)
                self.assertIn(response_status,(400,409))
                self.assertEqual(db.writes,[])
    def test_global_and_foreign_event_edits_are_denied(self):
        for campus in (B,None):
            db=DB({'events':[{'id':EVENT,'campus_id':campus}]})
            with self.app.test_request_context(method='POST',json={}),patch.object(events,'get_user_client',return_value=db):
                self.identity('admin')
                with self.assertRaises(Forbidden): events.generate_event_qr.__wrapped__(EVENT)
    def test_preferences_patch_preserves_other_opt_outs(self):
        db=MagicMock()
        db.rpc.return_value={'email_enabled':False,'promotions':False,'push_enabled':False}
        with self.app.test_request_context(method='PATCH',json={'push_enabled':False}),patch.object(notifications,'get_db',return_value=db):
            self.identity()
            _,status=notifications.update_preferences.__wrapped__()
            self.assertEqual(status,200)
            payload=db.rpc.call_args.args[1]['p_preferences']
            self.assertNotIn('email_enabled',payload)
            self.assertNotIn('promotions',payload)
    def test_preferences_reject_coercion(self):
        for body in ([False], {'push_enabled':'false'}, {'email_enabled':0}):
            with self.app.test_request_context(method='PATCH',json=body),patch.object(notifications,'get_user_client',return_value=MagicMock()):
                self.identity(); _,status=notifications.update_preferences.__wrapped__(); self.assertEqual(status,400)
    def test_preference_write_failure_is_not_success(self):
        db=MagicMock(); db.rpc.side_effect=RuntimeError('relation missing')
        with self.app.test_request_context(method='PATCH',json={'push_enabled':False}),patch.object(notifications,'get_db',return_value=db):
            self.identity(); _,status=notifications.update_preferences.__wrapped__(); self.assertEqual(status,503)
    def test_campus_blast_cannot_override_recipient_campus(self):
        for key in ('campus','campus_id'):
            with self.app.test_request_context(method='POST',json={'title':'Audit','body':'Synthetic','channels':['in_app'],'target_segment':{key:B}}),patch.object(notifications,'get_user_client',return_value=MagicMock()):
                self.identity('admin'); _,status=notifications.create_blast.__wrapped__(); self.assertEqual(status,403)
    def test_catering_validates_before_insert(self):
        good={'organizer_name':'Audit B','email':'audit-b@example.invalid','phone':'08012345678','event_name':'Audit B','event_date':'2026-12-01','expected_guests':10}
        for key,value in [('email','bad'),('phone',123),('event_date','bad'),('expected_guests',True),('expected_guests',1.5),('budget',-1),('budget',float('inf')),('hp_promo_optin','false')]:
            db=DB({})
            with self.app.test_request_context(method='POST',json={**good,key:value}),patch.object(events,'get_db',return_value=db):
                self.identity(); _,status=events.submit_catering_request.__wrapped__.__wrapped__(); self.assertEqual(status,400); self.assertEqual(db.writes,[])
    def test_marketplace_rejects_unknown_payment_and_string_hp(self):
        for body in ([], {'payment_method':'cash'}, {'use_hp':'false'}):
            with self.app.test_request_context(method='POST',json=body),patch.object(marketplace,'get_user_client',return_value=MagicMock()):
                self.identity(); _,status=marketplace.purchase.__wrapped__(EVENT); self.assertEqual(status,400)
    def test_inventory_service_lookup_cannot_mutate_foreign_campus(self):
        db=MagicMock()
        for fn in (kitchen.log_stock_purchase,kitchen.log_stock_usage):
            with self.app.test_request_context(method='POST',json={'quantity':1}),patch.object(kitchen,'get_db',return_value=db),patch.object(kitchen,'fetch_or_403',return_value=({'campus_id':B},None)):
                self.identity('admin')
                with self.assertRaises(Forbidden): fn.__wrapped__(TICKET)
                db.rpc.assert_not_called()
    def test_hostel_and_gate_money_is_finite_and_non_negative(self):
        for field in ('delivery_fee','base_fee','rate_per_km','min_fee'):
            for value in (-1,float('nan'),float('inf'),True):
                with self.assertRaises(ValueError): delivery._location_fields({field:value},(field,))
    def test_fresh_profile_role_wins_over_user_editable_auth_metadata(self):
        @require_role('admin')
        def protected(): return {'role': g.user_role}, 200
        self.app.add_url_rule('/protected', view_func=protected)
        for role in ('student','rider','kitchen','admin','super_admin'):
            db=DB({'profiles':[{'id':USER,'role':role,'is_active':True,'campus_id':A}]})
            db.auth_get_user=lambda token: {'id':USER,'user_metadata':{'role':'super_admin','campus_id':B}}
            with patch('app.middleware.auth.get_db',return_value=db):
                response=self.app.test_client().get('/protected',headers={'Authorization':'Bearer synthetic'})
                self.assertEqual(response.status_code,200 if role in ('admin','super_admin') else 403)
        db.rows['profiles'][0]['is_active']=False
        with patch('app.middleware.auth.get_db',return_value=db):
            self.assertEqual(self.app.test_client().get('/protected',headers={'Authorization':'Bearer synthetic'}).status_code,403)
        self.assertEqual(self.app.test_client().get('/protected').status_code,401)
    def test_signed_in_reference_lists_ignore_foreign_campus_query(self):
        for module, fn in ((departments,departments.list_departments),(academic_levels,academic_levels.list_academic_levels)):
            db=MagicMock()
            for name in ('select','eq','or_','order'):
                getattr(db.table.return_value,name).return_value=db.table.return_value
            db.table.return_value.execute.return_value=[]
            with self.app.test_request_context('/?campus_id='+B),patch.object(module,'get_user_client',return_value=db):
                self.identity()
                _,status=fn.__wrapped__()
                self.assertEqual(status,200)
                filters=str(db.table.return_value.method_calls)
                self.assertIn(A,filters)
                self.assertNotIn(B,filters)
