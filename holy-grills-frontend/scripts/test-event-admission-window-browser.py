"""Native admission opening controls; controlled API only."""
import os,signal,subprocess,tempfile,time
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
repo=Path(__file__).resolve().parents[1];out=Path(tempfile.mkdtemp(prefix='hg-event-operations-'))
C='11111111-1111-4111-8111-111111111111';E='22222222-2222-4222-8222-222222222222';OWNER='33333333-3333-4333-8333-333333333333'
expect.set_options(timeout=15000)
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5284','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
try:
 time.sleep(2)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  for width in (393,1280):
   state={'loss':True,'stale':False,'requests':{},'role':'super_admin','event':{'id':E,'title':'Event lifecycle journey','organizer_id':OWNER,'campus_id':C,'review_status':'approved','is_published':True,'starts_at':'2027-12-01T09:00:00Z','ends_at':'2027-12-01T12:00:00Z','updated_at':'2026-11-09T10:00:00Z','location':'Old hall','metadata':{},'hp_per_attendee':50}};writes=[];errors=[]
   def api(route):
    r=route.request;path=urlparse(r.url).path;data={}
    if path.endswith('/auth/me'):data={'id':OWNER,'role':state['role'],'campus_id':C,'is_active':True,'profile':{'id':OWNER,'role':state['role'],'campus_id':C}}
    elif path.endswith('/campuses'):data=[{'id':C,'name':'FUTA','is_active':True}]
    elif path.endswith('/feature-flags'):data=[{'feature_name':'events','is_active':True}]
    elif path=='/api/event-organizer/events':data={'events':[state['event']],'has_more':False}
    elif path.endswith('/admission-window'):
     body=r.post_data_json;writes.append(body);state['event']['metadata']['checkin_minutes_before_start']=body['minutes']
     if state['loss']:state['loss']=False;route.fulfill(status=503,json={'error':'Controlled lost committed response'});return
     data={'minutes':body['minutes'],'replayed':len(writes)>1}
    elif path.endswith('/change'):
     body=r.post_data_json;writes.append(body)
     if state['stale']:
      state['stale']=False;state['event']['updated_at']='2026-11-09T11:30:00Z';route.fulfill(status=409,json={'error':'This event changed in another session. Refresh its details before trying again.','code':'event_changed'});return
     if body['request_id'] not in state['requests']:
      state['requests'][body['request_id']]=body;state['event']['metadata']={'lifecycle_status':'cancelled' if body['action']=='cancel' else 'rescheduled','latest_change_id':body['request_id'],'change_reason':body['reason']};state['event']['updated_at']='2026-11-09T11:00:00Z'
      if body['action']=='reschedule':state['event'].update(starts_at=body['starts_at'],ends_at=body['ends_at'],location=body['location'])
     else:assert body==state['requests'][body['request_id']]
     if state['loss']:state['loss']=False;route.fulfill(status=503,json={'error':'Controlled lost committed response'});return
     data={'id':body['request_id'],'action':body['action'],'refunds':2,'free_cancelled':1,'awaiting_payment':1}
    elif path.endswith('/attendees'):data={'attendees':[]}
    elif path.startswith('/api/event-organizer/events/'):
     data={'event':state['event'],'tiers':[],'counts':{'confirmed':2,'pending':1},'earned':0,'paid':0,'reserved':0,'available':0,'requests':[]}
    elif path=='/api/events/'+E:data=state['event']
    elif path.endswith('/tiers'):data=[]
    route.fulfill(json=data)
   ctx=browser.new_context(viewport={'width':width,'height':1000});ctx.route('**/api/**',api)
   ctx.add_init_script("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_role','super_admin');localStorage.setItem('hg_admin_scope_all','1');localStorage.setItem('hg_cookie_consent',JSON.stringify({essential:true,analytics:false,date:new Date().toISOString()}));")
   page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto('http://127.0.0.1:5284/event-manager?event='+E)
   panel=page.get_by_role('region',name='Check-in opening time',exact=True);expect(panel).to_be_visible();expect(panel.get_by_text('No opening-time restriction is set.',exact=True)).to_be_visible();panel.get_by_label('Set an opening time',exact=True).check();field=panel.get_by_label('Minutes before event start',exact=True);field.fill('-1');panel.get_by_role('button',name='Save check-in opening time',exact=True).click();assert not writes
   field.fill('45');panel.get_by_role('button',name='Save check-in opening time',exact=True).evaluate('(b)=>{b.click();b.click()}');expect(panel.get_by_role('alert')).to_contain_text('Controlled lost committed response');assert len(writes)==1
   panel.get_by_role('button',name='Save check-in opening time',exact=True).click();expect(panel.get_by_role('status')).to_contain_text('Check-in opening time saved.');assert writes==[{'minutes':45},{'minutes':45}];expect(field).to_have_value('45')
   page.goto('http://127.0.0.1:5284/events/'+E);expect(page.get_by_text('Opens:',exact=False)).to_contain_text('9:15');assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
   page.goto('http://127.0.0.1:5284/event-manager?event='+E);panel=page.get_by_role('region',name='Check-in opening time',exact=True);panel.get_by_label('Set an opening time',exact=True).uncheck();panel.get_by_role('button',name='Save check-in opening time',exact=True).click();expect(panel.get_by_text('No opening-time restriction is set.',exact=True)).to_be_visible();assert writes[-1]=={'minutes':None};assert not errors,errors;ctx.close();print(f'PASS {width}: opening editor validation, duplicate click, response-loss retry, public WAT time, clear restriction',flush=True)
  browser.close()
finally:os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
