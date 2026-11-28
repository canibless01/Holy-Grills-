import unittest
from unittest.mock import MagicMock,patch
from app.services import engagement_reporting as service
from app.services import streak_service
A='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';U='11111111-1111-4111-8111-111111111111';V='22222222-2222-4222-8222-222222222222'
class EngagementActivityTests(unittest.TestCase):
    def test_page_identity_comes_from_verified_caller_not_body(self):
        db=MagicMock();body={'id':U,'visitor_id':V,'campus_id':A,'path':'/menu','user_id':'spoofed'}
        service.record_page(db,body,user_id=U)
        self.assertEqual(db.rpc.call_args.args[1]['p_user'],U)
        self.assertNotIn('user_id',db.rpc.call_args.args[1])
    def test_anonymous_page_has_no_invented_account(self):
        db=MagicMock();service.record_page(db,{'id':U,'visitor_id':V,'campus_id':A,'path':'/'})
        self.assertIsNone(db.rpc.call_args.args[1]['p_user'])
    def test_raw_urls_query_tokens_and_unknown_paths_never_reach_database(self):
        for path in ['/menu?claim=secret','/orders/private-id','https://example.test','/admin','/kitchen','/api/paystack']:
            db=MagicMock();self.assertEqual(service.record_page(db,{'id':U,'visitor_id':V,'campus_id':A,'path':path}),{'error':'invalid'});db.rpc.assert_not_called()
    def test_malformed_event_does_not_reach_database(self):
        db=MagicMock();self.assertEqual(service.record_page(db,{'id':'bad'}),{'error':'invalid'});db.rpc.assert_not_called()
    def test_admin_report_passes_actor_scope_and_half_open_bounds(self):
        db=MagicMock();service.report(db,U,A,'start','end')
        db.rpc.assert_called_once_with('hg_engagement_report',{'p_actor':U,'p_scope':A,'p_start':'start','p_end':'end'})
    def test_operations_report_includes_counts_and_current_hp_sources(self):
        db=MagicMock();db.rpc.return_value={'active_users':3,'visitors':4,'page_views':10,'funnel':{'menu_visitors':4,'checkout_after_menu':2,'paid_linked_accounts':1},'streaks':{'qualified_weeks':2,'failed_weeks':1},'hp':{'active':50,'pending':20,'difference':0,'sources':[{'source':'welcome','active':50,'pending':0}]}}
        lines=service.operations_lines(db,{'campus_id':A,'payload':{'period_start':'start','period_end':'end'}})
        text='\n'.join(lines);self.assertIn('3',text);self.assertIn('50 active',text);self.assertIn('welcome',text)
        self.assertTrue(db.rpc.call_args.args[1]['p_include_hp'])
    def test_analytics_failure_does_not_prevent_core_operations_report(self):
        db=MagicMock();db.rpc.side_effect=RuntimeError('offline')
        self.assertIn('temporarily unavailable',service.operations_lines(db,{'campus_id':A,'payload':{'period_start':'start','period_end':'end'}})[0])
    def test_login_activity_reuses_one_existing_profile_write(self):
        from datetime import datetime,timezone
        db=MagicMock();q=db.table.return_value;q.eq.return_value=q
        now=datetime.now(timezone.utc);streak_service._touch_last_activity(db,U,now)
        q.update.assert_called_once_with({'last_activity_at':now.isoformat(),'last_seen_at':now.isoformat()})
