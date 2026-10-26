"""Rich composer and audience contracts. External providers are recorders."""
import copy,unittest
from unittest.mock import patch,MagicMock
from flask import Flask,g
from app.routes import notifications
from app.services import notification_service as service
from app.db import SupabaseError, QueryResultList
A='bbbb0000-0000-4000-8000-000000000001';B='bbbb0000-0000-4000-8000-000000000002';USER='bbbb0000-0000-4000-8000-000000000003';OTHER='bbbb0000-0000-4000-8000-000000000004';INTENT='bbbb0000-0000-4000-8000-000000000005';IMAGE='https://res.cloudinary.com/test-cloud/image/upload/v1/blast.png'
class Query:
 def __init__(self,db,table):self.db=db;self.name=table;self.filters=[];self.start=0;self.size=10000;self.one=False;self.neg=False
 def select(self,*_):return self
 def value(self,row,key):
  if '->>' in key:
   a,b=key.split('->>');return (row.get(a) or {}).get(b)
  return row.get(key)
 def eq(self,k,v):self.filters.append(lambda r:self.value(r,k)==v);return self
 def in_(self,k,v):
  neg=self.neg;self.neg=False;self.filters.append(lambda r:(r.get(k) not in v) if neg else (r.get(k) in v));return self
 @property
 def not_(self):self.neg=True;return self
 def gte(self,k,v):self.filters.append(lambda r:str(r.get(k,''))>=v);return self
 def order(self,*_,**__):return self
 def limit(self,n):self.size=n;return self
 def offset(self,n):self.start=n;return self
 def single(self):self.one=True;return self
 def execute(self):
  rows=[copy.deepcopy(r) for r in self.db.rows.get(self.name,[]) if all(f(r) for f in self.filters)][self.start:self.start+self.size]
  return (rows[0] if rows else None) if self.one else rows
 def insert(self,payload):
  row=copy.deepcopy(payload)
  if row.get('id') and any(r.get('id')==row['id'] for r in self.db.rows.get(self.name,[])):raise SupabaseError('duplicate',409,{'code':'23505'})
  row.setdefault('id',INTENT);self.db.rows.setdefault(self.name,[]).append(row);self.db.writes.append((self.name,row));return QueryResultList([row])
 def update(self,patch):
  found=[]
  for row in self.db.rows.get(self.name,[]):
   if all(f(row) for f in self.filters):row.update(copy.deepcopy(patch));found.append(copy.deepcopy(row))
  return found
class DB:
 def __init__(self,rows=None):self.rows=rows or {};self.writes=[]
 def table(self,name):return Query(self,name)
