import inspect
from unittest.mock import patch
from flask import Flask,g
import pytest
from app.routes import orders
from app.services.delivery_benefits import quote_delivery_benefit
from tests.test_checkout_quote import Db,CAMPUS

app=Flask(__name__)


def database():
    db=Db()
    db.rows['exclusive_spin_fulfillments']=[
        {'id':'delivery','user_id':'student','campus_id':CAMPUS,'status':'pending','prize_name':'30% delivery treat','applied_order_id':None,'result_snapshot':{'prize_type':'free_delivery','expires_at':'2099-01-01T00:00:00Z','reward_config':{'cap':200,'discount_pct':0.3}}},
        {'id':'food','user_id':'student','campus_id':CAMPUS,'status':'pending','prize_name':'Double food HP','applied_order_id':None,'result_snapshot':{'prize_type':'hp_multiplier','expires_at':'2099-01-01T00:00:00Z','reward_config':{'multiplier':2}}}]
    return db


def call(db,query='',campus=CAMPUS):
    with app.test_request_context('/reward-options'+query),patch.object(orders,'get_db',return_value=db):
        g.user_id='student';g.campus_id=campus
        return inspect.unwrap(orders.checkout_reward_options)()


def test_owned_rewards_visible_without_address_fee_cart_or_reservation():
    db=database();response,status=call(db)
    assert status==200 and response.headers['Cache-Control']=='private, no-store'
    delivery=response.json['delivery'][0]
    assert delivery['id']=='delivery' and delivery['percentage']==30 and delivery['cap']==200
    assert 'discount' not in delivery # Unknown saving must not be presented as zero.
    assert response.json['hp'][0]['multiplier']==2
    # The fixture throws if any insert/update/delete or mutating RPC is attempted.


def test_same_preselected_reward_reprices_after_location_and_respects_cap():
    db=database()
    with patch('app.services.delivery_benefits.resolve_perk',return_value=False):
        first=quote_delivery_benefit('student',CAMPUS,500,False,db=db,choice='delivery')
        second=quote_delivery_benefit('student',CAMPUS,1000,False,db=db,choice='delivery')
    assert first['discount']==150 and second['discount']==200
    assert first['selected_id']==second['selected_id']=='delivery'
    assert 'percentage' not in first # Display-only terms never alter the financial claim.


def test_expired_rewards_not_offered_upfront():
    db=database()
    for row in db.rows['exclusive_spin_fulfillments']:row['result_snapshot']['expires_at']='2000-01-01T00:00:00Z'
    response,status=call(db);assert status==200 and response.json=={'delivery':[],'hp':[]}


@pytest.mark.parametrize('query,campus,status',[('?squad=garbage',CAMPUS,400),('',None,400),('', 'other-campus',503)])
def test_invalid_scope_and_options_do_not_offer_rewards(query,campus,status):
    response,actual=call(database(),query,campus)
    assert actual==status and 'error' in response.json


def test_failed_discovery_is_retryable_not_a_false_empty_balance():
    db=database();db.fail.add('exclusive_spin_fulfillments')
    response,status=call(db);assert status==503 and 'error' in response.json
