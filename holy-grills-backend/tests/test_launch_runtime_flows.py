"""Local doubles only: never run jobs against production."""
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch
from flask import Flask, g
from app.routes import admin, orders
from app.services import streak_service as streak
from app.services.notification_templates import render_notification_template
from app.tasks import scheduled
from app.tasks.celery_app import _worker_flask_app


def query_db(rows=None):
    q=MagicMock()
    for method in ('select','eq','in_','order','limit','offset','gte','lt','single'):
        getattr(q,method).return_value=q
    q.not_.in_.return_value=q
    q.execute.return_value=rows or []
    db=MagicMock();db.table.return_value=q
    return db,q


def test_order_lists_exclude_unpaid_attempts():
    for module,route in ((admin,admin.list_all_orders),(orders,orders.list_orders),(orders,orders.active_order)):
        db,q=query_db()
        with Flask(__name__).test_request_context(),patch.object(module,'get_user_client',return_value=db):
            g.user_role='admin';g.campus_id='campus';g.user_id='customer'
            _,status=route.__wrapped__()
        assert status==200
        assert any(c.args[0]=='payment_status' and 'pending' not in c.args[1] for c in q.in_.call_args_list)


def test_five_checkins_complete_week_but_four_reset_it():
    with patch.object(streak,'_award_login_streak_hp',return_value=25) as award:
        assert streak._evaluate_week(None,'user',date(2026,10,26),{str(i):'checked' for i in range(5)},1,0)==(True,2,1,25)
        assert award.call_args.kwargs['missed_days']==2
        award.reset_mock()
        assert streak._evaluate_week(None,'user',date(2026,10,26),{str(i):'checked' for i in range(4)},2,1)==(False,1,0,0)
        award.assert_not_called()


def test_only_valid_checkins_count():
    assert streak._effective_checkins({'0':'checked','1':'reclaimed','2':'fraud','7':'checked'})==2


def test_streak_copy_has_exact_week_and_misses():
    result=render_notification_template('streak_cycle_failed',{'missed_days':4,'week_start':'2026-10-26','name':'Alex'})
    assert '4 days' in result[1] and '2026-10-26' in result[1] and 'Up to 2' in result[1]
    result=render_notification_template('checkin_streak_week',{'missed_days':2,'week_start':'2026-10-26','week':1,'hp':25})
    assert '2 missed days' in result[1] and '25 pending' in result[1]


def test_skipped_week_does_not_reward_an_older_good_week():
    db,_=query_db()
    previous={'id':'streak','current_week_start':'2026-10-12','week_state':{str(i):'checked' for i in range(7)},'cycle_week_number':2}
    with patch('app.services.notification_service.send_notification') as notify:
        result=streak._process_login_streak_checkin(db,'user',previous,datetime(2026,11,4,tzinfo=timezone.utc),date(2026,11,4))
    assert result['previous_week_completed'] is False
    assert notify.call_args.kwargs['template_data']=={'missed_days':7,'week_start':'2026-10-26'}


def test_worker_reuses_application():
    _worker_flask_app.cache_clear()
    try:
        with patch('app.create_app',return_value=Flask(__name__)) as create:
            assert _worker_flask_app() is _worker_flask_app()
            create.assert_called_once()
    finally: _worker_flask_app.cache_clear()


def test_error_result_is_not_logged_as_success():
    with patch.object(scheduled,'_log_cron_execution') as log:
        @scheduled.with_cron_logging('example')
        def task(): return {'campus':{'error':'database unavailable'}}
        task()
    assert log.call_args.args==('example','failed')


def test_scheduled_scan_uses_today_and_durable_recipient_dedup():
    tables={name:query_db(rows)[1] for name,rows in {
        'campuses':[{'id':'campus'}],'orders':[{'id':'order'}],
        'profiles':[{'id':'already'},{'id':'new'}],
        'notifications':[{'reference_id':'order','user_id':'already'}]}.items()}
    db=MagicMock();db.rpc.return_value=True;db.table.side_effect=lambda name:tables[name]
    with patch.object(scheduled,'get_db',return_value=db),patch.object(scheduled,'today_wat',return_value=date(2026,11,4)),patch('app.services.notification_service.send_notification') as notify:
        result=scheduled.process_scheduled_orders.run()
    assert result['campus']['processed']==1
    notify.assert_called_once()
    assert notify.call_args.kwargs['user_id']=='new'
    assert notify.call_args.kwargs['reference_id']=='order'
    tables['orders'].gte.assert_called_once_with('scheduled_for','2026-11-04T00:00:00+01:00')
    tables['orders'].lt.assert_called_once_with('scheduled_for','2026-11-05T00:00:00+01:00')


def test_kitchen_range_is_bounded_and_defaults_to_today():
    from app.routes import kitchen
    for args,expected in (("?from_date=2026-11-02&to_date=2026-11-04",200),
                          ("?from_date=2026-11-05&to_date=2026-11-04",400),
                          ("?from_date=2026-01-01&to_date=2026-11-04",400),
                          ("?from_date=invalid",400)):
        db,q=query_db();q.or_.return_value=q;q.not_.is_.return_value=q
        with Flask(__name__).test_request_context(args),patch.object(kitchen,'get_user_client',return_value=db),patch.object(kitchen,'_resolve_kitchen_campus_id',return_value=('campus',None)):
            _,status=kitchen.live_queue.__wrapped__()
        assert status==expected
        if status==200:
            predicate=q.or_.call_args.args[0]
            assert '2026-11-02T00:00:00+01:00' in predicate
            assert '2026-11-05T00:00:00+01:00' in predicate


def test_admin_dashboard_counts_only_confirmed_payments():
    from app.routes import analytics
    db,q=query_db()
    with Flask(__name__).test_request_context(),patch.object(analytics,'get_user_client',return_value=db),patch.object(analytics,'_scoped_campus',return_value='campus'):
        _,status=analytics.dashboard_summary.__wrapped__()
    assert status==200
    q.in_.assert_any_call('payment_status',['paid','partially_refunded','refunded'])
