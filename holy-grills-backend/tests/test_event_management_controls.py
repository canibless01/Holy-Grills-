"""Event operations: authoritative paid metrics, local QR, scope and funding enum."""
import base64,io
from unittest.mock import MagicMock,patch
from flask import Flask,g
from PIL import Image
import pytest
from werkzeug.exceptions import Forbidden
from app.routes import events
A='11111111-1111-4111-8111-111111111111';B='22222222-2222-4222-8222-222222222222';E='33333333-3333-4333-8333-333333333333';T='44444444-4444-4444-8444-444444444444'
app=Flask(__name__)
def query(data):
 q=MagicMock()
 for name in ('select','eq','single','order','or_','limit','offset','in_'):getattr(q,name).return_value=q
 q.execute.return_value=data
 return q

def test_ticket_sales_use_recorded_cash_and_exclude_unpaid_cancelled_and_refunded():
 ev=query({'id':E,'campus_id':A,'capacity':10});tiers=query([{'id':T,'name':'Regular','price_naira':9999,'price_hp':500,'sold_count':6,'capacity':10}])
 tickets=query([
  {'id':'one','tier_id':T,'status':'confirmed','payment_status':'paid','wallet_amount_used':300.10,'card_amount_used':699.90,'hp_amount_paid':50},
  {'id':'two','tier_id':T,'status':'confirmed','payment_status':'not_required'},
  {'id':'three','tier_id':T,'status':'pending_payment','payment_status':'pending','card_amount_used':1000},
  {'id':'four','tier_id':T,'status':'cancelled','payment_status':'refunded','card_amount_used':1000},
  {'id':'five','tier_id':T,'status':'cancelled','payment_status':'refund_pending','card_amount_used':1000},
 ])
 db=MagicMock();db.table.side_effect=lambda name:{'events':ev,'event_ticket_tiers':tiers,'event_tickets':tickets}[name]
 with app.test_request_context(),patch.object(events,'get_user_client',return_value=db) as client:
  g.user_role='admin';g.campus_id=A
  response,status=events.event_ticket_sales.__wrapped__(E)
 assert status==200;client.assert_called_once_with(paginate=True)
 summary=response.json['summary'];assert summary=={'confirmed_count':2,'pending_count':1,'cancelled_count':2,'confirmed_cash':1000.0,'confirmed_hp':50,'capacity':10}
 assert response.json['tiers'][0]['confirmed_cash']==1000 and response.json['tiers'][0]['confirmed_count']==2

@pytest.mark.parametrize('role,campus,allowed',[('admin',A,True),('admin',B,False),('super_admin',B,True)])
def test_event_sales_scope(role,campus,allowed):
 db=MagicMock();db.table.return_value=query({'id':E,'campus_id':campus})
 with app.test_request_context(),patch.object(events,'get_user_client',return_value=db):
  g.user_role=role;g.campus_id=A
  if not allowed:
   with pytest.raises(Forbidden):events.event_ticket_sales.__wrapped__(E)
  else:
   # Empty tier/ticket reads after the event lookup.
   db.table.return_value.execute.side_effect=[{'id':E,'campus_id':campus},[],[]]
   assert events.event_ticket_sales.__wrapped__(E)[1]==200

def test_venue_qr_is_rendered_locally_and_token_saved_privately():
 db=MagicMock();db.table.return_value=query({'id':E,'campus_id':A,'title':'Controlled'})
 service=MagicMock()
 with app.test_request_context(),patch.object(events,'get_user_client',return_value=db),patch.object(events,'get_db',return_value=service):
  g.user_role='admin';g.campus_id=A
  response,status=events.generate_event_qr.__wrapped__(E)
 assert status==200;data=response.json;assert data['qr_payload']==f"hg-event:{E}:{data['qr_token']}"
 image=Image.open(io.BytesIO(base64.b64decode(data['qr_image'].split(',',1)[1])));assert image.format=='PNG' and image.width>=192 and image.width==image.height
 assert service.table.call_args.args[0]=='event_door_tokens' and service.table.return_value.upsert.call_args.args[0]['qr_token']==data['qr_token']

@pytest.mark.parametrize('funding,expected',[('host_funded','host_prepaid'),('host_prepaid','host_prepaid'),('hg_funded','hg_funded'),('invalid',None)])
def test_funding_creation_matches_database_enum_and_naive_dates_are_wat(funding,expected):
 db=MagicMock();q=db.table.return_value;q.insert.return_value.execute.return_value=[{'id':E}]
 body={'title':'Controlled event','location':'FUTA','starts_at':'2026-11-12T10:00','funding_source':funding,'is_published':False}
 with app.test_request_context(method='POST',json=body),patch.object(events,'get_user_client',return_value=db),patch.object(events,'resolve_write_campus',return_value=A):
  g.user_id=T;g.user_role='admin';g.campus_id=A
  response,status=events.create_event.__wrapped__()
 assert status==(201 if expected else 400)
 if expected:
  row=q.insert.call_args.args[0];assert row['funding_source']==expected and row['starts_at']=='2026-11-12T10:00:00+01:00' and row['is_published'] is False
 else:q.insert.assert_not_called()
