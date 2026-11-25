"""Store choice must change fulfilment ownership, not campus pricing/schedules."""
from copy import deepcopy
from unittest.mock import MagicMock,patch
import pytest
from app.services import store_fulfilment as stores
from app.messages import MSG
C='11111111-1111-4111-8111-111111111111';A='22222222-2222-4222-8222-222222222222';B='33333333-3333-4333-8333-333333333333'
ROWS=[{'id':A,'campus_id':C,'name':'West store','address':'West road','instructions':'Counter','lat':7.3,'lon':5.14},
      {'id':B,'campus_id':C,'name':'North store','address':'North road','instructions':'Desk','lat':7.32,'lon':5.14}]

def db():
 value=MagicMock();value.rpc.return_value=deepcopy(ROWS)
 value.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value={'value':15}
 return value


def test_disabled_release_preserves_legacy_checkout_and_does_not_read_stores():
 with patch.object(stores,'is_feature_enabled',return_value=False),patch.object(stores,'get_db') as read:
  assert stores.resolve(C,'on_campus') is None
  with pytest.raises(ValueError,match='not available'):stores.resolve(C,'on_campus',A)
 read.assert_not_called()


def test_nearest_eligible_store_suggested_and_explicit_store_choice_retained():
 value=db()
 with patch.object(stores,'is_feature_enabled',return_value=True),patch.object(stores,'get_db',return_value=value):
  result=stores.options(C,'off_campus',7.319,5.14)
  assert result['suggested_store_id']==B
  assert stores.resolve(C,'off_campus',None,7.319,5.14)['id']==B
  assert stores.resolve(C,'off_campus',A,7.319,5.14)['id']==A
 assert value.rpc.call_args.args==('hg_order_store_choices',{'p_campus':C,'p_pickup':False})


def test_without_pin_multiple_stores_need_an_explicit_selection():
 with patch.object(stores,'is_feature_enabled',return_value=True),patch.object(stores,'get_db',return_value=db()):
  assert stores.options(C,'on_campus')['suggested_store_id'] is None
  with pytest.raises(ValueError,match='Choose a store'):stores.resolve(C,'on_campus')
  assert stores.resolve(C,'on_campus',A)['address']=='West road'


def test_foreign_closed_or_unstaffed_store_not_in_authoritative_choices_is_rejected():
 value=db();value.rpc.return_value=[deepcopy(ROWS[0])]
 with patch.object(stores,'is_feature_enabled',return_value=True),patch.object(stores,'get_db',return_value=value):
  with pytest.raises(ValueError):stores.resolve(C,'off_campus',B,7.31,5.14)
  assert stores.resolve(C,'on_campus')['id']==A


def test_outside_radius_cannot_select_a_distant_store_or_create_a_fake_nearest_choice():
 value=db()
 with patch.object(stores,'is_feature_enabled',return_value=True),patch.object(stores,'get_db',return_value=value):
  result=stores.options(C,'off_campus',8.0,5.14)
  assert result['stores']==[] and result['suggested_store_id'] is None
  with pytest.raises(ValueError):stores.resolve(C,'off_campus',A,8.0,5.14)


def test_one_coordinate_is_not_a_valid_delivery_pin():
 with patch.object(stores,'is_feature_enabled',return_value=True),patch.object(stores,'get_db') as value:
  with pytest.raises(ValueError):stores.options(C,'off_campus',7.3,None)
 value.assert_not_called()


def test_pickup_uses_same_campus_store_choices_without_delivery_requirement():
 value=db()
 with patch.object(stores,'is_feature_enabled',return_value=True),patch.object(stores,'get_db',return_value=value):
  result=stores.resolve(C,'store_pickup',B)
 assert result=={key:ROWS[1].get(key) for key in stores.SNAPSHOT}
 assert value.rpc.call_args.args[1]['p_pickup'] is True
 assert 'price' not in result and 'capacity' not in result and 'opens_at' not in result


@pytest.mark.parametrize('profile,allowed',[({'role':'student','campus_id':C,'is_active':True},False),({'role':'admin','campus_id':A,'is_active':True},False),({'role':'kitchen','campus_id':C,'is_active':False},False),({'role':'super_admin','campus_id':A,'is_active':True},True)])
def test_fresh_role_and_campus_boundaries(profile,allowed):
 value=MagicMock();value.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value=profile
 with patch.object(stores,'get_db',return_value=value):assert stores.staff_may_access(A,B,C) is allowed
 value.rpc.assert_not_called()