class RichBlastContracts(unittest.TestCase):
 def setUp(self):self.app=Flask(__name__);self.app.config['CLOUDINARY_CLOUD_NAME']='test-cloud'
 def call(self,fn,db,body):
  with self.app.test_request_context(method='POST',json=body),patch.object(notifications,'get_user_client',return_value=db),patch.object(notifications,'resolve_write_campus',return_value=A),patch.object(notifications,'send_blast',return_value={'sent_to':1}):
   g.user_id=USER;g.user_role='admin';g.campus_id=A;return fn.__wrapped__()
 def payload(self):return {'title':'New meal','body':'Ready','channels':['in_app'],'request_id':INTENT,'body_html':'<p><strong>Fresh</strong></p>','images':[{'id':'image1','url':IMAGE,'alt':'Meal'}],'cta_blocks':[{'id':'cta1','label':'Menu','url':'/menu','style':'primary'}],'push_image':IMAGE,'segment':{'role':'student','has_active_order':True,'user_ids':[OTHER]}}
 def test_rich_fields_survive_insert_and_lost_response_replay(self):
  db=DB();body=self.payload();r,status=self.call(notifications.create_blast,db,body);self.assertEqual(status,201)
  for key in ('body_html','images','cta_blocks','push_image'):self.assertEqual(db.rows['notification_blasts'][0][key],body[key])
  r,status=self.call(notifications.create_blast,db,body);self.assertEqual(status,200);self.assertTrue(r.json['already_created']);self.assertEqual(len(db.rows['notification_blasts']),1)
 def test_html_only_editor_uses_sanitized_plain_push_body(self):
  body=self.payload();body['body']='';body['body_html']='<p>New <b>meal</b></p><script>leak()</script>';db=DB();r,status=self.call(notifications.create_blast,db,body);self.assertEqual(status,201);self.assertEqual(r.json['blast']['body'],'New meal');self.assertNotIn('leak',r.json['blast']['body_html'])
 def test_bad_images_destinations_and_audiences_fail_before_write(self):
  for change in ({'cta_blocks':[{'label':'Go','url':'javascript:alert(1)'}]},{'push_image':'https://attacker.invalid/a.png'},{'images':[{'url':IMAGE,'alt':{'bad':1}}]},{'segment':{'unsupported_broadening_key':True}},{'segment':{'has_cart':'false'}}):
   with self.subTest(change=change):
    db=DB();_,status=self.call(notifications.create_blast,db,{**self.payload(),**change});self.assertEqual(status,400);self.assertFalse(db.writes)
 def test_preview_rejects_foreign_scope(self):
  _,status=self.call(notifications.preview_blast,DB(),{'target_segment':{'campus_id':B}});self.assertEqual(status,403)
 def test_test_send_binds_verified_admin_only(self):
  db=DB({'profiles':[{'id':USER,'campus_id':A,'email':'admin@example.invalid'}]});body={**self.payload(),'test_email':'admin@example.invalid'};r,status=self.call(notifications.send_test_blast,db,body);self.assertEqual(status,200);self.assertEqual(db.rows['notification_blasts'][0]['segment'],{'user_ids':[USER]});_,status=self.call(notifications.send_test_blast,db,{**body,'test_email':'someone@example.invalid'});self.assertEqual(status,403)
 def test_cart_active_recent_and_specific_person_intersect(self):
  from datetime import datetime,timezone
  now=datetime.now(timezone.utc).isoformat();db=DB({'profiles':[{'id':uid,'role':'student','campus_id':campus,'is_active':True} for uid,campus in [(USER,A),(OTHER,A),(INTENT,B)]],'orders':[{'id':'o','user_id':USER,'status':'preparing','created_at':now}],'cart_items':[{'id':'c','user_id':USER}]});self.assertEqual(service.resolve_segment_user_ids({'has_cart':True,'has_active_order':True,'last_order_days':7,'user_ids':[USER,OTHER]},A,db),{USER});self.assertEqual(service.resolve_segment_user_ids({'has_cart':False},A,db),{OTHER})
 def test_2501_recipients_not_silently_limited(self):
  db=DB({'profiles':[{'id':str(i),'campus_id':A,'is_active':True} for i in range(2501)]});self.assertEqual(len(service.resolve_segment_user_ids({},A,db)),2501)
 def test_dispatch_preserves_rich_metadata_and_escapes_personalization(self):
  blast={**self.payload(),'id':INTENT,'status':'pending','campus_id':A,'metadata':{}};blast['body_html']='<p>Hi {name}</p>';db=DB({'notification_blasts':[blast],'notifications':[]})
  with self.app.app_context(),patch.object(service,'get_db',return_value=db),patch.object(service,'resolve_segment_user_ids',return_value={USER}),patch.object(service,'_fetch_user_name',return_value='<img>'),patch.object(service,'send_notification') as send,patch.object(service,'get_email_provider',return_value='onesignal'):
   result=service.send_blast(INTENT);self.assertEqual(result['sent_to'],1);self.assertEqual(send.call_args.kwargs['metadata']['push_image'],IMAGE);self.assertIn('&lt;img&gt;',send.call_args.kwargs['metadata']['body_html']);self.assertEqual(send.call_args.kwargs['email_provider'],'onesignal')
 def test_push_image_reaches_os_payload(self):
  with self.app.app_context(),patch.object(service,'_get_onesignal_creds',return_value=('app','key')),patch.object(service,'_onesignal_post',return_value=MagicMock(status_code=200)) as post:
   service._dispatch_push_async(USER,'Title','Body','/menu','receipt',push_image=IMAGE);payload=post.call_args.kwargs['payload'];self.assertEqual(payload['chrome_web_image'],IMAGE);self.assertEqual(payload['big_picture'],IMAGE);self.assertEqual(payload['url'],'/menu')
