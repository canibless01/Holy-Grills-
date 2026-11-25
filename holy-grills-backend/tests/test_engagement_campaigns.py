"""No provider transport: validate full cycle, operating rules and outbox policy."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
import pytest
from flask import Flask, g
from app.services import engagement_campaigns as s
from app.routes import engagement_campaigns as routes
from app.services import notification_outbox as outbox, notification_service as ns
U='11111111-1111-4111-8111-111111111111';C='22222222-2222-4222-8222-222222222222'
NOW=datetime(2026,11,25,8,15,tzinfo=timezone.utc)


def test_default_cycle_complete_and_paused():
    value=s.validate(s.defaults());assert not value['is_active'];assert len(value['steps'])==28
    for step in value['steps']:
        assert '{{' not in s.render(step,{},'FUTA','16:00')['body']


@pytest.mark.parametrize('mutate',[
 lambda x:x.update(steps=x['steps'][:-1]),lambda x:x['steps'].__setitem__(1,deepcopy(x['steps'][0])),
 lambda x:x.update(morning_time='15:00'),lambda x:x.update(afternoon_time='11:00'),
 lambda x:x.update(is_active='true'),lambda x:x.update(revision=True),
 lambda x:x['steps'][0].update(body='Hi {{secret}}'),lambda x:x['steps'][0].update(body='Hi {{nickname'),
 lambda x:x['steps'][0].update(action_url='//attacker.test'),lambda x:x['steps'][0].update(action_url='/admin'),
 lambda x:x['steps'][0].update(action_url='/menu?token=private'),lambda x:x['steps'][0].update(push_image='https://attacker.test/x.jpg'),
])
def test_invalid_config_rejected(mutate):
    value=s.defaults();mutate(value)
    with pytest.raises(ValueError):s.validate(value)


def test_personalization_fallbacks_and_no_template_injection():
    step=s.defaults()['steps'][0]
    assert 'Blessing' in s.render(step,{'full_name':'Blessing Friend'},'FUTA','16:00')['body']
    assert 'Nick' in s.render(step,{'nickname':' Nick  ','full_name':'Other'},'FUTA','16:00')['body']
    assert 'friend' in s.render(step,{},'FUTA','16:00')['body']
    assert '{{campus}}' in s.render(step,{'nickname':'{{campus}}'},'FUTA','16:00')['body']


@pytest.mark.parametrize('status',[{'is_open':False},{'is_open':None},{'is_open':True,'windows':[]}])
def test_closed_sunday_override_full_or_unknown_never_returns_cutoff(status):
    with patch('app.utils.schedule.effective_windows_with_config',return_value=([{'id':C}],'date_override')),patch('app.services.order_service.get_ordering_window_status',return_value=status):
        assert s.ordering_cutoff(MagicMock(),C,NOW) is None


def test_cutoff_reuses_strict_schedule_and_capacity_status():
    with patch('app.utils.schedule.effective_windows_with_config',return_value=([{'id':C}],'weekly')) as strict,patch('app.services.order_service.get_ordering_window_status',return_value={'is_open':True,'windows':[{'is_open_now':True,'closes_at':'16:00:00'},{'is_open_now':False,'closes_at':'12:00'}]}):
        assert s.ordering_cutoff(MagicMock(),C,NOW).hour==16
        assert strict.call_args.kwargs=={'strict':True}


def test_schedule_failure_is_not_assumed_open():
    with patch('app.utils.schedule.effective_windows_with_config',side_effect=RuntimeError('offline')):
        with pytest.raises(RuntimeError):s.ordering_cutoff(MagicMock(),C,NOW)


def test_enqueue_renders_and_caps_expiry_at_real_cutoff():
    db=MagicMock();cfg=s.defaults();cfg.update(campus_id=C,campus_name='FUTA',cycle_day=1,slot='morning',scheduled_at=NOW.isoformat())
    db.rpc.side_effect=[[cfg],[{'id':U,'nickname':'Nick'}],{'queued':1}]
    cutoff=NOW+timedelta(minutes=20)
    with patch.object(s,'ordering_cutoff',return_value=cutoff):assert s.enqueue_due(db)['queued']==1
    params=db.rpc.call_args.args[1];assert params['p_expires']==cutoff.isoformat();assert 'Nick' in params['p_messages'][0]['body']


@pytest.mark.parametrize('valid,expired',[(False,False),(True,True)])
def test_paused_edited_or_expired_message_cannot_dispatch(valid,expired):
    db=MagicMock();db.rpc.return_value=valid
    snapshot={'user_id':U,'campus_id':C,'metadata':{'campaign_id':U,'campaign_revision':1,'expires_at':(NOW+timedelta(minutes=-1 if expired else 20)).isoformat()}}
    with patch.object(s,'ordering_cutoff',return_value=NOW+timedelta(hours=1)):
        assert s.dispatch_ttl(db,snapshot,NOW)==0


def test_dispatch_ttl_is_capped_by_actual_ordering_cutoff():
    db=MagicMock();db.rpc.return_value=True
    snapshot={'user_id':U,'campus_id':C,'metadata':{'campaign_id':U,'campaign_revision':1,'expires_at':(NOW+timedelta(minutes=20)).isoformat()}}
    with patch.object(s,'ordering_cutoff',return_value=NOW+timedelta(minutes=2)):
        assert s.dispatch_ttl(db,snapshot,NOW)==120


@pytest.mark.parametrize('ttl',[0,120])
def test_real_outbox_cancels_or_freezes_ttl_before_transport(ttl):
    db=MagicMock();q=db.table.return_value;q.select.return_value=q;q.eq.return_value=q;q.single.return_value=q;q.execute.return_value={'email':'local@example.invalid','campus_id':C}
    claim={'state':'claimed','channel':'push','token':U,'key':U,'payload':{'notification':{'user_id':U,'type':'engagement_cycle','title':'Title','body':'Body','metadata':{}}}}
    calls=[]
    def rpc(name,params):
        calls.append((name,params));return deepcopy(claim) if name=='hg_claim_notification_dispatch_v2' else True
    db.rpc.side_effect=rpc
    with patch.object(outbox,'get_db',return_value=db),patch.object(outbox,'effective_preferences',return_value={}),patch.object(s,'dispatch_ttl',return_value=ttl),patch.object(ns,'_get_onesignal_creds',return_value=('app','key')),patch.object(ns,'_prepare_notification_push',return_value={'idempotency_key':U}),patch.object(ns,'_deliver_push_attempt',return_value={'state':'accepted'}) as provider:
        result=outbox.dispatch_notification(U)
        if ttl==0:
            assert result['state']=='cancelled';provider.assert_not_called()
        else:
            assert result['state']=='accepted';assert provider.call_args.kwargs['prepared']['ttl']==120
            assert calls[-2][0]=='hg_begin_notification_dispatch'


@pytest.mark.parametrize('role,active,expected',[('student',True,403),('community_manager',True,403),('admin',False,403),('admin',True,200),('super_admin',True,200)])
def test_actual_role_boundary_and_preview_never_sends(role,active,expected):
    from app.middleware import auth
    app=Flask(__name__);app.register_blueprint(routes.engagement_campaigns_bp,url_prefix='/cycle')
    db=MagicMock();db.auth_get_user.return_value={'id':U}
    q=db.table.return_value
    for name in ('select','eq','single'):getattr(q,name).return_value=q
    q.execute.return_value={'id':U,'role':role,'is_active':active,'campus_id':C,'name':'FUTA'}
    db.rpc.return_value={'campaign':None}
    with patch.object(auth,'get_db',return_value=db),patch.object(routes,'get_db',return_value=db),patch.object(ns,'_deliver_push_attempt') as send:
        response=app.test_client().post('/cycle/preview',json={'campaign':s.defaults(),'day':1,'slot':'morning','nickname':'Nick'},headers={'Authorization':'Bearer synthetic-only','X-Campus-ID':C})
        assert response.status_code==expected
        if expected==403:db.rpc.assert_not_called()
        else:assert 'Nick' in response.json['body']
        send.assert_not_called()


def test_strict_closed_override_cannot_be_reopened_by_later_fallback_read():
    with patch('app.utils.schedule.effective_windows_with_config',return_value=([{'is_closed':True}],'override')),patch('app.services.order_service.get_ordering_window_status',return_value={'is_open':True,'windows':[{'is_open_now':True,'closes_at':'16:00'}]}) as fallback:
        assert s.ordering_cutoff(MagicMock(),C,NOW) is None
        fallback.assert_not_called()


def test_campus_targeted_tick_does_not_queue_another_campus():
    db=MagicMock();cfg=s.defaults();cfg['campus_id']=U;db.rpc.return_value=[cfg]
    with patch.object(s,'ordering_cutoff') as availability:
        assert s.enqueue_due(db,campus_id=C)=={'campaigns':0,'queued':0,'skipped':0}
        availability.assert_not_called()
    assert db.rpc.call_count==1
