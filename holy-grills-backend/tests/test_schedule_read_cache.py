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
