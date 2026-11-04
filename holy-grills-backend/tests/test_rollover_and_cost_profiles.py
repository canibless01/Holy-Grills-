import copy
from datetime import datetime, timezone
from unittest.mock import patch
from flask import Flask, g
from app.tasks import scheduled
from app.tasks.celery_app import celery_app, _scan_schedule
from app.routes import cart


class Result(list):
    def execute(self): return self


class Query:
    def __init__(self, db, table): self.db,self.table=db,table;self.filters=[];self.start=0;self.size=1000
    def select(self,*args): return self
    def eq(self,key,value): self.filters.append(lambda row:row.get(key)==value);return self
    def is_(self,key,value): self.filters.append(lambda row:row.get(key) is None);return self
    def in_(self,key,values): self.filters.append(lambda row:row.get(key) in values);return self
    def or_(self,expr):
        self.db.predicates.append(expr)
        if 'reference_type' in expr: self.filters.append(lambda row:row.get('reference_type')!='hp_transfer')
        return self
    def gte(self,*args): return self
    def lt(self,*args): return self
    def order(self,*args): return self
    def limit(self,value): self.size=value;return self
    def offset(self,value): self.start=value;return self
    def execute(self):
        self.db.reads.append(self.table)
        rows=[row for row in self.db.rows.get(self.table,[]) if all(f(row) for f in self.filters)]
        return copy.deepcopy(rows[self.start:self.start+self.size])
    def insert(self,row): self.db.rows.setdefault(self.table,[]).append(copy.deepcopy(row));return Result([row])
    def delete(self):
        rows=self.execute();self.db.rows[self.table]=[row for row in self.db.rows[self.table] if row not in rows];return Result(rows)


class DB:
    def __init__(self,rows): self.rows=rows;self.reads=[];self.predicates=[];self.calls=[]
    def table(self,table): return Query(self,table)
    def rpc(self,name,params):
        self.calls.append((name,params))
        if name=='hg_finalize_monthly_leaderboard':
            self.rows.setdefault('leaderboard_snapshots',[]).append({'campus_id':params['p_campus_id'],'period_key':params['p_period'],'ranking_type':'monthly'})
            return {'idempotent':False,'period':params['p_period'],'inducted':[]}
        return True


def test_completed_period_labels_and_wat_boundaries():
    key,start,end=scheduled._completed_period(datetime(2026,11,8,23,1,tzinfo=timezone.utc),'weekly')
    assert key=='2026-11-02' and start.isoformat()=='2026-11-01T23:00:00+00:00' and end.isoformat()=='2026-11-08T23:00:00+00:00'
    key,start,end=scheduled._completed_period(datetime(2026,10,31,23,1,tzinfo=timezone.utc),'monthly')
    assert key=='2026-10' and start.isoformat()=='2026-09-30T23:00:00+00:00' and end.isoformat()=='2026-10-31T23:00:00+00:00'


def test_rollover_excludes_staff_inactive_foreign_campus_and_transfers():
    profiles=[{'id':uid,'role':role,'is_active':active,'campus_id':campus} for uid,role,active,campus in [('a','student',True,'c'),('b','student',True,'c'),('staff','super_admin',True,'c'),('inactive','student',False,'c'),('foreign','student',True,'other')]]
    tx=[{'id':str(i),'user_id':p['id'],'amount':10,'type':'earn','campus_id':'c','reference_type':None} for i,p in enumerate(profiles)]
    tx.append({'id':'transfer','user_id':'b','amount':10000,'type':'earn','campus_id':'c','reference_type':'hp_transfer'})
    db=DB({'profiles':profiles,'hp_transactions':tx})
    with patch('app.services.squad_service.resolve_leaderboard_names_batch',return_value={'a':'A','b':'B'}):
        entries=scheduled._period_student_entries(db,'c',datetime.now(timezone.utc),datetime.now(timezone.utc))
    assert [(e['user_id'],e['rank'],e['hp_earned']) for e in entries]==[('a',1,10),('b',2,10)]
    assert 'reference_type.is.null,reference_type.neq.hp_transfer' in db.predicates


def test_rollover_does_not_truncate_at_data_api_page_limit():
    profiles=[{'id':str(i).zfill(5),'role':'student','is_active':True,'campus_id':'c'} for i in range(1005)]
    tx=[{'id':str(i).zfill(5),'user_id':p['id'],'amount':i+1,'type':'earn','campus_id':'c'} for i,p in enumerate(profiles)]
    db=DB({'profiles':profiles,'hp_transactions':tx})
    with patch('app.services.squad_service.resolve_leaderboard_names_batch',return_value={}):
        entries=scheduled._period_student_entries(db,'c',datetime.now(timezone.utc),datetime.now(timezone.utc))
    assert entries[0]['user_id']=='01004'
    assert db.reads.count('profiles')==2 and db.reads.count('hp_transactions')==2


