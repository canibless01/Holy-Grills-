"""Selected campus identities must resolve privately before roster writes."""
import unittest
from unittest.mock import patch
from flask import Flask, g
from app.routes import squads

CAMPUS='bbbb0000-0000-4000-8000-000000000001'
OWNER='bbbb0000-0000-4000-8000-000000000002'
MEMBER='bbbb0000-0000-4000-8000-000000000003'
SQUAD='bbbb0000-0000-4000-8000-000000000004'
class Saved(list):
 def execute(self):return self
class Query:
 def __init__(self,db,table):self.db=db;self.table=table;self.filters=[];self.one=False
 def select(self,*_,**__):return self
 def eq(self,key,value):self.filters.append(lambda row:row.get(key)==value);return self
 def in_(self,key,values):self.filters.append(lambda row:row.get(key) in values);return self
 def single(self):self.one=True;return self
 def execute(self):
  rows=[row for row in self.db.rows.get(self.table,[]) if all(check(row) for check in self.filters)]
  return (rows[0] if rows else None) if self.one else rows
 def insert(self,payload):
  row={'id':SQUAD,**payload};self.db.writes.append((self.table,row));return Saved([row])
class DB:
 def __init__(self,rows):self.rows=rows;self.writes=[]
 def table(self,name):return Query(self,name)
class SquadIdentityPicker(unittest.TestCase):
 def setUp(self):
  self.app=Flask(__name__);self.public=DB({'squads':[{'id':SQUAD,'creator_id':OWNER,'campus_id':CAMPUS}]})
  self.private=DB({'profiles':[{'id':MEMBER,'email':'member@example.invalid','role':'student','campus_id':CAMPUS,'is_active':True}]})
 def call(self,body,create=False):
  with self.app.test_request_context(method='POST',json=body),patch.object(squads,'get_user_client',return_value=self.public),patch.object(squads,'get_db',return_value=self.private),patch.object(squads,'is_feature_enabled',return_value=True):
   g.user_id=OWNER;g.campus_id=CAMPUS;g.user_role='student'
   return squads.create_squad.__wrapped__() if create else squads.add_roster_member.__wrapped__(SQUAD)
 def test_selected_identity_resolves_email_without_public_profile_lookup(self):
  _,status=self.call({'user_id':MEMBER});self.assertEqual(status,201)
  table,row=self.public.writes[0];self.assertEqual(table,'squad_roster');self.assertEqual(row['user_id'],MEMBER);self.assertEqual(row['email'],'member@example.invalid')
 def test_foreign_inactive_staff_or_missing_identity_cannot_be_added(self):
  for change in ({'campus_id':'foreign'},{'is_active':False},{'role':'admin'},{'id':OWNER}):
   with self.subTest(change=change):
    self.private.rows['profiles'][0].update(change);_,status=self.call({'user_id':MEMBER});self.assertEqual(status,400);self.assertEqual(self.public.writes,[])
    self.setUp()
 def test_malformed_identity_or_email_rejected_before_write(self):
  for body in ({'user_id':'bad'},{'email':'not-an-email'},{'email':[]},{'user_id':OWNER}):
   with self.subTest(body=body):
    _,status=self.call(body);self.assertEqual(status,400);self.assertEqual(self.public.writes,[])
 def test_create_resolves_selected_id_and_preserves_privacy_contract(self):
  _,status=self.call({'name':'Crew','member_user_ids':[MEMBER]},create=True);self.assertEqual(status,201)
  self.assertEqual([table for table,_ in self.public.writes],['squads','squad_roster']);self.assertEqual(self.public.writes[1][1]['user_id'],MEMBER)
 def test_create_refuses_foreign_id_before_creating_squad(self):
  self.private.rows['profiles'][0]['campus_id']='foreign';_,status=self.call({'name':'Crew','member_user_ids':[MEMBER]},create=True)
  self.assertEqual(status,400);self.assertEqual(self.public.writes,[])
