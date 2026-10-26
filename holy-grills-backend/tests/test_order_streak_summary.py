"""Login and delivered-order streaks are independent and campus rewards are effective."""
import unittest
from datetime import date
from unittest.mock import MagicMock,patch
from app.services import streak_service as service

class OrderStreakSummaryTests(unittest.TestCase):
    def setUp(self):
        self.db=MagicMock();self.rows={
            'order_streaks':{'streak_weeks':3,'longest_streak':6,'last_order_week':'2026-44'},
            'login_streaks':{'streak_count':1,'consecutive_weeks':99},
            'order_streak_rewards':[{'weeks':3,'hp_awarded':100,'is_active':True,'campus_id':None},{'weeks':6,'hp_awarded':200,'is_active':True,'campus_id':None},{'weeks':12,'hp_awarded':350,'is_active':True,'campus_id':None}],
        }
        def table(name):
            q=MagicMock();q.select.return_value=q;q.eq.return_value=q;q.single.return_value=q;q.execute.side_effect=lambda:self.rows.get(name);return q
        self.db.table.side_effect=table
    def read(self):
        with patch.object(service,'today_wat',return_value=date(2026,10,26)):
            return service.get_order_streak('me','campus',self.db)
    def test_order_count_does_not_use_login_consecutive_weeks(self):
        with patch.object(service,'get_user_client',return_value=self.db),patch.object(service,'today_wat',return_value=date(2026,10,26)):
            result=service.get_streak('me','campus')
        self.assertEqual(result['consecutive_weeks'],99);self.assertEqual(result['order_streak']['streak_weeks'],3)
    def test_no_login_row_does_not_hide_order_streak(self):
        self.rows['login_streaks']=None
        with patch.object(service,'get_user_client',return_value=self.db),patch.object(service,'today_wat',return_value=date(2026,10,26)):
            self.assertEqual(service.get_streak('me','campus')['order_streak']['streak_weeks'],3)
    def test_saved_milestones_and_next_target(self):
        result=self.read();self.assertTrue(result['counted_this_week']);self.assertEqual(result['next_reward'],{'weeks':6,'hp_awarded':200});self.assertEqual(result['repeat_after_week'],12)
    def test_previous_week_stays_alive_while_current_week_is_open(self):
        self.rows['order_streaks']['last_order_week']='2026-43'
        self.assertEqual(self.read()['streak_weeks'],3);self.assertFalse(self.read()['counted_this_week'])
    def test_missed_week_resets_visible_count_but_preserves_personal_best(self):
        self.rows['order_streaks']['last_order_week']='2026-42'
        self.assertEqual(self.read()['streak_weeks'],0);self.assertEqual(self.read()['longest_streak'],6)
    def test_campus_override_and_disabled_override_are_not_global_rewards(self):
        self.rows['order_streak_rewards'] += [{'weeks':3,'hp_awarded':125,'is_active':True,'campus_id':'campus'},{'weeks':6,'hp_awarded':999,'is_active':False,'campus_id':'campus'},{'weeks':12,'hp_awarded':888,'is_active':True,'campus_id':'foreign'}]
        self.assertEqual(self.read()['rewards'],[{'weeks':3,'hp_awarded':125},{'weeks':12,'hp_awarded':350}])
    def test_order_read_failure_is_not_disguised_as_zero(self):
        base=self.db.table.side_effect
        self.db.table.side_effect=lambda name: (_ for _ in ()).throw(RuntimeError('offline')) if name=='order_streaks' else base(name)
        with patch.object(service,'get_user_client',return_value=self.db):self.assertIsNone(service.get_streak('me')['order_streak'])
    def test_year_boundary_uses_iso_year(self):
        self.rows['order_streaks']['last_order_week']='2025-52'
        with patch.object(service,'today_wat',return_value=date(2025,12,29)):
            self.assertEqual(service.get_order_streak('me',db=self.db)['streak_weeks'],3)
    def test_reads_never_award_hp(self):
        with patch.object(service,'_award_order_streak_hp',side_effect=AssertionError('GET must not award')):
            self.read()
    def test_award_uses_effective_campus_and_actual_multiplier_amount(self):
        with patch('app.services.hp_service.award_active_hp',return_value={'awarded':200,'replayed':False}) as award,patch('app.services.notification_service.send_notification') as notify:
            result=service._award_order_streak_hp(self.db,'me',3,'2026-44','campus')
        self.assertEqual(result,200);self.assertEqual(award.call_args.kwargs['campus_id'],'campus');self.assertEqual(notify.call_args.kwargs['template_data']['hp'],200)
    def test_replayed_award_does_not_send_another_reward_notification(self):
        with patch('app.services.hp_service.award_active_hp',return_value={'awarded':0,'replayed':True}),patch('app.services.notification_service.send_notification') as notify:
            self.assertEqual(service._award_order_streak_hp(self.db,'me',3,'2026-44','campus'),0)
        notify.assert_not_called()
