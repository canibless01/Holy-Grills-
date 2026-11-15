"""Recovery/visibility contracts for birthday outreach and voluntary gifts."""
from unittest.mock import MagicMock, patch
from uuid import uuid4
import pytest
from flask import Flask, g
from app.services import birthdays, hp_gifts, wallet_transfers
from app.routes.hp import transfer_hp
from app.services.operations_email import render

@pytest.fixture
def app():
    return Flask(__name__)

@pytest.mark.parametrize('options', [{'anonymous': 'false'}, {'share_contact': 1}, {'anonymous':True, 'share_contact':True}, {'anonymous':None}])
def test_privacy_requires_explicit_boolean_options(options):
    with pytest.raises(wallet_transfers.TransferError):
        wallet_transfers.gift_options(options)


def test_named_default_does_not_share_phone():
    assert wallet_transfers.gift_options({}) == {}
    assert wallet_transfers.gift_options({'anonymous':False, 'share_contact':True}) == {'anonymous':False, 'share_contact':True}


def gift():
    return {'request_id':str(uuid4()), 'recipient_id':str(uuid4()), 'amount':10, 'notes':' Happy birthday ', 'anonymous':True, 'share_contact':False}


def completed(data):
    return {'direction':'sent','recipient_id':data['recipient_id'],'recipient_name':'Friend','amount':10,
            'note':'Happy birthday','anonymous':True,'share_contact':False,'balance_after':40}


def test_replay_checks_original_intent_and_does_not_recharge():
    body=gift();db=MagicMock();db.rpc.return_value=completed(body)
    with patch.object(hp_gifts,'get_db',return_value=db):
        result=hp_gifts.replay(body,'owner')
    assert result['replayed'] is True and result['new_balance']==40
    db.rpc.assert_called_once_with('hg_hp_gift_receipt',{'p_actor':'owner','p_request':body['request_id']})

@pytest.mark.parametrize('change',[{'amount':11},{'recipient_id':str(uuid4())},{'notes':'different'},{'anonymous':False},{'share_contact':True,'anonymous':False}])
def test_changed_replay_cannot_replace_original_gift(change):
    body=gift();db=MagicMock();db.rpc.return_value=completed(body)
    with patch.object(hp_gifts,'get_db',return_value=db),pytest.raises(wallet_transfers.TransferError) as failure:
        hp_gifts.replay({**body,**change},'owner')
    assert failure.value.code=='transfer_intent_conflict'

@pytest.mark.parametrize('amount',[True,'NaN','Infinity',-1,0,'1.5',{},2147483648])
def test_invalid_hp_cannot_reach_receipt_or_money_rpc(amount):
    with patch.object(hp_gifts,'get_db') as db,pytest.raises(wallet_transfers.TransferError):
        hp_gifts.replay({**gift(),'amount':amount},'owner')
    db.assert_not_called()


def test_committed_gift_returns_before_current_rules_or_balance(app):
    body=gift();db=MagicMock();db.rpc.return_value=completed(body)
    with app.test_request_context(method='POST',json=body),patch.object(hp_gifts,'get_db',return_value=db),patch('app.services.notification_outbox.start_reference_dispatch') as wake,patch('app.services.feature_flags.is_feature_enabled',side_effect=AssertionError('must not recheck committed intent')):
        g.user_id='owner'
        response,status=transfer_hp.__wrapped__()
    assert status==200 and response.json['replayed']
    assert wake.call_count==2


def test_birthday_uses_campus_setting_and_tier_perk_and_replay_is_not_counted(app):
    db=MagicMock();db.rpc.side_effect=[[{'id':'one','campus_id':'campus'},{'id':'two','campus_id':'campus'}],{'processed':True,'hp_awarded':250},{'replayed':True,'hp_awarded':250}]
    with app.app_context(),patch.object(birthdays,'get_db',return_value=db),patch.object(birthdays,'is_feature_enabled',return_value=True),patch.object(birthdays,'get_validated_setting',return_value=150),patch.object(birthdays,'resolve_perk',return_value=250):
        result=birthdays.process_birthdays()
    assert result['processed']==1 and result['hp_awarded']==250
    assert db.rpc.call_args_list[1].args[1]=={'p_user':'one','p_hp':250}


def test_disabled_birthday_hp_can_still_celebrate_and_race_skip_is_safe(app):
    db=MagicMock();db.rpc.side_effect=[[{'id':'one','campus_id':'campus'}],{'skipped':True}]
    with app.app_context(),patch.object(birthdays,'get_db',return_value=db),patch.object(birthdays,'is_feature_enabled',return_value=False),patch.object(birthdays,'resolve_perk') as perk:
        result=birthdays.process_birthdays()
    assert result['skipped_profiles']==1 and result['hp_awarded']==0
    assert db.rpc.call_args_list[1].args[1]['p_hp']==0
    perk.assert_not_called()


def test_birthday_unknown_capture_does_not_acknowledge_success(app):
    db=MagicMock();db.rpc.side_effect=[[{'id':'one','campus_id':'campus'}],None]
    with app.app_context(),patch.object(birthdays,'get_db',return_value=db),patch.object(birthdays,'is_feature_enabled',return_value=False),pytest.raises(RuntimeError):
        birthdays.process_birthdays()


def test_monthly_report_uses_existing_private_outbox(app):
    db=MagicMock();db.rpc.return_value={'campuses':1}
    with app.app_context(),patch.object(birthdays,'get_db',return_value=db),patch('app.services.operations_email.dispatch_pending',return_value={'accepted':1}) as dispatch:
        result=birthdays.queue_monthly_report()
    db.rpc.assert_called_once_with('hg_queue_birthday_reports',{})
    dispatch.assert_called_once_with(db)
    assert result['delivery']=={'accepted':1}


def test_birthday_report_contains_outreach_fields_without_raw_html():
    db=MagicMock();db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value={'name':'Campus'}
    result=render(db,{'campus_id':'campus','kind':'birthday_report','payload':{'month':'November','count':1,'people':[{'name':'<script>person</script>','date':'15 Nov','faculty':'Computing','department':'Software','phone':'+2348000000000'}]}})
    assert '15 Nov' in str(result) and 'Computing' in str(result) and '+2348000000000' in str(result)
    assert '<script>person</script>' not in result[1]
