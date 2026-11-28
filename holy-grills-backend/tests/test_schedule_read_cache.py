from unittest.mock import MagicMock
from app.services.schedule_read_cache import ScheduleReadCache


def test_configuration_fetches_once_per_request_and_preserves_date_filters():
    db=MagicMock();query=db.table.return_value
    query.select.return_value=query;query.eq.return_value=query
    query.execute.return_value=[{'id':'weekday','campus_id':'campus','weekday':4,'date':None}, {'id':'dated','campus_id':'campus','date':'2026-10-30'}]
    cached=ScheduleReadCache(db,'campus')
    one=cached.table('ordering_windows').select('*').eq('date','2026-10-30').execute()
    assert [row['id'] for row in one]==['dated']
    one[0]['id']='changed-by-caller'
    assert cached.table('ordering_windows').select('*').eq('date','2026-10-30').execute()[0]['id']=='dated'
    assert cached.table('ordering_windows').eq('weekday',4).execute()[0]['id']=='weekday'
    assert query.execute.call_count==1
    assert cached.table('orders') is query  # live counts, never a cached snapshot
    other=ScheduleReadCache(db,'campus')
    other.table('ordering_windows')
    assert query.execute.call_count==2


def test_plain_status_read_also_reuses_its_schedule_snapshot():
    from flask import Flask
    from unittest.mock import MagicMock, patch
    from app.routes import orders
    db=MagicMock();snapshot=MagicMock()
    with Flask(__name__).test_request_context('/orders/delivery-windows/status'),patch.object(orders,'get_user_client',return_value=db),patch.object(orders,'get_db',return_value=db),patch('app.routes.events._get_campus_id',return_value='campus'),patch('app.services.schedule_read_cache.ScheduleReadCache',return_value=snapshot) as cache,patch('app.services.order_service.get_ordering_window_status',return_value={'is_open':True,'windows':[]}) as status:
        response,code=orders.delivery_windows_status()
    assert code==200 and response.json['is_open'] is True
    cache.assert_called_once_with(db,'campus')
    status.assert_called_once_with(snapshot,'campus')
