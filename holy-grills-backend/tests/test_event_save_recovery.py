"""A lost create response must not create another event on retry."""
from unittest.mock import MagicMock, patch
from flask import Flask, g
from app.routes import events
from app.messages import MSG
import pytest

app = Flask(__name__)
A='11111111-1111-4111-8111-111111111111'
R='22222222-2222-4222-8222-222222222222'
BODY={'request_id':R,'title':'Launch night','description':'First paragraph\n\nSecond paragraph','location':'FUTA','starts_at':'2026-12-01T18:00','capacity':200}

class Query:
 def __init__(self): self.rows=[];self.action='select';self.value=None
 def select(self,*a): self.action='select';return self
 def eq(self,*a): return self
 def single(self): return self
 def insert(self,value): self.action='insert';self.value=value;return self
 def execute(self):
  if self.action=='insert':
   self.rows.append(dict(self.value))
   raise TimeoutError('response lost after commit')
  return self.rows[0] if self.rows else None

def call(db, body):
 with app.test_request_context(method='POST',json=body),patch.object(events,'get_user_client',return_value=db),patch.object(events,'resolve_write_campus',return_value=A):
  g.user_id=A;g.user_role='admin';g.campus_id=A
  return events.create_event.__wrapped__()

def test_timeout_retry_reuses_exact_row_and_preserves_paragraphs():
 q=Query();db=MagicMock();db.table.return_value=q
 with pytest.raises(TimeoutError):call(db,BODY)
 response,status=call(db,BODY)
 assert status==200 and response.json['id']==R and len(q.rows)==1
 assert response.json['description']==BODY['description']
 response,status=call(db,{**BODY,'capacity':300})
 assert status==409 and response.json['error']==MSG.EVENT_SAVE_CONFLICT and len(q.rows)==1

def test_other_actor_cannot_replay_or_read_event():
 q=Query();db=MagicMock();db.table.return_value=q
 with pytest.raises(TimeoutError):call(db,BODY)
 q.rows[0]['organizer_id']=R
 response,status=call(db,BODY)
 assert status==409 and 'title' not in response.json

@pytest.mark.parametrize('value',['invalid',123,{},[]])
def test_invalid_request_id_cannot_write(value):
 db=MagicMock()
 response,status=call(db,{**BODY,'request_id':value})
 assert status==400;db.table.return_value.insert.assert_not_called()
