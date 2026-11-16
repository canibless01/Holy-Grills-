from flask import Flask,g
from unittest.mock import MagicMock,patch
import pytest
from app.routes import events,event_organizers
from app.db import SupabaseError
A='11111111-1111-4111-8111-111111111111';E='22222222-2222-4222-8222-222222222222'
app=Flask(__name__)
@pytest.mark.parametrize('body',[None,[],{}, {'minutes':True},{'minutes':1.5},{'minutes':-1},{'minutes':10081}])
def test_invalid_window_never_writes(body):
 with app.test_request_context(method='POST',json=body),patch.object(events,'get_db') as db:
  _,status=events.set_event_admission_window.__wrapped__(E)
 assert status==400;db.assert_not_called()
@pytest.mark.parametrize('minutes',[None,0,30,10080])
def test_window_binds_actor_and_accepts_optional_offset(minutes):
 db=MagicMock();db.rpc.return_value={'minutes':minutes}
 with app.test_request_context(method='POST',json={'minutes':minutes,'actor':E}),patch.object(events,'get_db',return_value=db):
  g.user_id=A;_,status=events.set_event_admission_window.__wrapped__(E)
 assert status==200;db.rpc.assert_called_once_with('hg_set_event_admission_window',{'p_actor':A,'p_event':E,'p_minutes':minutes})
def test_organizer_opening_error_is_actionable():
 with app.app_context():response,status=event_organizers._failure(SupabaseError('HG_ADMISSION_NOT_OPEN'))
 assert status==409 and response.get_json()['error']==events.MSG.EVENT_ADMISSION_NOT_OPEN
