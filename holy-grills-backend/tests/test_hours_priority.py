from flask import Flask
from app.utils.schedule import effective_windows_with_config
from tests.test_ordering_window_status import FakeDb,_window,CAMPUS


def test_weekly_admin_hours_control_checkout_fallback_and_campus_beats_global():
    with Flask(__name__).app_context():
        rows,source=effective_windows_with_config(FakeDb(),CAMPUS,'2026-10-28',2,operating_hours=[
            {'weekday':2,'campus_id':None,'open_time':'08:00','close_time':'16:00'},
            {'weekday':2,'campus_id':CAMPUS,'open_time':'10:00','close_time':'22:00'}])
    assert source=='operating_hours' and rows[0]['opens_at']=='10:00' and rows[0]['closes_at']=='22:00'


def test_date_override_beats_weekly_hours_but_explicit_date_window_wins():
    override={'date':'2026-10-28','campus_id':CAMPUS,'is_closed':True}
    db=FakeDb(overrides=[override])
    with Flask(__name__).app_context():
        rows,source=effective_windows_with_config(db,CAMPUS,'2026-10-28',2,operating_hours=[{'weekday':2,'campus_id':CAMPUS,'open_time':'10:00','close_time':'22:00'}])
        assert source=='override_closed' and rows[0]['is_closed']
        db.ordering_windows=[_window('special','12:00','14:00',date='2026-10-28')]
        rows,source=effective_windows_with_config(db,CAMPUS,'2026-10-28',2)
        assert source=='date' and rows[0]['opens_at']=='12:00'
