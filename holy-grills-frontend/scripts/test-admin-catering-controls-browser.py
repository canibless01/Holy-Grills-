"""Native catering staff/quote/status/version controls. Controlled transport only."""
import json,os
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('HG_BROWSER_BASE','http://127.0.0.1:4185');C='70000001-cafe-cafe-cafe-000000000001';U='11111111-1111-4111-8111-111111111111';R='22222222-2222-4222-8222-222222222222';K='33333333-3333-4333-8333-333333333333';V='2026-11-15T10:00:00+00:00'
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for width in (393,1280):
  state={'row':{'id':R,'campus_id':C,'organizer_name':'Fixture organizer','email':'fixture@example.invalid','phone':'08012345678','event_name':'Fixture catering','event_date':'2026-12-01','expected_guests':30,'status':'new','notes':'','quoted_amount':None,'assigned_to':None,'updated_at':V},'staff_fail':True,'writes':[],'held':[],'conflict':True};errors=[]
  ctx=browser.new_context(viewport={'width':width,'height':1000});ctx.add_init_script(f"localStorage.setItem('hg_access_token','synthetic');localStorage.setItem('hg_user_role','admin');localStorage.setItem('hg_campus_id','{C}');localStorage.setItem('hg_user_campus_id','{C}');localStorage.setItem('hg_cookie_consent',JSON.stringify({{essential:true,analytics:false,date:new Date().toISOString()}}));")
  def api(route):
   req=route.request;url=urlparse(req.url);path=url.path;q=parse_qs(url.query);data={}
   if path.endswith('/auth/me'):data={'id':U,'full_name':'Audit admin','role':'admin','campus_id':C}
   elif path.endswith('/campuses'):data={'campuses':[{'id':C,'name':'FUTA','slug':'futa','is_active':True}]}
   elif path.endswith('/admin/users'):
    assert q['campus_id']==[C]
    if q.get('role')==['kitchen'] and state['staff_fail']:route.fulfill(status=503,json={'error':'Controlled staff failure'});return
    data={'users':[{'id':K,'full_name':'Named kitchen staff','role':'kitchen','campus_id':C,'is_active':True},{'id':U,'full_name':'Inactive staff','role':'admin','campus_id':C,'is_active':False},{'id':R,'full_name':'Foreign staff','role':'kitchen','campus_id':R,'is_active':True}]} if q.get('role')==['kitchen'] else []
   elif path.endswith('/events/catering-requests'):data={'requests':[state['row']]}
   elif '/events/catering-requests/' in path:
    body=req.post_data_json;state['writes'].append(body)
    if len(state['writes'])==1:state['held'].append(route);return
    if body['status']=='cancelled' and state['conflict']:
     state['conflict']=False;state['row'].update(status='confirmed',updated_at='2026-11-15T12:00:00+00:00');route.fulfill(status=409,json={'error':'This catering request changed. Close it, refresh the list and reopen it before saving.'});return
    assert body['expected_updated_at']==state['row']['updated_at'];state['row'].update({k:v for k,v in body.items() if k!='expected_updated_at'});state['row']['updated_at']='2026-11-15T11:00:00+00:00' if body['status']=='quoted' else '2026-11-15T13:00:00+00:00';data=state['row']
   elif path.endswith('/events/admin'):
    route.fulfill(status=503,json={'error':'Controlled unrelated event failure'});return
   elif '/notifications' in path:data={'notifications':[]}
   else:data=[]
   route.fulfill(status=200,json=data)
  ctx.route('**/api/**',api);ctx.route('https://*.onesignal.com/**',lambda r:r.abort())
  page=ctx.new_page();page.set_default_timeout(15000);page.on('pageerror',lambda e:errors.append(str(e)));page.goto(BASE+'/admin?section=catering',wait_until='domcontentloaded',timeout=30000);page.get_by_role('button').filter(has_text='Fixture organizer').click();dialog=page.get_by_role('dialog',name='Catering Request',exact=True);expect(dialog.get_by_role('alert')).to_contain_text('Staff could not be loaded.');expect(dialog.get_by_role('button',name='Save Changes',exact=True)).to_be_disabled();state['staff_fail']=False;dialog.get_by_role('button',name='Retry',exact=True).click();staff=dialog.get_by_label('Assign to staff',exact=True);expect(staff).to_be_enabled();assert 'Inactive staff' not in staff.inner_text() and 'Foreign staff' not in staff.inner_text();staff.select_option(K)
  dialog.get_by_label('Status',exact=True).select_option('quoted');quote=dialog.get_by_label('Quoted Amount (₦)',exact=True);quote.fill('-1');dialog.get_by_role('button',name='Save Changes',exact=True).click();assert not state['writes'];quote.fill('0');dialog.get_by_label('Admin Notes',exact=True).fill('Private preparation notes');dialog.get_by_role('button',name='Save Changes',exact=True).click();expect(dialog.get_by_role('button',name='Close catering request',exact=True)).to_be_disabled();dialog.evaluate('(form)=>form.requestSubmit()');assert len(state['writes'])==1
  state['held'][0].fulfill(status=503,json={'error':'Controlled save failure'});expect(page.get_by_text('Controlled save failure',exact=True)).to_be_visible();expect(quote).to_have_value('0');expect(staff).to_have_value(K);dialog.get_by_role('button',name='Save Changes',exact=True).click();expect(dialog).not_to_be_visible();assert state['writes'][0]==state['writes'][1] and state['row']['quoted_amount']==0
  page.get_by_role('button').filter(has_text='Fixture organizer').click();dialog=page.get_by_role('dialog');dialog.get_by_label('Status',exact=True).select_option('cancelled');dialog.get_by_role('button',name='Save Changes',exact=True).click();expect(page.get_by_text('This catering request changed. Close it, refresh the list and reopen it before saving.',exact=True)).to_be_visible();expect(dialog).to_be_visible();dialog.get_by_role('button',name='Close catering request',exact=True).click();page.get_by_role('button',name='Refresh catering requests',exact=True).click();page.get_by_role('button').filter(has_text='Fixture organizer').click();dialog=page.get_by_role('dialog');expect(dialog.get_by_label('Status',exact=True)).to_have_value('confirmed');dialog.get_by_label('Status',exact=True).select_option('cancelled');dialog.get_by_role('button',name='Save Changes',exact=True).click();expect(dialog).not_to_be_visible();assert state['row']['status']=='cancelled' and state['writes'][-1]['expected_updated_at']=='2026-11-15T12:00:00+00:00'
  assert not errors,errors
  print(json.dumps({'width':width,'passed':True,'production_writes':0}),flush=True);ctx.close()
 browser.close()
