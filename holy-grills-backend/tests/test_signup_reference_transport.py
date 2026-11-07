"""Exercise the real query client, including filter-before-update semantics."""
from unittest.mock import Mock, patch
import pytest
from flask import Flask, g
from app.db import SupabaseClient
from app.services.ambassador_service import set_assignment_status, AmbassadorError
from app.utils.reference_data import resolve_department, resolve_level

CAMPUS = '70000001-cafe-cafe-cafe-000000000001'

def client_with_rows(*rows):
    db = SupabaseClient('https://example.invalid', 'service', 'anon')
    def response(data):
        r = Mock(status_code=200, content=b'json', headers={})
        r.json.return_value = data
        return r
    db._session = Mock()
    db._session.get.side_effect = [response(row) for row in rows]
    db._session.patch.return_value = response([{'id':'assignment', 'status':'seen'}])
    return db

@pytest.mark.parametrize('value', ['Medicine and Surgery (MBBS)', 'Name, with comma', 'A "quoted" name', 'A=B'])
def test_scalar_filters_preserve_literal_names(value):
    db = client_with_rows([])
    db.table('departments').eq('name', value).execute()
    assert db._session.get.call_args.kwargs['params']['name'] == 'eq.' + value
    assert db.table('departments').in_('name', [value])._build_params()['name'].startswith('in.(')
    if any(c in value for c in ',()"'):
        assert db.table('departments').in_('name', [value])._build_params()['name'].startswith('in.("')


def test_registration_resolvers_use_selected_ids_and_active_campus_scope():
    db = client_with_rows([{'id':'department','name':'Medicine and Surgery (MBBS)'}], [{'id':'level','value':'300'}])
    assert resolve_department(db, 'old label', CAMPUS, row_id='department')['name'].endswith('(MBBS)')
    assert resolve_level(db, 'old label', CAMPUS, row_id='level')['value'] == '300'
    for call, row_id in zip(db._session.get.call_args_list, ['department','level']):
        params = call.kwargs['params']
        assert params['id'] == 'eq.' + row_id
        assert params['is_active'] == 'eq.true'
        assert CAMPUS in str(params['or']) and 'campus_id.is.null' in str(params['or'])

@pytest.mark.parametrize('role', ['community_manager','admin','super_admin'])
def test_seen_status_updates_through_real_transport(role):
    db=client_with_rows({'id':'assignment','ambassador_id':'student'}, {'profile_id':'student','campus_id':CAMPUS})
    with Flask(__name__).test_request_context(), patch('app.services.ambassador_service.audit'):
        g.user_role=role; g.campus_id=CAMPUS
        result=set_assignment_status(db,'actor','assignment','seen',None)
    assert result['status']=='seen'
    assert db._session.patch.call_args.kwargs['params'] == {'id':'eq.assignment'}
    assert db._session.patch.call_args.kwargs['json']['updated_by']=='actor'


def test_foreign_campus_cannot_mark_seen():
    db=client_with_rows({'id':'assignment','ambassador_id':'student'}, {'profile_id':'student','campus_id':'other'})
    with Flask(__name__).test_request_context(), patch('app.services.ambassador_service.audit'):
        g.user_role='community_manager'; g.campus_id=CAMPUS
        with pytest.raises(AmbassadorError): set_assignment_status(db,'actor','assignment','seen',None)
    db._session.patch.assert_not_called()


def test_registration_options_one_rpc_and_no_auth_dependency():
    from app.routes.auth import auth_bp
    app=Flask(__name__);app.register_blueprint(auth_bp,url_prefix='/api/auth')
    db=Mock();snapshot={'campus_id':CAMPUS,'campuses':[],'departments':[],'levels':[]};db.rpc.return_value=snapshot
    with patch('app.routes.auth.get_db',return_value=db):
        response=app.test_client().get('/api/auth/registration-options',headers={'X-Campus-ID':CAMPUS,'Authorization':'Bearer expired-token'})
    assert response.status_code==200 and response.get_json()==snapshot
    db.rpc.assert_called_once_with('hg_registration_options',{'p_campus_id':CAMPUS})


def test_registration_options_rejects_bad_campus_without_db_call():
    from app.routes.auth import auth_bp
    app=Flask(__name__);app.register_blueprint(auth_bp,url_prefix='/api/auth')
    with patch('app.routes.auth.get_db') as db:
        response=app.test_client().get('/api/auth/registration-options?campus_id=invalid')
    assert response.status_code==400;db.assert_not_called()


def test_registration_options_transient_error_is_retryable():
    from app.routes.auth import auth_bp
    from app.db import SupabaseError
    app=Flask(__name__);app.register_blueprint(auth_bp,url_prefix='/api/auth')
    db=Mock();db.rpc.side_effect=SupabaseError('offline')
    with patch('app.routes.auth.get_db',return_value=db):
        response=app.test_client().get('/api/auth/registration-options')
    assert response.status_code==503
