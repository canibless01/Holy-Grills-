"""Actual ticket QR generation, exact payload and server-side ownership gates."""
import base64,io
from unittest.mock import MagicMock,patch
import pytest,qrcode
from PIL import Image
from flask import Flask,g
from app.routes import events
E='11111111-1111-4111-8111-111111111111';T='22222222-2222-4222-8222-222222222222';U='33333333-3333-4333-8333-333333333333'
app=Flask(__name__)
TICKET={'id':T,'event_id':E,'user_id':U,'status':'confirmed','payment_status':'paid'}
EVENT={'metadata':{},'ends_at':'2027-12-01T10:00:00+00:00'}

def call(ticket=None,event=None,actor=U,body=None):
 db=MagicMock();q=db.table.return_value
 for method in ('select','eq','single'):getattr(q,method).return_value=q
 q.execute.side_effect=[TICKET if ticket is None else ticket,EVENT if event is None else event]
 with app.test_request_context(method='POST',json={} if body is None else body),patch.object(events,'get_db',return_value=db):
  g.user_id=actor
  response,status=events.ticket_qr_image.__wrapped__.__wrapped__(E,T)
 return response,status,db

def test_owner_receives_real_private_png_for_ticket_based_payload():
 with patch('qrcode.make',wraps=qrcode.make) as make:
  response,status,_=call()
 assert status==200 and response.headers['Cache-Control']=='private, no-store'
 assert response.json['qr_payload']==f'hg-event:{E}:{T}'
 make.assert_called_once_with(f'hg-event:{E}:{T}')
 image=Image.open(io.BytesIO(base64.b64decode(response.json['qr_image'].split(',')[1])))
 assert image.format=='PNG' and image.width>=200

@pytest.mark.parametrize('actor',[None,E])
def test_other_accounts_and_anonymous_requests_cannot_read_member_ticket(actor):
 with patch('qrcode.make') as make:response,status,db=call(actor=actor,body={'user_id':U,'guest_email':'forged@example.invalid'})
 assert status==403 and 'qr_image' not in response.json;make.assert_not_called()
 assert db.table.call_count==1

def test_guest_requires_original_email_and_exact_ticket_identity():
 response,status,_=call(ticket={**TICKET,'user_id':None,'guest_email':'Guest@Example.invalid'},actor=None,body={'guest_email':' guest@example.invalid '})
 assert status==200 and response.json['qr_payload']==f'hg-event:{E}:{T}'

@pytest.mark.parametrize('body',[{}, {'guest_email':'wrong@example.invalid'},{'guest_email':123}])
def test_guest_email_is_not_optional_or_an_owner_override(body):
 response,status,_=call(ticket={**TICKET,'user_id':None,'guest_email':'guest@example.invalid'},actor=None,body=body)
 assert status==403 and 'qr_image' not in response.json

@pytest.mark.parametrize('ticket,event',[
 ({**TICKET,'status':'pending_payment','payment_status':'pending'},EVENT),
 ({**TICKET,'status':'cancelled','payment_status':'refunded'},EVENT),
 (TICKET,{'metadata':{'lifecycle_status':'cancelled'},'ends_at':EVENT['ends_at']}),
 (TICKET,{'metadata':{},'ends_at':'2000-01-01T10:00:00Z'}),
 ({**TICKET,'qr_expires_at':'2000-01-01T10:00:00Z'},EVENT),
])
def test_ineligible_ticket_never_gets_an_entry_qr(ticket,event):
 with patch('qrcode.make') as make:response,status,_=call(ticket=ticket,event=event)
 assert status==409 and 'qr_image' not in response.json;make.assert_not_called()
