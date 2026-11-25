"""Real isolated PostgreSQL concurrency and interrupted enqueue proof; no network sends."""
import json, os, threading, uuid
from concurrent.futures import ThreadPoolExecutor
import psycopg2
from psycopg2.extensions import parse_dsn
from psycopg2.extras import Json
from app.services.engagement_campaigns import defaults
DSN=os.environ.get('HG_CYCLE_TEST_DSN','host=127.0.0.1 port=55449 dbname=engagement user=postgres password=engagement-local')
p=parse_dsn(DSN)
if p.get('host') not in ('127.0.0.1','localhost') or p.get('dbname')!='engagement':raise SystemExit('Only isolated localhost engagement database is allowed')
def sql(statement,args=(),one=False):
    with psycopg2.connect(DSN) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET statement_timeout='10s'; SET lock_timeout='8s'; SET request.jwt.claims='{\"role\":\"service_role\"}'")
            cursor.execute(statement,args)
            if cursor.description:return cursor.fetchone()[0] if one else cursor.fetchall()
def race(calls):
    gate=threading.Barrier(len(calls))
    def worker(call):gate.wait(timeout=12);return sql(*call,one=True)
    with ThreadPoolExecutor(max_workers=len(calls)) as pool:return list(pool.map(worker,calls))
