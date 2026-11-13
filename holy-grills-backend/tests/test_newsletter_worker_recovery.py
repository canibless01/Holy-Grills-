from unittest.mock import MagicMock,patch
from flask import Flask
import pytest
from app.services import newsletter_service as service
from app.messages import MSG

@pytest.mark.parametrize('receipt',[{'state':'unknown'},{'state':'rejected','http_status':503},{'state':'quota','fallback':{'state':'unknown'}},{'state':'rejected','http_status':200}])
def test_ambiguous_provider_outcome_is_not_definite_failure(receipt):
 def send(*args,**kwargs):kwargs['receipt'].update(receipt);return False
 with patch('app.utils.email.send_email_routed',side_effect=send),pytest.raises(RuntimeError,match='unconfirmed'):
  service._default_sender('a@example.invalid','A','Subject','Body')
@pytest.mark.parametrize('receipt',[{'state':'rejected','http_status':400},{'state':'skipped'},{'state':'quota','fallback':{'state':'rejected','http_status':400}}])
def test_confirmed_refusal_does_not_become_uncertain(receipt):
 def send(*args,**kwargs):kwargs['receipt'].update(receipt);return False
 with patch('app.utils.email.send_email_routed',side_effect=send):assert service._default_sender('a@example.invalid','A','Subject','Body') is False

def test_preview_unknown_outcome_returns_failure_to_route():
 app=Flask(__name__);app.config.update(SECRET_KEY='controlled',FRONTEND_URL='https://holygrills.online')
 with app.app_context(),patch.object(service,'_compose',return_value=('Subject','Body',None)):
  assert service.send_test('a@example.invalid','A','Subject','Body',sender=MagicMock(side_effect=TimeoutError)) is False

def test_worker_never_inserts_unchecked_recipient_or_adds_read_modify_write_counters():
 db=MagicMock();q=db.table.return_value
 for name in ('select','eq','lt','in_','limit'):getattr(q,name).return_value=q
 q.execute.return_value=[];db.rpc.side_effect=[None,{'done':True}]
 app=Flask(__name__);app.config['FRONTEND_URL']='https://holygrills.online'
 with app.app_context(),patch.object(service,'_audience_page',side_effect=[[{'id':'s','email':'a@example.invalid'}],[]]),patch.object(service,'_compose',return_value=('Subject','Body',None)):
  sender=MagicMock();out=service._process_one(db,{'id':'c','status':'sending','subject':'Subject','body':'Body'},float('inf'),sender)
 assert out['done'];sender.assert_not_called();q.insert.assert_not_called();db.rpc.assert_any_call('hg_claim_newsletter_delivery',{'p_campaign':'c','p_subscription':'s','p_email':'a@example.invalid'});db.rpc.assert_any_call('hg_refresh_newsletter_summary',{'p_campaign':'c','p_uncertain_notice':MSG.NEWSLETTER_SEND_UNCERTAIN})


def test_actual_newsletter_artwork_escapes_body_and_preserves_paragraphs_and_unsubscribe():
 import os
 from urllib.parse import urlparse,parse_qs
 app=Flask(__name__);app.config.update(SECRET_KEY='controlled',FRONTEND_URL='https://holygrills.online',APP_NAME='Holy Grills')
 with app.app_context(),patch.dict(os.environ,{'API_PUBLIC_URL':''}):
  subject,html,headers=service._compose(' Guest@Example.invalid ','Guest',' Subject\nline ','First paragraph\n\n<script>bad()</script>','Holy Grills','')
  assert subject=='Subject line' and '<script>bad()</script>' not in html and '&lt;script&gt;' in html and '<br><br>' in html and 'newsletter/unsubscribe?token=' in html and headers is None
  token=service.make_unsubscribe_token(' Guest@Example.invalid ');assert service.read_unsubscribe_token(token)=='guest@example.invalid';assert service.read_unsubscribe_token('tampered'+token) is None
  app.config['SECRET_KEY']='different-key';assert service.read_unsubscribe_token(token) is None
