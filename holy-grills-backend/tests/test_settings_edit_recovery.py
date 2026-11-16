"""Settings edits cannot overwrite an unseen concurrent change or announce a failed write."""
from unittest.mock import MagicMock,patch
import pytest
from flask import Flask,g
from app.routes import admin_gifts as route
from app.db import SupabaseError

OLD='2026-11-15T10:00:00+00:00'
NEW='2026-11-15T11:00:00+00:00'

def invoke(body,existing=None,write=None,role='super_admin',campus=None):
    db=MagicMock();q=db.table.return_value
    for method in ('eq','is_'):getattr(q,method).return_value=q
    q.update.return_value=[{'key':'hp_multiplier','updated_at':NEW}] if write is None else write
    app=Flask(__name__)
    with app.test_request_context(method='PATCH',json=body),patch.object(route,'get_user_client',return_value=db),patch.object(route,'read_global_setting',return_value=existing or {'key':'hp_multiplier','value':1,'updated_at':OLD}),patch.object(route,'read_percampus_setting',return_value=existing or {'key':'hp_multiplier','value':1,'updated_at':OLD}),patch.object(route,'_broadcast_multiplier_event') as broadcast:
        g.user_id='admin';g.user_role=role;g.campus_id=campus
        response,status=route.update_setting.__wrapped__('hp_multiplier')
    return response,status,q,broadcast


def test_stale_editor_cannot_write_or_broadcast():
    _,status,q,broadcast=invoke({'value':2,'expected_updated_at':OLD},existing={'value':1,'updated_at':NEW})
    assert status==409;q.update.assert_not_called();broadcast.assert_not_called()


def test_interleaved_change_after_read_is_guarded_at_write():
    _,status,q,broadcast=invoke({'value':2,'expected_updated_at':OLD},write=[])
    assert status==409
    assert ('updated_at',OLD) in [c.args for c in q.eq.call_args_list]
    broadcast.assert_not_called()


def test_legacy_editor_also_uses_read_version_at_write():
    _,status,q,_=invoke({'value':1})
    assert status==200
    assert ('updated_at',OLD) in [c.args for c in q.eq.call_args_list]


def test_equivalent_instant_is_accepted_and_filter_keeps_original_value():
    _,status,q,_=invoke({'value':1,'expected_updated_at':'2026-11-15T10:00:00Z'})
    assert status==200
    assert ('updated_at','2026-11-15T10:00:00Z') in [c.args for c in q.eq.call_args_list]

@pytest.mark.parametrize('stamp',[None,True,[],{},'bad'])
def test_invalid_version_is_rejected_without_write(stamp):
    _,status,q,_=invoke({'value':2,'expected_updated_at':stamp})
    assert status==400;q.update.assert_not_called()


def test_global_setting_still_forbidden_for_campus_admin():
    _,status,q,_=invoke({'value':2},role='admin',campus='campus-a')
    assert status==403;q.update.assert_not_called()


def test_scoped_write_keeps_campus_filter():
    _,status,q,_=invoke({'value':1,'campus_id':'campus-a'},role='admin',campus='campus-a')
    assert status==200
    assert ('campus_id','campus-a') in [c.args for c in q.eq.call_args_list]
