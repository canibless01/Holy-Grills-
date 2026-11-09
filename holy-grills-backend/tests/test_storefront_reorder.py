from unittest.mock import MagicMock,patch
from flask import Flask,g
import pytest
from app.routes import storefront as sf
from app.db import SupabaseError
from app.messages import MSG
app=Flask(__name__)
ID='11111111-1111-4111-8111-111111111111'
@pytest.mark.parametrize('body',[None,{},[],{'direction':True,'expected':[]},{'direction':0,'expected':[{}]},{'direction':1,'expected':[]},{'direction':-1,'expected':[{}]*501}])
def test_invalid_moves_cannot_reach_database(body):
 with app.test_request_context(method='POST',json=body),patch.object(sf,'get_db') as db:
  assert sf._move_cms(ID,'hg_move_storefront_section')[1]==400
 db.assert_not_called()
@pytest.mark.parametrize('helper',['hg_move_storefront_section','hg_move_storefront_banner'])
def test_actor_is_server_bound_and_full_expected_list_is_forwarded(helper):
 db=MagicMock();db.rpc.return_value={'moved':True}
 expected=[{'id':ID,'sort_order':0,'updated_at':None}]
 with app.test_request_context(method='POST',json={'direction':1,'expected':expected,'actor':'attacker'}),patch.object(sf,'get_db',return_value=db):
  g.user_id='actual-admin';assert sf._move_cms(ID,helper)[1]==200
 db.rpc.assert_called_once_with(helper,{'p_actor':'actual-admin','p_section':ID,'p_direction':1,'p_expected':expected})
@pytest.mark.parametrize('error,status',[('HG_STOREFRONT_ACCESS',403),('HG_STOREFRONT_STALE',409),('HG_STOREFRONT_INVALID',400)])
def test_privileged_errors_are_readable_without_leaking_database_details(error,status):
 db=MagicMock();db.rpc.side_effect=SupabaseError(error+' secret database detail',400,{})
 with app.test_request_context(method='POST',json={'direction':1,'expected':[{}]}),patch.object(sf,'get_db',return_value=db):
  g.user_id='actual-admin';response,code=sf._move_cms(ID,'hg_move_storefront_section')
 assert code==status and 'database detail' not in response.json['error']