def test_weekly_job_archives_empty_period_and_replay_skips_it():
    db=DB({'campuses':[{'id':'c','is_active':True}]})
    with patch.object(scheduled,'get_db',return_value=db),patch.object(scheduled,'_period_student_entries',return_value=[]):
        scheduled.reset_weekly_leaderboard.run()
        result=scheduled.reset_weekly_leaderboard.run()
    assert len(db.rows['leaderboard_snapshots'])==1
    assert 'skipped' in result['c']


def test_monthly_job_uses_atomic_rpc_and_does_not_repeat_notifications():
    db=DB({'campuses':[{'id':'c','is_active':True}]})
    with Flask(__name__).app_context(),patch.object(scheduled,'get_db',return_value=db),patch.object(scheduled,'_period_student_entries',return_value=[]),patch.object(scheduled,'_notify_monthly_result') as notify:
        scheduled.reset_monthly_leaderboard.run()
        scheduled.reset_monthly_leaderboard.run()
    assert len([call for call in db.calls if call[0]=='hg_finalize_monthly_leaderboard'])==1
    notify.assert_called_once()


def test_cost_profile_keeps_all_jobs_with_fewer_nonurgent_scans():
    schedule=celery_app.conf.beat_schedule
    assert len(schedule['send-newsletter-campaigns']['schedule'].minute)==4
    assert len(schedule['process-scheduled-orders']['schedule'].minute)==4
    assert len(schedule['abandoned-cart-scan']['schedule'].minute)==1
    assert len(schedule['check-post-delivery-nudges']['schedule'].minute)==1
    assert 'reset-weekly-leaderboard' in schedule and 'reset-monthly-leaderboard' in schedule
    assert celery_app.conf.timezone=='Africa/Lagos'
    with patch.dict('os.environ',{'TEST_SCAN_MINUTES':'5'}): assert len(_scan_schedule('TEST_SCAN_MINUTES',15).minute)==12


def test_cart_batches_availability_and_preserves_price_stock_rules():
    rows=[{'id':str(i),'user_id':'u','menu_item_id':str(i),'quantity':1,'menu_items':{'id':str(i),'name':'Meal','is_available':True,'price':100}} for i in range(3)]
    db=DB({'cart_items':rows,'menu_item_availability':[{'menu_item_id':'0','campus_id':'c','is_available':True,'price_override':120},{'menu_item_id':'1','campus_id':'c','is_available':False}]})
    with Flask(__name__).test_request_context(),patch.object(cart,'get_user_client',return_value=db),patch('app.services.order_service._resolve_item_variations',return_value=(0,[])),patch('app.services.order_service._resolve_item_addons',return_value=(0,[])):
        g.user_id='u';g.campus_id='c'
        response,status=cart.get_cart.__wrapped__()
    assert status==200 and response.json['subtotal']==320 and response.json['has_unavailable_items'] is True
    assert db.reads.count('menu_item_availability')==1


def test_monthly_tier_grants_reuse_hp_reference_and_do_not_duplicate_sides():
    db=DB({'profiles':[{'id':'student','is_active':True,'campus_id':'c'}]})
    with Flask(__name__).app_context(),patch.object(scheduled,'get_db',return_value=db),patch.object(scheduled,'get_validated_setting',return_value=60),patch('app.services.tier_service.resolve_perk',side_effect=lambda uid,key:1 if key=='free_side_credits_monthly' else 5),patch('app.services.hp_service.award_active_hp') as award:
        scheduled.grant_monthly_tier_perks.run()
        scheduled.grant_monthly_tier_perks.run()
    assert len(db.rows['free_side_credits'])==1
    assert award.call_args_list[0].kwargs['reference_id']==award.call_args_list[1].kwargs['reference_id']


def test_monthly_tracker_reset_keeps_current_month():
    from app.utils.tz import today_wat
    month=today_wat().replace(day=1)
    previous=(month-__import__('datetime').timedelta(days=1)).strftime('%Y-%m')
    db=DB({'campuses':[{'id':'c','is_active':True}], 'monthly_hp_tracker':[
        {'campus_id':'c','month':previous},{'campus_id':'c','month':month.strftime('%Y-%m')}]})
    with patch.object(scheduled,'get_db',return_value=db): scheduled.reset_monthly_hp_tracker.run()
    assert db.rows['monthly_hp_tracker']==[{'campus_id':'c','month':month.strftime('%Y-%m')}]


def test_cron_monitor_uses_one_read_and_the_actual_scan_cadence():
    from unittest.mock import MagicMock
    from app.routes import admin
    stamp=datetime.now(timezone.utc).isoformat()
    event={'created_at':stamp,'action':'scheduled_execution_success','after_value':{}}
    db=MagicMock();db.rpc.return_value=[{'job':'process-scheduled-orders','last_run':event,'last_success':event}]
    with Flask(__name__).test_request_context(),patch.object(admin,'get_db',return_value=db):
        response,status=admin.cron_status.__wrapped__()
    assert status==200
    assert response.json['jobs']['process-scheduled-orders']['cadence']=='every 15 minutes'
    assert response.json['jobs']['process-scheduled-orders']['status']=='ok'
    db.table.assert_not_called();db.rpc.assert_called_once()
