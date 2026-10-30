"""Guest contact email must never establish account ownership or HP entitlement."""
import unittest
from unittest.mock import patch
from flask import Flask, g
from app.routes import events
from app.db import QueryResultList
from tests.test_platform_boundaries import DB, A, B, USER, EVENT, TICKET
class ServiceDB(DB):
 def table(self, name):
  query=super().table(name)
  insert=query.insert
  query.insert=lambda payload:QueryResultList(insert(payload))
  return query
class EventGuestOwnershipTests(unittest.TestCase):
 def setUp(self):
  release=patch.object(events,'is_feature_enabled',return_value=True);release.start();self.addCleanup(release.stop)
  self.app=Flask(__name__)
  self.event={'id':EVENT,'campus_id':A,'is_published':True,'hp_per_attendee':50}
  self.ticket={'id':TICKET,'event_id':EVENT,'user_id':None,'is_guest':True,'guest_email':'owned@example.invalid','status':'confirmed','payment_status':'not_required'}
 def test_matching_contact_email_does_not_link_or_credit_account(self):
  public=DB({'events':[self.event],'profiles':[{'id':USER,'email':'owned@example.invalid'}]})
  service=ServiceDB({'event_tickets':[self.ticket],'event_door_tokens':[{'event_id':EVENT,'qr_token':'door'}]})
  with self.app.test_request_context(method='POST',json={'qr_token':'door','ticket_id':TICKET}),patch.object(events,'get_user_client',return_value=public),patch.object(events,'get_db',return_value=service),patch.object(events,'award_active_hp') as award:
   g.user_id=None;g.user_role=None;g.campus_id=A
   response,status=events.checkin.__wrapped__(EVENT)
   self.assertEqual(status,200);self.assertEqual(response.json['hp_added_to_pending'],0);award.assert_not_called()
   self.assertEqual([table for table,_ in service.writes],['event_checkins'])
 def test_guest_duplicate_is_found_even_when_public_reads_hide_admission(self):
  public=DB({'events':[self.event]})
  original=public.table
  def scoped(name):
   if name=='event_checkins':raise AssertionError('Admission recovery must use validated service lookup')
   return original(name)
  public.table=scoped
  service=ServiceDB({'event_tickets':[self.ticket],'event_door_tokens':[{'event_id':EVENT,'qr_token':'door'}],'event_checkins':[{'id':B,'ticket_id':TICKET}]})
  with self.app.test_request_context(method='POST',json={'qr_token':'door','ticket_id':TICKET}),patch.object(events,'get_user_client',return_value=public),patch.object(events,'get_db',return_value=service),patch.object(events,'award_active_hp') as award:
   g.user_id=None;g.user_role=None;g.campus_id=A
   self.assertEqual(events.checkin.__wrapped__(EVENT)[1],400);self.assertEqual(service.writes,[]);award.assert_not_called()
