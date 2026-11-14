from flask import Flask,g
from unittest.mock import MagicMock,patch
import pytest
from app.routes import events
from app.db import SupabaseError
A='11111111-1111-4111-8111-111111111111';E='22222222-2222-4222-8222-222222222222';T='33333333-3333-4333-8333-333333333333';R='44444444-4444-4444-8444-444444444444'
app=Flask(__name__)
fn=events.resend_event_ticket.__wrapped__.__wrapped__
def db_ticket():
 db=MagicMock();q=db.table.return_value
 for name in ('select','eq','single'):getattr(q,name).return_value=q
 q.execute.return_value={'id':T,'event_id':E,'guest_email':'guest@example.invalid','user_id':None}
 db.rpc.return_value={'delivery_id':R,'state':'queued'};return db
@pytest.mark.parametrize('body',[None,[],{}, {'request_id':'not-uuid'}])
def test_resend_invalid_input_never_writes(body):
 with app.test_request_context(method='POST',json=body),patch.object(events,'get_db') as db:
  _,status=fn(E,T)
 assert status==400;db.assert_not_called()
def test_resend_canonical_actor_and_signed_proof():
 db=db_ticket()
 with app.test_request_context(method='POST',json={'request_id':R,'guest_email':'guest@example.invalid','access_token':'invalid','actor':T,'signed':True,'email':'attacker@example.invalid'}),patch.object(events,'get_db',return_value=db),patch('app.utils.event_ticket_access.valid_ticket_access',return_value=False),patch.object(events,'start_ticket_email_dispatch') as dispatch:
  g.user_id=A;response,status=fn(E,T)
 assert status==200 and response.headers['Cache-Control']=='private, no-store'
 args=db.rpc.call_args.args[1];assert args['p_actor']==A and args['p_signed'] is False and args['p_email']=='guest@example.invalid';dispatch.assert_called_once_with(R)
@pytest.mark.parametrize('message,status',[('HG_TICKET_RESEND_ACCESS',403),('HG_TICKET_RESEND_COOLDOWN',429),('HG_TICKET_RESEND_INVALID',409),('HG_TICKET_RESEND_CONFLICT',409)])
def test_resend_rejected_never_dispatches(message,status):
 db=db_ticket();db.rpc.side_effect=SupabaseError(message)
 with app.test_request_context(method='POST',json={'request_id':R}),patch.object(events,'get_db',return_value=db),patch('app.utils.event_ticket_access.valid_ticket_access',return_value=False),patch.object(events,'start_ticket_email_dispatch') as dispatch:
  _,actual=fn(E,T)
 assert actual==status;dispatch.assert_not_called()
