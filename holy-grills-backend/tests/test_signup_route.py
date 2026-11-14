"""Exercise the real registration route before provider account creation."""
from unittest.mock import MagicMock, patch
from flask import Flask
import pytest
from app.routes import auth
from app.messages import MSG
from app.db import SupabaseError

CAMPUS = '11111111-1111-4111-8111-111111111111'
VALID = dict(email='audit@example.invalid', password='LongPassword!1', full_name='Audit',
             phone='+2348012345678', date_of_birth='2000-01-01', department='Engineering',
             academic_level='100L', campus_id=CAMPUS)

@pytest.mark.parametrize('field,message', [('phone',MSG.REGISTER_PHONE_REQUIRED),
    ('date_of_birth',MSG.REGISTER_DOB_REQUIRED),('department',MSG.REGISTER_DEPARTMENT_REQUIRED),
    ('academic_level',MSG.REGISTER_LEVEL_REQUIRED)])
def test_missing_field_names_action_before_remote_call(field,message):
    with Flask(__name__).test_request_context(method='POST',json={**VALID,field:''}), \
         patch.object(auth,'get_db') as db,patch.object(auth.auth_service,'register') as create:
        response,status=auth.register.__wrapped__()
        assert status==400 and response.json=={'error':message,'field':field}
        db.assert_not_called();create.assert_not_called()

@pytest.mark.parametrize('consent',[False,True])
def test_valid_registration_reaches_service_without_local_import_crash(consent):
    db=MagicMock();db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value={'id':CAMPUS}
    with Flask(__name__).test_request_context(method='POST',json={**VALID,'promotional_emails':consent}), \
         patch.object(auth,'get_db',return_value=db), \
         patch.object(auth.auth_service,'register',return_value={}) as create:
        response,status=auth.register.__wrapped__()
        assert status==200
        assert create.call_args.kwargs['promotional_emails'] is consent


def test_reference_outage_is_actionable_and_never_creates_account():
    db=MagicMock();db.table.side_effect=SupabaseError('unavailable',503,{})
    with Flask(__name__).test_request_context(method='POST',json=VALID),patch.object(auth,'get_db',return_value=db),patch.object(auth.auth_service,'register') as create:
        response,status=auth.register.__wrapped__()
        assert status==503 and response.json['error']==MSG.REFERENCE_DATA_UNAVAILABLE
        create.assert_not_called()


def test_consent_requires_boolean():
    with Flask(__name__).test_request_context(method='POST',json={**VALID,'promotional_emails':'false'}),patch.object(auth.auth_service,'register') as create:
        _,status=auth.register.__wrapped__()
        assert status==400;create.assert_not_called()


def test_autoconfirm_signup_returns_only_real_issued_session():
    db=MagicMock()
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value={'id':CAMPUS}
    result={'user':{'id':'new-owner'},'access_token':'issued-access','refresh_token':'issued-refresh'}
    with Flask(__name__).test_request_context(method='POST',json=VALID), patch.object(auth,'get_db',return_value=db), patch.object(auth.auth_service,'register',return_value=result), patch.object(auth,'_notify_security') as notify:
        response,status=auth.register.__wrapped__()
    assert status==201 and response.json['access_token']=='issued-access'
    assert response.json['refresh_token']=='issued-refresh'
    assert notify.call_args.kwargs['template_data']['welcome_hp']=='0'


def test_duplicate_stays_ambiguous_and_never_gets_a_session():
    db=MagicMock()
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value={'id':CAMPUS}
    with Flask(__name__).test_request_context(method='POST',json=VALID), patch.object(auth,'get_db',return_value=db), patch.object(auth.auth_service,'register',side_effect=ValueError(MSG.REGISTER_EMAIL_AMBIGUOUS)):
        response,status=auth.register.__wrapped__()
    assert status==200 and response.json['status']=='check_email'
    assert 'access_token' not in response.json