uid=lambda:str(uuid.uuid4())
c,c2,admin,student,other,boss,optout,cm=[uid() for _ in range(8)];cfg=defaults();cid=cfg['id'];slot=None
try:
    sql("INSERT INTO campuses(id,name,slug,is_active) VALUES(%s,'Local cycle',%s,true),(%s,'Foreign cycle',%s,true)",(c,'local-'+c,c2,'local-'+c2))
    for identity,role,campus in [(admin,'admin',c),(student,'student',c),(other,'student',c2),(boss,'super_admin',c),(optout,'student',c),(cm,'community_manager',c)]:
        sql('INSERT INTO auth.users(id,email) VALUES(%s,%s)',(identity,identity+'@example.invalid'))
        sql('INSERT INTO profiles(id,email,full_name,role,campus_id,is_active) VALUES(%s,%s,%s,%s,%s,true) ON CONFLICT(id) DO UPDATE SET role=excluded.role,campus_id=excluded.campus_id,is_active=true',(identity,identity+'@example.invalid','Local cycle',role,campus))
        sql("INSERT INTO device_tokens(user_id,token,platform) VALUES(%s,%s,'web')",(identity,uid()))
    sql('INSERT INTO notification_preferences(user_id,promotions) VALUES(%s,false)',(optout,))
    day,clock=sql("SELECT (now() AT TIME ZONE 'Africa/Lagos')::date, (now() AT TIME ZONE 'Africa/Lagos')::time")[0]
    slot='morning' if clock.hour<12 else 'afternoon';cfg.update(start_date=str(day),is_active=True)
    cfg['morning_time']=str(clock) if slot=='morning' else '09:00'
    cfg['afternoon_time']=str(clock) if slot=='afternoon' else '15:00'
    for actor,scope in [(student,c),(admin,c2),(cm,c)]:
        assert sql('SELECT hg_engagement_campaign_config(%s,%s,%s)',(actor,scope,Json(cfg)),True)['error']=='forbidden'
    assert sql('SELECT hg_engagement_campaign_config(%s,null)',(boss,),True)['error']=='forbidden'
    created=sql('SELECT hg_engagement_campaign_config(%s,%s,%s)',(admin,c,Json(cfg)),True)['campaign'];assert created['revision']==1
    due=sql('SELECT hg_due_engagement_campaigns()',one=True);assert any(x['id']==cid and x['cycle_day']==1 for x in due)
    recipients=sql('SELECT hg_engagement_campaign_recipients(%s,%s)',(cid,slot),True);assert [x['id'] for x in recipients]==[student],recipients
    expires=sql("SELECT now()+interval '20 minutes'",one=True).isoformat()
    good={'user_id':student,'title':'Morning Nick','body':'Bring your people','action_url':'/menu'}
    call='SELECT hg_enqueue_engagement_campaign(%s,1,%s,%s,%s)'
    # Failure on the second eligible recipient rolls back the first receipt/outbox too.
    sql('UPDATE notification_preferences SET promotions=true WHERE user_id=%s',(optout,))
    try:
        sql(call,(cid,slot,Json([good,dict(good,user_id=optout,title='')]),expires),True)
        raise AssertionError('invalid second recipient did not abort')
    except psycopg2.Error:pass
    assert sql('SELECT count(*) FROM hg_internal.engagement_campaign_receipts WHERE campaign_id=%s',(cid,),True)==0
    sql('UPDATE notification_preferences SET promotions=false WHERE user_id=%s',(optout,))
    results=race([(call,(cid,slot,Json([good,dict(good,user_id=other),dict(good,user_id=boss),dict(good,user_id=optout)]),expires)) for _ in range(6)])
    assert sum(r['queued'] for r in results)==1,results
    assert sql('SELECT count(*) FROM hg_internal.engagement_campaign_receipts WHERE campaign_id=%s',(cid,),True)==1
    notice=sql('SELECT notification_id FROM hg_internal.engagement_campaign_receipts WHERE campaign_id=%s',(cid,),True)
    assert sql('SELECT count(*) FROM notification_deliveries WHERE notification_id=%s',(notice,),True)==1
    print('PASS six concurrent queues: one receipt, one push and one durable outbox; foreign campus, staff and opt-outs excluded',flush=True)
    claim=sql('SELECT hg_claim_notification_dispatch_v2(%s)',(notice,),True);assert claim['state']=='claimed',claim
    prepared={'app_id':'synthetic-local-only','idempotency_key':claim['key'],'ttl':900}
    assert sql('SELECT hg_begin_notification_dispatch(%s,%s,%s)',(notice,claim['token'],Json(prepared)),True) is True
    assert sql('SELECT hg_finish_notification_dispatch(%s,%s,%s)',(notice,claim['token'],Json({'state':'retry'})),True) is True
    sql("UPDATE notification_deliveries SET dispatch=jsonb_set(dispatch,'{next_at}',to_jsonb(now()-interval '1 second')) WHERE notification_id=%s",(notice,))
    again=sql('SELECT hg_claim_notification_dispatch_v2(%s)',(notice,),True)
    assert again['state']=='claimed' and again['key']==claim['key'] and again['payload']['prepared']==prepared,again
    assert sql('SELECT hg_begin_notification_dispatch(%s,%s,%s)',(notice,again['token'],Json(dict(prepared,ttl=800))),True) is True
    assert sql('SELECT hg_finish_notification_dispatch(%s,%s,%s)',(notice,again['token'],Json({'state':'retry'})),True) is True
    sql("UPDATE notification_deliveries SET dispatch=jsonb_set(dispatch,'{next_at}',to_jsonb(now()-interval '1 second')) WHERE notification_id=%s",(notice,))
    third=sql('SELECT hg_claim_notification_dispatch_v2(%s)',(notice,),True)
    for changed in [dict(prepared,ttl=900),dict(prepared,ttl=700,app_id='changed'),{'app_id':'synthetic-local-only','idempotency_key':claim['key']}]:
        try:
            sql('SELECT hg_begin_notification_dispatch(%s,%s,%s)',(notice,third['token'],Json(changed)),True)
            raise AssertionError('mutable content or extended/missing TTL accepted')
        except psycopg2.Error:pass
    print('PASS interrupted push recovers same content/key; only shorter TTL allowed, never content edits or extended/missing TTL; no provider send',flush=True)
    cfg['revision']=1;cfg['is_active']=False
    edits=race([('SELECT hg_engagement_campaign_config(%s,%s,%s)',(admin,c,Json(cfg))) for _ in range(2)])
    assert sum('campaign' in r for r in edits)==1 and sum(r.get('error')=='stale' for r in edits)==1,edits
    assert sql('SELECT hg_engagement_campaign_notice_valid(%s,1,%s)',(cid,student),True) is False
    cfg['revision']=2;cfg['is_active']=True
    assert sql('SELECT hg_engagement_campaign_config(%s,%s,%s)',(admin,c,Json(cfg)),True)['campaign']['revision']==3
    assert sql('SELECT hg_enqueue_engagement_campaign(%s,3,%s,%s,%s)',(cid,slot,Json([good]),expires),True)['queued']==0
    assert sql('SELECT count(*) FROM hg_internal.engagement_campaign_history WHERE campaign_id=%s',(cid,),True)==3
    assert sql("SELECT has_function_privilege('anon','hg_enqueue_engagement_campaign(uuid,integer,text,jsonb,timestamptz)','EXECUTE')",one=True) is False
    assert sql("SELECT has_table_privilege('authenticated','hg_internal.engagement_campaign_receipts','SELECT')",one=True) is False
    print('PASS paused/edit-invalidated notices, optimistic edits, re-enable cannot resend occurrence, history and private grants',flush=True)
finally:
    sql('DELETE FROM notification_deliveries WHERE notification_id IN (SELECT notification_id FROM hg_internal.engagement_campaign_receipts WHERE campaign_id=%s)',(cid,))
    sql('DELETE FROM notifications WHERE id IN (SELECT notification_id FROM hg_internal.engagement_campaign_receipts WHERE campaign_id=%s)',(cid,))
    sql('DELETE FROM hg_internal.engagement_campaign_receipts WHERE campaign_id=%s',(cid,))
    sql('DELETE FROM hg_internal.engagement_campaign_history WHERE campaign_id=%s',(cid,))
    sql('DELETE FROM hg_internal.engagement_campaigns WHERE id=%s',(cid,))
    ids=[admin,student,other,boss,optout,cm]
    sql('DELETE FROM device_tokens WHERE user_id=ANY(%s::uuid[])',(ids,));sql('DELETE FROM notification_preferences WHERE user_id=ANY(%s::uuid[])',(ids,))
    sql('DELETE FROM profiles WHERE id=ANY(%s::uuid[])',(ids,));sql('DELETE FROM auth.users WHERE id=ANY(%s::uuid[])',(ids,));sql('DELETE FROM campuses WHERE id IN (%s,%s)',(c,c2))
