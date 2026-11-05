import copy
import unittest
from unittest.mock import MagicMock, patch
from flask import Flask, g
from app.services import gift_campaigns as service
from app.routes import admin_gifts
from tests.test_welcome_credit import DB, CAMPUS, OTHER
from tests.test_checkout_quote import Db as QuoteDB

CAMPAIGN='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
CONFIG={'id':CAMPAIGN,'name':'Launch gifts','enabled':True,'eligibility':'first_order',
        'starts_at':'2026-10-01T08:00:00+01:00','ends_at':'2026-11-01T22:00:00+01:00','validity_days':60,
        'benefits':[{'kind':'hp','amount':50},{'kind':'free_side','credits':2},
                    {'kind':'delivery_discount','percent':50,'cap':300},{'kind':'hp_multiplier','multiplier':2}]}


class GiftCampaignTests(unittest.TestCase):
    def test_preview_uses_verified_creation_time_and_existing_paid_history(self):
        db=QuoteDB(); config=service.validate_config(CONFIG)
        self.assertTrue(service.eligible_preview(db,'student',config,{}))
        db.rows['orders']=[{'id':'old','user_id':'student','created_at':'2026-09-01T00:00:00Z'}]
        self.assertFalse(service.eligible_preview(db,'student',config,{}))
        db.rows['orders'][0]['created_at']='2026-10-05T00:00:00Z'
        self.assertTrue(service.eligible_preview(db,'student',config,{}))
        db.rows['orders'].append({'id':'second','user_id':'student','created_at':'2026-10-06T00:00:00Z'})
        self.assertFalse(service.eligible_preview(db,'student',config,{}))
        config['eligibility']='signup'
        self.assertFalse(service.eligible_preview(db,'student',config,{'user_metadata':{'created_at':'2099-01-01T00:00:00Z'}}))
        self.assertTrue(service.eligible_preview(db,'student',config,{'created_at':'2026-10-05T00:00:00Z'}))

    def test_public_teaser_requires_campus_active_dates_and_appropriate_audience(self):
        from app.routes import storefront
        from datetime import datetime, timezone, timedelta
        now=datetime.now(timezone.utc)
        config=service.validate_config({**CONFIG,'starts_at':(now-timedelta(days=1)).isoformat(),'ends_at':(now+timedelta(days=1)).isoformat()})
        db=QuoteDB();db.rows['feature_flags']=[{'feature_name':'free_side_credits','is_active':True,'campus_id':None}]
        with Flask(__name__).test_request_context(),patch.object(service,'read_config',return_value=(config,None,False)) as read,patch.object(storefront,'get_db',return_value=db):
            g.user_id=None;g.user_role=None
            self.assertIsNone(storefront._active_gift_campaign(None));read.assert_not_called()
            self.assertEqual(storefront._active_gift_campaign(CAMPUS)['id'],CAMPAIGN)
            g.user_id='student';g.user_role='student'
            self.assertIsNone(storefront._active_gift_campaign(CAMPUS))
            config['eligibility']='everyone'
            self.assertEqual(storefront._active_gift_campaign(CAMPUS)['id'],CAMPAIGN)
            config['enabled']=False
            self.assertIsNone(storefront._active_gift_campaign(CAMPUS))
            config['enabled']=True;db.rows['feature_flags'][0]['is_active']=False
            self.assertIsNone(storefront._active_gift_campaign(CAMPUS))

    def call(self, db, body=None, role='admin', query=''):
        with Flask(__name__).test_request_context('/gift-campaign'+query,method='PATCH' if body is not None else 'GET',json=body), \
             patch.object(admin_gifts,'get_db',return_value=db),patch.object(admin_gifts,'get_user_client',return_value=db):
            g.user_id='actor';g.user_role=role;g.campus_id=CAMPUS
            return admin_gifts.gift_campaign_settings.__wrapped__()

    def test_bundle_is_canonical_and_labels_follow_values(self):
        result=service.validate_config(CONFIG)
        self.assertEqual(result['starts_at'],'2026-10-01T07:00:00+00:00')
        self.assertEqual(result['benefits'][0]['label'],'50 HP')
        self.assertIn('50%',result['benefits'][2]['label'])

    def test_invalid_types_duplicates_exclusive_spins_and_unknown_fields_fail(self):
        changes=[{'benefits':[]},{'benefits':[{'kind':'exclusive_spin'}]},
                 {'benefits':[{'kind':{}},{'kind':'hp','amount':50}]},
                 {'benefits':[{'kind':'hp','amount':True}]},{'benefits':[{'kind':'hp','amount':1.5}]},
                 {'benefits':[{'kind':'hp','amount':50},{'kind':'hp','amount':50}]},
                 {'benefits':[{'kind':'delivery_discount','percent':101,'cap':300}]},
                 {'benefits':[{'kind':'delivery_discount','percent':50,'cap':float('nan')}]},
                 {'benefits':[{'kind':'hp_multiplier','multiplier':1}]},
                 {'benefits':[{'kind':'free_side','credits':11}]},{'validity_days':True},
                 {'starts_at':'2026-10-01T08:00:00'},{'ends_at':'2026-09-01T00:00:00Z'},
                 {'id':'invalid'},{'enabled':'true'},{'unexpected':1}]
        for change in changes:
            with self.subTest(change=change),self.assertRaises(ValueError):
                service.validate_config({**CONFIG,**change})

    def test_campus_inherits_global_without_using_its_revision_for_override(self):
        db=DB([{'key':service.CONFIG_KEY,'campus_id':None,'value':CONFIG,'updated_at':'global-stamp'}])
        response,status=self.call(db)
        self.assertEqual(status,200);self.assertTrue(response.json['inherited']);self.assertIsNone(response.json['updated_at'])

    def test_admin_global_is_denied_and_foreign_campus_request_stays_own(self):
        db=DB()
        self.assertEqual(self.call(db,{'scope':'global','config':CONFIG})[1],403)
        response,status=self.call(db,{'campus_id':OTHER,'config':CONFIG,'expected_updated_at':None})
        self.assertEqual(status,200);self.assertEqual(db.rows[0]['campus_id'],CAMPUS)

    def test_super_admin_can_save_global_and_stale_editor_cannot_overwrite(self):
        db=DB()
        response,status=self.call(db,{'scope':'global','config':CONFIG,'expected_updated_at':None},role='super_admin')
        self.assertEqual(status,200);self.assertIsNone(db.rows[0]['campus_id'])
        original=copy.deepcopy(db.rows)
        _,status=self.call(db,{'scope':'global','config':{**CONFIG,'name':'Stale edit'},'expected_updated_at':'old'},role='super_admin')
        self.assertEqual(status,409);self.assertEqual(db.rows,original)

    def test_generic_settings_cannot_bypass_campaign_validation(self):
        for handler in (admin_gifts.update_setting,admin_gifts.create_setting):
            db=DB([{'key':service.CONFIG_KEY,'campus_id':CAMPUS,'value':copy.deepcopy(CONFIG)}])
            original=copy.deepcopy(db.rows)
            with Flask(__name__).test_request_context(method='PATCH',json={'key':service.CONFIG_KEY,'campus_id':CAMPUS,'value':{**CONFIG,'benefits':[]}}), \
                 patch.object(admin_gifts,'get_user_client',return_value=db):
                g.user_id='actor';g.user_role='admin';g.campus_id=CAMPUS
                result=handler.__wrapped__(service.CONFIG_KEY) if handler is admin_gifts.update_setting else handler.__wrapped__()
                self.assertEqual(result[1],400);self.assertEqual(db.rows,original)

    def test_claim_uses_server_user_and_replay_has_no_repeat_notification(self):
        db=MagicMock();db.rpc.return_value={'granted':False,'idempotent':True,'receipt_id':CAMPAIGN}
        with patch.object(service,'get_db',return_value=db),patch('app.services.notification_service.send_notification') as notify:
            result=service.claim('verified-user',CAMPAIGN)
        self.assertTrue(result['idempotent']);notify.assert_not_called()
        db.rpc.assert_called_once_with('hg_claim_gift_campaign_atomic',{'p_user_id':'verified-user','p_expected_campaign_id':CAMPAIGN})

    def test_committed_grant_is_not_lost_when_notification_dispatch_fails(self):
        db=MagicMock();db.rpc.return_value={'granted':True,'receipt_id':CAMPAIGN,'name':'Launch gifts'}
        with patch.object(service,'get_db',return_value=db),patch('app.services.notification_service.send_notification',side_effect=RuntimeError('offline')):
            self.assertTrue(service.claim('verified-user',CAMPAIGN)['granted'])