def test_membership_lookup_is_needed_for_active_kitchen_or_rider():
 value=MagicMock();value.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value={'role':'kitchen','campus_id':C,'is_active':True}
 with patch.object(stores,'get_db',return_value=value):
  value.rpc.return_value=False;assert stores.staff_may_access(A,B,C) is False
  value.rpc.return_value=True;assert stores.staff_may_access(A,B,C) is True


@pytest.mark.parametrize('decision',[False,None,'true',{'ready':True}])
def test_store_release_never_activates_from_an_unverified_dispatch_decision(decision):
 from flask import Flask,g
 from app.routes import admin_feature_flags as flags
 app=Flask(__name__);value=MagicMock();value.rpc.return_value=decision
 with app.test_request_context(),patch.object(flags,'get_db',return_value=value),patch.object(flags,'get_user_client') as write:
  g.user_id=A
  response,status=flags._upsert_feature_flag('multi_store_ordering',{'is_active':True})
 assert status==409 and response.json['error']==MSG.STORE_RELEASE_NOT_READY
 write.assert_not_called()


def test_store_release_stays_off_when_dispatch_verification_is_unavailable():
 from flask import Flask,g
 from app.routes import admin_feature_flags as flags
 from app.db import SupabaseError
 app=Flask(__name__);value=MagicMock();value.rpc.side_effect=SupabaseError('Unavailable',503,{})
 with app.test_request_context(),patch.object(flags,'get_db',return_value=value),patch.object(flags,'get_user_client') as write:
  g.user_id=A
  response,status=flags._upsert_feature_flag('multi_store_ordering',{'is_active':True})
 assert status==409;write.assert_not_called()


def test_no_operational_stores_gives_a_clear_unavailability_message():
 value=db();value.rpc.return_value=[]
 with patch.object(stores,'is_feature_enabled',return_value=True),patch.object(stores,'get_db',return_value=value):
  with pytest.raises(ValueError,match='No stores'):stores.resolve(C,'off_campus')


def test_super_admin_student_store_picker_uses_account_campus_not_admin_header():
 from flask import Flask,g
 from app.routes import delivery
 import inspect
 app=Flask(__name__)
 with app.test_request_context(headers={'X-Campus-ID':B}),patch.object(stores,'options',return_value={'enabled':False,'stores':[]}) as options:
  g.user_id=A;g.user_role='super_admin';g.campus_id=C
  response=inspect.unwrap(delivery.available_stores)()
 options.assert_called_once_with(C,'on_campus',None,None)
 assert response.json['enabled'] is False


def test_admin_batch_uses_frozen_store_origin_and_only_eligible_riders():
 from flask import Flask,g
 from app.routes import admin
 app=Flask(__name__);value=MagicMock();service=MagicMock()
 origin={'id':B,'name':'North store','lat':7.32,'lon':5.14}
 tables={name:MagicMock() for name in ('delivery_batches','orders','gates')}
 tables['delivery_batches'].select.return_value.eq.return_value.single.return_value.execute.return_value={'id':A,'store_id':B,'campus_id':C,'gate_id':A}
 tables['orders'].select.return_value.eq.return_value.execute.return_value=[{'id':A,'created_at':'2026-11-23','fulfilment_store_snapshot':origin,'delivery_location_lat':7.321,'delivery_location_lon':5.14}]
 value.table.side_effect=lambda name:tables[name]
 service.rpc.return_value=[{'id':A,'store_ids':[B]},{'id':C,'store_ids':[A]}]
 with app.test_request_context(),patch.object(admin,'get_user_client',return_value=value),patch.object(admin,'get_db',return_value=service),patch.object(admin,'assert_can_modify'):
  g.user_id=A
  response,status=admin.get_batch.__wrapped__(A)
 assert status==200 and response.json['fulfilment_store']==origin
 assert [row['id'] for row in response.json['eligible_riders']]==[A]
 tables['gates'].select.assert_not_called()
 service.rpc.assert_called_once_with('hg_store_riders',{'p_actor':A,'p_campus':C})
