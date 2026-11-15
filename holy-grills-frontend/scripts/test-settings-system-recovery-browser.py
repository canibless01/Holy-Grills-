"""Native Settings/System read/write recovery with controlled HTTP; no live mutation/job."""
import json,os,signal,subprocess,tempfile,time
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1];C='11111111-1111-4111-8111-111111111111';OLD='2026-11-15T10:00:00+00:00';NEW='2026-11-15T11:00:00+00:00'
log=Path(tempfile.mkdtemp())/'vite.log';proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5284','--strictPort'],cwd=ROOT,env=dict(os.environ,VITE_API_BASE_URL='/api'),stdout=log.open('w'),stderr=subprocess.STDOUT,start_new_session=True)
try:
 time.sleep(2)
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);expect.set_options(timeout=12000)
  for width in (393,1280):
   state={'patches':[],'settings_fail':False,'conflict':False,'cron_fail':True,'audit_fail':True,'held':[],'role':'super_admin'};errors=[]
   rows=[{'key':'campus_cart_recovery','value':{'initial_minutes':30,'repeat_minutes':1440,'max_hours':48},'campus_id':None,'updated_at':OLD,'is_public':False},{'key':'signup_bonus_hp','value':50,'campus_id':C,'updated_at':OLD,'is_public':True},{'key':'support_address','value':'Old hostel','campus_id':None,'updated_at':OLD,'is_public':True}]
   def api(route):
    r=route.request;u=urlparse(r.url);path=u.path;data={}
    if path.endswith('/auth/me'):data={'id':C,'full_name':'Audit admin','role':state['role'],'campus_id':C,'is_active':True}
    elif path.endswith('/campuses'):data=[{'id':C,'name':'Campus A','is_active':True}]
    elif path.endswith('/admin/settings') and r.method=='GET':
     if state['settings_fail']:route.fulfill(status=503,json={'error':'Controlled settings read failure'});return
     data={'settings':rows}
    elif '/admin/settings/' in path and r.method=='PATCH':
     body=r.post_data_json;state['patches'].append(body)
     if state['conflict']:state['conflict']=False;route.fulfill(status=409,json={'error':'This setting changed. Reload latest settings.'});return
     key=path.split('/')[-1];row=next(x for x in rows if x['key']==key);row.update(value=body['value'],updated_at=NEW);data={'message':'Setting updated'}
    elif path.endswith('/admin/cron/status'):
     if state['cron_fail']:state['cron_fail']=False;route.fulfill(status=503,json={'error':'Controlled cron read failure'});return
     data={'jobs':{'birthday-hp':{'status':'ok','cadence':'daily','last_triggered':OLD},'monthly-birthday-report':{'status':'never_run','cadence':'monthly'}}}
    elif '/admin/cron/' in path and r.method=='POST':state['held'].append(route);return
    elif path.endswith('/health'):data={'status':'ok','checks':{'redis':'connected','supabase':'connected','supabase_auth':'connected'},'revision':'controlled'}
    elif path.endswith('/admin/audit-log'):
     if state['audit_fail']:state['audit_fail']=False;route.fulfill(status=503,json={'error':'Controlled audit read failure'});return
     offset=int(parse_qs(u.query).get('offset',['0'])[0]);data={'logs':[] if offset else [{'id':str(n),'action':'saved_setting','entity_type':'system_settings','entity_id':str(n),'after_value':{'value':n}} for n in range(15)]}
    elif path.endswith('/messages'):data={'messages':{}}
    elif path.endswith('/cart'):data={'items':[]}
    route.fulfill(json=data)
   ctx=browser.new_context(viewport={'width':width,'height':1000});ctx.route('**/api/**',api);ctx.route('https://*.onesignal.com/**',lambda r:r.abort());ctx.add_init_script(f"sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_role','super_admin');localStorage.setItem('hg_user_campus_id','{C}');localStorage.setItem('hg_admin_scope_all','1');localStorage.setItem('hg_cookie_consent',JSON.stringify({{essential:true,analytics:false,date:new Date().toISOString()}}));")
   page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto('http://127.0.0.1:5284/admin?section=settings')
   group=page.get_by_role('group',name='campus_cart_recovery global',exact=True);group.get_by_role('button',name='Edit',exact=True).click();field=page.get_by_label('campus_cart_recovery value');field.fill('{');group.get_by_role('button',name='Save',exact=True).click();expect(page.get_by_role('alert').first).to_be_visible();expect(field).to_have_value('{');assert not state['patches']
   field.fill('{"initial_minutes":45,"repeat_minutes":1440,"max_hours":48}');state['conflict']=True;group.get_by_role('button',name='Save',exact=True).click();expect(field).to_have_value('{"initial_minutes":45,"repeat_minutes":1440,"max_hours":48}');expect(page.get_by_role('alert').first).to_contain_text('changed');assert state['patches'][-1]['expected_updated_at']==OLD
   page.get_by_role('button',name='Reload latest settings').click();group.get_by_role('button',name='Save',exact=True).click();expect(group.get_by_role('button',name='Edit',exact=True)).to_be_visible();assert state['patches'][-1]['value']['initial_minutes']==45
   group=page.get_by_role('group',name='support_address global',exact=True);group.get_by_role('button',name='Edit',exact=True).click();page.get_by_label('support_address value').fill('Room 2, West Gate');group.get_by_role('button',name='Save',exact=True).click();expect(group.get_by_text('Room 2, West Gate',exact=True)).to_be_visible();assert state['patches'][-1]['value']=='Room 2, West Gate'
   page.goto('http://127.0.0.1:5284/admin?section=system');expect(page.get_by_role('alert').first).to_contain_text('cron read failure');expect(page.get_by_text('No cron status available',exact=True)).to_have_count(0);page.get_by_role('button',name='Retry',exact=True).click();runs=page.get_by_role('button',name='Run',exact=True);expect(runs.first).to_be_enabled();runs.first.click();expect(runs.last).to_be_disabled();assert len(state['held'])==1;state['held'].pop().fulfill(status=202,json={'status':'started','note':'Job started in background'});expect(runs.first).to_be_enabled()
   page.get_by_role('button',name='Health',exact=True).click();expect(page.get_by_text('connected',exact=True)).to_have_count(3);expect(page.get_by_text('No data',exact=True)).to_have_count(0)
   page.get_by_role('button',name='Audit Log',exact=True).click();expect(page.get_by_role('alert').first).to_contain_text('audit read failure');expect(page.get_by_text('No audit entries',exact=True)).to_have_count(0);page.get_by_role('button',name='Retry',exact=True).click();expect(page.get_by_role('button',name='Payload',exact=True)).to_have_count(15)
   page.get_by_role('button',name='Next',exact=True).click();expect(page.get_by_role('button',name='Prev',exact=True)).to_be_enabled();page.get_by_role('button',name='Prev',exact=True).click();expect(page.get_by_role('button',name='Payload',exact=True)).to_have_count(15)
   assert not errors,errors;ctx.close();print(f'PASS {width}: JSON error and stale-edit draft recovery, structured/text types, cron failure/retry/run guard, nested health checks, audit failure/retry/empty-page navigation',flush=True)
  browser.close()
finally:
 os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
