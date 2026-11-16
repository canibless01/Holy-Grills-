from flask import Flask,g
from unittest.mock import MagicMock,patch
import pytest
from app.routes import events
from app.middleware import auth
A='11111111-1111-4111-8111-111111111111';E='22222222-2222-4222-8222-222222222222';T='33333333-3333-4333-8333-333333333333'
app=Flask(__name__);app.register_blueprint(events.events_bp,url_prefix='/api/events')
@pytest.mark.parametrize('body',[None,[],{}, {'amount':True,'reason':'Verified original promise'}, {'amount':1.5,'reason':'Verified original promise'}, {'amount':-1,'reason':'Verified original promise'}, {'amount':20001,'reason':'Verified original promise'}, {'amount':50,'reason':'short'}])
def test_invalid_review_never_reaches_ledger(body):
 with app.test_request_context(method='POST',json=body),patch.object(events,'get_db') as db:
  g.user_id=A
  response,status=events.review_guest_attendance_hp.__wrapped__(E,T)
 assert status==400;db.assert_not_called()
def test_review_actor_is_server_bound():
 db=MagicMock();db.rpc.return_value={'completed':True,'hp_added_to_active':50}
 with app.test_request_context(method='POST',json={'amount':50,'reason':'Verified original event promise','actor':T}),patch.object(events,'get_db',return_value=db):
  g.user_id=A;response,status=events.review_guest_attendance_hp.__wrapped__(E,T)
 assert status==200
 db.rpc.assert_called_once_with('hg_review_guest_attendance_hp',{'p_actor':A,'p_event':E,'p_ticket':T,'p_amount':50,'p_reason':'Verified original event promise'})
@pytest.mark.parametrize('role',['student','event_organizer','kitchen','rider','community_manager'])
def test_nonadmin_cannot_choose_attendance_hp(role):
 db=MagicMock();db.auth_get_user.return_value={'id':A};q=db.table.return_value
 for name in ('select','eq','single'):getattr(q,name).return_value=q
 q.execute.return_value={'id':A,'role':role,'campus_id':A,'is_active':True}
 with patch.object(auth,'get_db',return_value=db),patch.object(events,'get_db') as ledger:
  response=app.test_client().post(f'/api/events/{E}/tickets/{T}/attendance-hp',json={'amount':50,'reason':'Verified original event promise'},headers={'Authorization':'Bearer synthetic'})
 assert response.status_code==403;ledger.assert_not_called()
