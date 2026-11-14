"""Native event lifecycle controls/customer states; controlled API only."""
import os,signal,subprocess,tempfile,time
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
repo=Path(__file__).resolve().parents[1];out=Path(tempfile.mkdtemp(prefix='hg-event-operations-'))
C='11111111-1111-4111-8111-111111111111';E='22222222-2222-4222-8222-222222222222';OWNER='33333333-3333-4333-8333-333333333333'
expect.set_options(timeout=15000)
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5274','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
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
   page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));url='http://127.0.0.1:5274/event-manager?event='+E;page.goto(url)
   panel=page.get_by_role('region',name='Schedule and cancellation',exact=True);expect(panel).to_be_visible()
   expect(panel.get_by_label('Starts (WAT)',exact=True)).to_have_value('2027-12-01T10:00')
   panel.get_by_label('Starts (WAT)',exact=True).fill('2027-12-03T10:00');panel.get_by_label('Ends (WAT)',exact=True).fill('2027-12-03T13:00');panel.get_by_label('Venue / location',exact=True).fill('New hall');panel.get_by_label('Reason sent to attendees',exact=True).fill('The venue requested a later event date.')
   panel.get_by_role('button',name='Save new schedule',exact=True).evaluate('(b)=>{b.click();b.click()}');expect(panel.get_by_role('alert')).to_contain_text('Controlled lost committed response');assert len(writes)==1
   panel.get_by_role('button',name='Save new schedule',exact=True).click();expect(panel.get_by_role('status')).to_contain_text('attendee notices have been queued');assert len(writes)==2 and writes[0]==writes[1]
   state['stale']=True;panel.get_by_label('Venue / location',exact=True).fill('Updated hall');panel.get_by_role('button',name='Save new schedule',exact=True).click();expect(panel.get_by_role('alert')).to_contain_text('changed in another session');expect(page.get_by_role('button',name='Refresh',exact=True)).to_be_enabled()
   panel.get_by_label('Event action',exact=True).select_option('cancel');page.screenshot(path=str(out/f'cancel-form-{width}.png'));panel.get_by_label('Reason sent to attendees',exact=True).fill('The host has cancelled this event entirely.');panel.get_by_role('button',name='Cancel event',exact=True).click()
   confirm=page.get_by_role('dialog',name='Cancel this event and refund unused paid tickets?',exact=True);expect(confirm).to_contain_text('payment-provider fees are excluded');confirm.get_by_role('button',name='Go back',exact=True).click();assert len(writes)==3
   panel.get_by_role('button',name='Cancel event',exact=True).click();page.get_by_role('dialog',name='Cancel this event and refund unused paid tickets?',exact=True).get_by_role('button',name='Cancel event',exact=True).click();expect(panel.get_by_text('Event cancelled',exact=True)).to_be_visible();assert len(writes)==4 and writes[-1]['expected_updated_at']=='2026-11-09T11:30:00Z'
   page.screenshot(path=str(out/f'event-cancelled-admin-{width}.png'),full_page=True)
   page.goto('http://127.0.0.1:5274/events/'+E);expect(page.get_by_role('heading',name='Event cancelled',exact=True)).to_be_visible();expect(page.get_by_role('button',name='Get Your Ticket',exact=True)).to_have_count(0);expect(page.get_by_role('button',name="I'm In",exact=True)).to_have_count(0)
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
   state['role']='event_organizer';page.goto(url);expect(page.get_by_role('heading',name='Organizer settlement',exact=True)).to_be_visible();expect(page.get_by_role('heading',name='Schedule and cancellation',exact=True)).to_have_count(0)
   assert not errors,errors
   ctx.close();print(f'PASS {width}: WAT dates, one request on double click, lost-response receipt retry, stale version refresh, cancellation confirmation/policy, customer cancelled state, organizer cannot self-cancel; screenshots={out}',flush=True)
  browser.close()
finally:os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
