from copy import deepcopy
from datetime import datetime
from unittest.mock import MagicMock,patch
from flask import Flask
import pytest
from app.services import ambassador_report_mail as m
from app.services import notification_outbox as outbox,notification_service as ns

@pytest.mark.parametrize('stamp,expected',[
 ('2026-11-30T08:59:00+01:00',[]),
 ('2026-11-30T09:00:00+01:00',[('weekly','2026-11-23')]),
 ('2026-12-01T09:00:00+01:00',[('weekly','2026-11-23'),('monthly','2026-11-01')]),
 ('2026-12-02T09:00:00+01:00',[('monthly','2026-11-01')]),
 ('2026-12-03T09:00:00+01:00',[]),
 ('2027-01-01T09:00:00+01:00',[('monthly','2026-12-01')]),
])
def test_schedule_wat_completed_period_and_bounded_recovery(stamp,expected):
 assert m.due_periods(datetime.fromisoformat(stamp))==expected

def sample():
 person={'user_id':'user','name':'Personal Student','nickname':'Nick','current_tier':'Flame','progress':{'signups':3,'orders':2,'shared_count':1,'assigned_count':4,'revenue':999999,'phone':'SECRET-PHONE'},'month_progress':{'signups':5,'orders':4,'shared_count':2,'monthly_share_target':16},'email':'SECRET-EMAIL'}
 data={'kind':'monthly','month':'2026-11','campus_name':'FUTA','period_start':'2026-11-01','period_end':'2026-11-30','people':[person],
 'team':{'ambassadors':2,'signups':5,'orders':3,'shared_count':2,'profit':999999,'email':'TEAM-SECRET'},'tiers':[{'tier':'Flame','members':2}]}
 return data,person

def test_personal_report_and_team_tiers_never_leak_finance_or_contacts():
 data,person=sample();app=Flask(__name__)
 with app.app_context():title,body=m.render(data,person)
 assert 'Nick' in body and 'Flame: 2 ambassadors' in body and '5 sign-ups' in body
 assert '999999' not in body and 'SECRET' not in body and 'profit' not in body and 'revenue' not in body
 assert 'https://holygrills.online/dashboard' in body and 'monthly' in title

def test_non_due_tick_does_no_database_work():
 db=MagicMock();assert m.capture_due(db,datetime.fromisoformat('2026-11-26T09:00:00+01:00'))['queued']==0;db.rpc.assert_not_called()

def test_one_campus_read_and_snapshot_reused_for_all_members():
 data,person=sample();second=deepcopy(person);second['user_id']='second';data['people'].append(second)
 db=MagicMock();db.rpc.side_effect=[[{'campus_id':'campus'}],data,{'queued':True},{'duplicate':True}]
 with Flask(__name__).app_context(),patch.object(m,'due_periods',return_value=[('monthly','2026-11-01')]):result=m.capture_due(db)
 assert result=={'queued':1,'duplicates':1,'skipped':0,'errors':0}
 assert [c.args[0] for c in db.rpc.call_args_list]==['hg_due_ambassador_report_campuses','hg_ambassador_mail_data','hg_queue_ambassador_report','hg_queue_ambassador_report']

def test_snapshot_error_is_deferred_and_not_sent():
 db=MagicMock();db.rpc.side_effect=RuntimeError('offline')
 with patch.object(m,'due_periods',return_value=[('monthly','2026-11-01')]):assert m.capture_due(db)['errors']==1

@pytest.mark.parametrize('valid',[True,False])
def test_dispatch_rechecks_ambassador_before_external_email(valid):
 db=MagicMock();q=db.table.return_value
 for name in ['select','eq','single']:getattr(q,name).return_value=q
 q.execute.return_value={'email':'local@example.invalid','campus_id':'campus'}
 claim={'state':'claimed','channel':'email','token':'token','key':'key','payload':{'notification':{'user_id':'user','email':'local@example.invalid','name':'Nick','title':'Report','body':'Body','type':'ambassador_progress_report','metadata':{'report_campus_id':'campus'}}}}
 def rpc(name,args):
  if name=='hg_claim_notification_dispatch_v2':return deepcopy(claim)
  if name=='hg_ambassador_report_notice_valid':return valid
  return True
 db.rpc.side_effect=rpc
 with patch.object(outbox,'get_db',return_value=db),patch.object(outbox,'effective_preferences',return_value={}),patch.object(ns,'_prepare_notification_email',return_value={'provider':'resend'}),patch.object(ns,'_deliver_email_attempt',return_value={'state':'accepted'}) as email:
  result=outbox.dispatch_notification('notice')
  if valid:assert result['state']=='accepted';email.assert_called_once()
  else:assert result['state']=='cancelled';email.assert_not_called()
