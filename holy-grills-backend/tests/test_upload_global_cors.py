"""Cross-origin global uploads must pass the browser's actual preflight."""
from unittest.mock import MagicMock,patch
import pytest
from flask import g
from app import create_app
from app.config import Config
from app.routes import uploads
from app.middleware import auth

@pytest.fixture
def app():
 class TestConfig(Config):
  TESTING=True
  CLOUDINARY_CLOUD_NAME='test-cloud'
  CLOUDINARY_API_KEY='test-key'
  CLOUDINARY_API_SECRET='test-signing-value'
 return create_app(TestConfig)

@pytest.mark.parametrize('path',['/api/upload/signature','/api/events','/api/event-organizer/events'])
def test_global_scope_browser_preflight_allows_explicit_scope(app,path):
 response=app.test_client().options(path,headers={'Origin':'https://holygrills.online','Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'authorization,content-type,x-campus-scope'})
 assert response.status_code in (200,204)
 assert response.headers['Access-Control-Allow-Origin']=='https://holygrills.online'
 assert 'x-campus-scope' in response.headers['Access-Control-Allow-Headers'].lower()

def test_untrusted_origin_is_not_allowed(app):
 response=app.test_client().options('/api/upload/signature',headers={'Origin':'https://untrusted.invalid','Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'x-campus-scope'})
 assert 'Access-Control-Allow-Origin' not in response.headers

@pytest.mark.parametrize('campus',[None,'11111111-1111-4111-8111-111111111111'])
def test_real_authenticated_super_admin_can_sign_event_upload_without_campus(app,campus):
 db=MagicMock();db.auth_get_user.return_value={'id':'controlled'}
 db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value={'id':'controlled','role':'super_admin','is_active':True,'campus_id':campus}
 with patch.object(auth,'get_db',return_value=db):
  response=app.test_client().post('/api/upload/signature',json={'folder':'events'},headers={'Authorization':'Bearer controlled','X-Campus-Scope':'global','Origin':'https://holygrills.online'})
 assert response.status_code==200
 assert response.json['folder']=='events' and response.json['signature']
 assert 'secret' not in response.json
