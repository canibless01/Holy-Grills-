from datetime import date
from unittest.mock import MagicMock, patch
from app.routes import kitchen
from flask import Flask


def test_queue_summary_and_bulk_actions_use_one_wat_preparation_date():
    query = MagicMock()
    query.in_.return_value = query
    query.not_.is_.return_value = query
    query.or_.return_value = query
    with patch.object(kitchen, 'today_wat', return_value=date(2026, 10, 30)):
        kitchen._today_preparation(query)
    predicate = query.or_.call_args.args[0]
    assert 'scheduled_for.gte.2026-10-30T00:00:00+01:00' in predicate
    assert 'scheduled_for.lt.2026-10-31T00:00:00+01:00' in predicate
    assert 'created_at.gte.2026-10-30T00:00:00+01:00' in predicate
    assert 'created_at.lt.2026-10-31T00:00:00+01:00' in predicate
    query.not_.is_.assert_called_once_with('delivery_window_id', 'null')


def test_kitchen_lists_only_todays_occurrence_even_after_delivery_ends():
    query = MagicMock()
    for method in ('select', 'eq', 'in_'):
        getattr(query, method).return_value = query
    query.not_.in_.return_value = query
    rows = [{'id': str(day), 'campus_id': 'campus', 'weekday': day,
             'opens_at': '19:30:00', 'closes_at': '20:30:00',
             'label': 'Daily delivery', 'status': 'open', 'is_active': True}
            for day in range(7)]
    query.execute.side_effect = [rows, []]
    db = MagicMock(); db.table.return_value = query
    with Flask(__name__).test_request_context(), patch.object(kitchen, 'today_wat', return_value=date(2026, 10, 30)), patch.object(kitchen, '_resolve_kitchen_campus_id', return_value=('campus', None)), patch.object(kitchen, 'get_user_client', return_value=db):
        response, status = kitchen.delivery_windows.__wrapped__()
    assert status == 200
    assert len(response.json) == 1
    assert response.json[0]['id'] == '4'
    assert response.json[0]['label'] == '2026-10-30 · Daily delivery'
