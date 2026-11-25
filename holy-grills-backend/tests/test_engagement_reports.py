import unittest
from datetime import date
from unittest.mock import MagicMock
from flask import Flask
from app.services.hp_reporting import period_totals
from app.services.ambassador_reports import insights,weekly,week_start
from app.services.ambassador_service import AmbassadorError

class HpFlowTests(unittest.TestCase):
    def test_pending_and_revoked_awards_do_not_inflate_active_earnings(self):
        report=period_totals([{'type':'earn','source':'signup','status':'active','amount':50},{'type':'earn','source':'review','status':'pending','amount':20},{'type':'earn','source':'order','status':'revoked','amount':30}])
        self.assertEqual(report['hp_earned_active'],50);self.assertEqual(report['hp_pending'],20)
    def test_transfers_remain_separate_from_awards_and_redemptions(self):
        report=period_totals([{'type':'earn','source':'hp_transfer_received','status':'active','amount':40},{'type':'spend','source':'hp_transfer_sent','status':'active','amount':10},{'type':'spend','source':'meal','status':'active','amount':15}])
        self.assertEqual(report['hp_earned_active'],0);self.assertEqual(report['hp_spent'],15);self.assertEqual(report['hp_transfer_received'],40);self.assertEqual(report['hp_transfer_sent'],10)
    def test_expiry_is_a_separate_flow(self):
        self.assertEqual(period_totals([{'type':'expire','amount':5}])['hp_expired'],5)

class AmbassadorReportTests(unittest.TestCase):
    def setUp(self):self.app=Flask(__name__);self.app.config['FRONTEND_URL']='https://example.test'
    def test_week_normalisation_and_invalid_dates(self):
        self.assertEqual(week_start('2026-11-25'),date(2026,11,23))
        with self.assertRaises(AmbassadorError):week_start('not-a-date')
    def test_roster_uses_one_actor_and_campus_scoped_rpc(self):
        db=MagicMock();db.rpc.return_value={'ambassadors':[{'profile':{'referral_code':'A&B'}}]}
        with self.app.app_context():result=insights(db,'actor','campus','2026-11','2026-11-25')
        db.rpc.assert_called_once_with('hg_ambassador_insights',{'p_actor':'actor','p_scope':'campus','p_month':'2026-11','p_week':'2026-11-23','p_only':None})
        self.assertEqual(result['ambassadors'][0]['tracking_link'],'https://example.test/register?ref=A%26B')
    def test_self_reports_bind_the_caller(self):
        db=MagicMock();db.rpc.return_value={'ambassadors':[]}
        with self.app.app_context():insights(db,'actor','campus','2026-11','2026-11-25',only='actor')
        self.assertEqual(db.rpc.call_args.args[1]['p_only'],'actor')
    def test_denied_scope_is_not_a_successful_empty_report(self):
        db=MagicMock();db.rpc.return_value={'error':'forbidden'}
        with self.app.app_context(),self.assertRaises(AmbassadorError) as error:insights(db,'actor','foreign','2026-11')
        self.assertEqual(error.exception.status,403)
    def test_shareable_report_does_not_expose_contact_details(self):
        db=MagicMock();db.rpc.return_value={'week_start':'2026-11-23','week_end':'2026-11-29','as_of':'now','order_basis':'paid delivered','share_basis':'manual','ambassadors':[{'ambassador':{'profile_id':'amb'},'profile':{'nickname':'Nick','phone':'private','referral_code':'REF'},'week':{'signups':1,'orders':2,'retained_order_value':5000,'assigned_count':4,'shared_count':3}}]}
        with self.app.app_context():report=weekly(db,'actor','campus','2026-11-25')
        self.assertIn('Nick',report['share_text']);self.assertNotIn('private',str(report));self.assertEqual(report['totals']['orders'],2)
