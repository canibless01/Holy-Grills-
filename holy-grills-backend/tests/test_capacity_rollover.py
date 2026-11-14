import unittest
from datetime import date
from unittest.mock import patch, MagicMock
from flask import Flask, g
from app.routes import admin, kitchen
from app.services import order_service
from tests.test_ordering_window_status import FakeDb, _window, _FrozenClock, _at, CAMPUS


class DailyCapDb(FakeDb):
    def rows_for(self, table, filters):
        if table == 'kitchen_settings': return [{'value': '1'}]
        return super().rows_for(table, filters)


class CapacityRolloverTests(unittest.TestCase):
    def test_daily_setting_increase_fills_earliest_dates_first(self):
        app=Flask(__name__); db=MagicMock(); settings=MagicMock(); windows=MagicMock()
        db.table.side_effect=lambda name: settings if name=='kitchen_settings' else windows
        settings.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value={'value':'20'}
        settings.upsert.return_value.execute.return_value=[{'value':'50'}]
        windows.select.return_value.eq.return_value.execute.return_value=[
            {'id':'tuesday','weekday':1,'opens_at':'08:00'}, {'id':'wednesday','weekday':2,'opens_at':'08:00'}]
        with app.test_request_context(method='PATCH',json={'settings':{'daily_order_capacity':'50'}}), \
             patch.object(kitchen,'_resolve_kitchen_campus_id',return_value=(CAMPUS,None)), \
             patch.object(kitchen,'get_user_client',return_value=db), \
             patch.object(kitchen,'today_wat',return_value=date(2026,10,27)), \
             patch.object(admin,'_move_up_deferred_orders',return_value=1) as move:
            g.user_id='actor'
            response,status=kitchen.update_kitchen_settings.__wrapped__()
            self.assertEqual(status,200)
            self.assertEqual(response.json['orders_moved_up'],4)
            self.assertEqual([call.kwargs['target_dates'][0].isoformat() for call in move.call_args_list],
                ['2026-10-27','2026-10-28','2026-11-03','2026-11-04'])

    def test_daily_cap_offers_next_day_even_when_ordering_window_has_room(self):
        db = DailyCapDb(ordering_windows=[_window('today', '08:00', '21:00', weekday=1, capacity=50),
              _window('tomorrow', '08:00', '21:00', weekday=2, capacity=50)],
              orders=[{'id':'occupied','created_at':'2026-10-06T10:00:00+01:00'}])
        _FrozenClock.fixed = _at(12)
        with patch.object(order_service, 'datetime', _FrozenClock):
            status = order_service.get_ordering_window_status(db, CAMPUS)
            self.assertEqual(status['reason'], 'full')
            with self.assertRaises(order_service.OrderingWindowUnavailable) as raised:
                order_service.resolve_ordering_window(db, CAMPUS)
            self.assertEqual(raised.exception.code, 'ORDERING_WINDOW_AT_CAPACITY')
            self.assertEqual(raised.exception.next_available_date, '2026-10-07')

    def test_booking_for_next_week_does_not_fill_todays_daily_cap(self):
        db = DailyCapDb(orders=[{'id':'future','is_scheduled':True,
             'created_at':'2026-10-06T10:00:00+01:00','scheduled_for':'2026-10-13T10:00:00+01:00'}])
        self.assertEqual(order_service._daily_capacity_remaining(db, CAMPUS, '2026-10-06'), 1)

    def test_increased_recurring_capacity_uses_service_rpc_and_notifies_both_actor_types(self):
        app=Flask(__name__); service=MagicMock(); user_db=MagicMock()
        receipt={'id':'order','originally_requested_date':'2026-10-26','target_date':'2026-10-27',
                 'deliv_start':'19:30','deliv_end':'20:30'}
        service.rpc.side_effect=[[{**receipt,'user_id':'owner'},{**receipt,'user_id':None,'guest_email':'audit@example.invalid'}], []]
        with app.test_request_context(), patch.object(admin,'today_wat',return_value=date(2026,10,27)), \
             patch.object(admin,'get_db',return_value=service),patch.object(admin,'send_notification') as notify, \
             patch('app.utils.schedule.effective_windows_with_config',return_value=([{'id':'window'}], 'recurring')), \
             patch('app.utils.email.send_email') as email:
            g.user_id='actor'
            moved=admin._move_up_deferred_orders(user_db,{'capacity':20},
                {'id':'window','capacity':50,'weekday':1,'campus_id':CAMPUS})
            self.assertEqual(moved,2)
            self.assertEqual(service.rpc.call_count,2)
            self.assertEqual(service.rpc.call_args_list[0].args[1]['p_target_date'],'2026-10-27')
            self.assertEqual(service.rpc.call_args_list[1].args[1]['p_target_date'],'2026-11-03')
            notify.assert_called_once(); email.assert_called_once()
            user_db.table.assert_not_called()

class TwoOrderCapacityTests(unittest.TestCase):
    def test_two_orders_fill_today_and_next_slot_is_tomorrow(self):
        class TwoCapDb(FakeDb):
            def rows_for(self, table, filters):
                if table=='kitchen_settings': return [{'value':'2'}]
                return super().rows_for(table,filters)
        db=TwoCapDb(ordering_windows=[_window('today','00:00','23:59',weekday=1,capacity=2),
            _window('tomorrow','00:00','23:59',weekday=2,capacity=2)],orders=[
            {'id':'first','created_at':'2026-10-06T10:00:00+01:00'},
            {'id':'second','created_at':'2026-10-06T11:00:00+01:00'}])
        _FrozenClock.fixed=_at(12)
        with patch.object(order_service,'datetime',_FrozenClock):
            self.assertEqual(order_service.get_ordering_window_status(db,CAMPUS)['reason'],'full')
            slot=order_service.find_next_available_ordering_slot(db,CAMPUS,date(2026,10,6))
            self.assertEqual(slot['date'],'2026-10-07')
            self.assertEqual(slot['window_id'],'tomorrow')
