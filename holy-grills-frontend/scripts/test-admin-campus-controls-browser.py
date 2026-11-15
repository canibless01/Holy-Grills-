"""Native campus editor lifecycle and role controls, using controlled transport only."""
import copy,json,os
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('HG_BROWSER_BASE','http://127.0.0.1:4185');A='11111111-1111-4111-8111-111111111111';U='22222222-2222-4222-8222-222222222222';STAMP='2026-11-15T10:00:00+00:00'
expect.set_options(timeout=20000)
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for role,width in [('super_admin',393),('super_admin',1280),('admin',393),('community_manager',1280)]:
  state={'fail':True,'save_fail':True,'hold':False,'held':[],'writes':[],'rows':[{'id':A,'name':'Campus A','slug':'campus-a','is_default':True,'is_active':True,'updated_at':STAMP}]};errors=[]
  ctx=browser.new_context(viewport={'width':width,'height':1000});ctx.add_init_script(f"localStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_role','{role}');localStorage.setItem('hg_user_campus_id','{A}');localStorage.setItem('hg_admin_scope_all','true');localStorage.setItem('hg_cookie_consent',JSON.stringify({{essential:true,analytics:false,date:new Date().toISOString()}}));")
  def api(route):
   req=route.request;path=urlparse(req.url).path;data={}
   if path.endswith('/auth/me'):data={'id':U,'full_name':'Fixture staff','role':role,'campus_id':A}
   elif path.endswith('/campuses') and not path.endswith('/admin/campuses'):data=[r for r in state['rows'] if r['is_active']]
   elif path.endswith('/admin/campuses') and req.method=='GET':
    if state['fail']:route.fulfill(status=503,json={'error':'Controlled campus outage'});return
    data=state['rows']
   elif path.endswith('/admin/campuses') and req.method=='POST':
    body=req.post_data_json;state['writes'].append(copy.deepcopy(body));assert role=='super_admin';data=next((r for r in state['rows'] if r['id']==body['request_id']),None)
    if not data:
     data={'id':body['request_id'],'name':body['name'],'slug':body['slug'],'is_active':body['is_active'],'is_default':False,'updated_at':STAMP};state['rows'].append(data)
    if state['save_fail']:route.fulfill(status=503,json={'error':'Controlled lost response'});return
   elif '/admin/campuses/' in path and req.method=='PATCH':
    body=req.post_data_json;state['writes'].append(copy.deepcopy(body));assert role=='super_admin' and body['expected_updated_at']==STAMP
    data=next(r for r in state['rows'] if r['id']==path.rsplit('/',1)[-1]);data.update({k:v for k,v in body.items() if k!='expected_updated_at'})
    if state['hold']:state['held'].append((route,copy.deepcopy(data)));return
   elif '/notifications' in path:data={'notifications':[]}
   elif 'cart' in path:data={'items':[]}
   elif any(x in path for x in ('orders','feature-flags','tiers','ambassadors','sections','banners')):data=[]
   route.fulfill(status=200,json=data)
  ctx.route('**/api/**',api);ctx.route('https://*.onesignal.com/**',lambda r:r.abort());page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto(BASE+'/admin?section=campuses',wait_until='domcontentloaded')
  if role=='community_manager':
   expect(page.get_by_role('heading',name='Campus Ambassadors',exact=True).first).to_be_visible();assert not state['writes'];expect(page.get_by_role('button',name='Add campus',exact=True)).to_have_count(0)
  else:
   expect(page.get_by_role('button',name='Retry',exact=True)).to_be_visible();state['fail']=False;page.get_by_role('button',name='Retry',exact=True).click();expect(page.get_by_text('Campus A',exact=True).last).to_be_visible()
   if role=='admin':
    expect(page.get_by_text('Campus names and availability are managed by super admins.',exact=True)).to_be_visible();expect(page.get_by_role('button',name='Add campus',exact=True)).to_have_count(0);expect(page.get_by_role('button',name='Edit campus',exact=True)).to_have_count(0)
   else:
    page.get_by_role('button',name='Add campus',exact=True).click();dialog=page.get_by_role('dialog');save=dialog.get_by_role('button',name='Save campus',exact=True);expect(save).to_be_disabled();dialog.get_by_label('Campus name',exact=True).fill('Fixture campus');dialog.get_by_label('Campus slug',exact=True).fill('BAD Slug');expect(save).to_be_disabled();dialog.get_by_label('Campus slug',exact=True).fill('fixture-campus');save.click();expect(page.get_by_text('Controlled lost response',exact=True)).to_be_visible();expect(dialog.get_by_label('Campus name',exact=True)).to_have_value('Fixture campus');state['save_fail']=False;save.click();expect(dialog).to_have_count(0);assert state['writes'][0]==state['writes'][1] and len(state['rows'])==2
    card=page.get_by_text('Fixture campus',exact=True).locator('..').locator('..');card.get_by_role('button',name='Edit campus',exact=True).click();dialog=page.get_by_role('dialog');dialog.get_by_label('Campus name',exact=True).fill('Renamed campus');dialog.get_by_label('Active',exact=True).uncheck();state['hold']=True;dialog.get_by_role('button',name='Save campus',exact=True).click();expect(dialog.get_by_role('button',name='Save campus',exact=True)).to_be_disabled();expect(dialog.get_by_label('Campus name',exact=True)).to_be_disabled();dialog.get_by_role('button',name='Close dialog',exact=True).click();expect(dialog).to_be_visible()
    for _ in range(100):
     if state['held']:break
     page.wait_for_timeout(100)
    assert len(state['held'])==1 and len(state['writes'])==3;state['held'][0][0].fulfill(status=200,json=state['held'][0][1]);expect(dialog).to_have_count(0);expect(page.get_by_text('Renamed campus',exact=True)).to_be_visible();assert not state['rows'][1]['is_active'];state['hold']=False
    default=page.get_by_text('Campus A',exact=True).last.locator('..').locator('..');default.get_by_role('button',name='Edit campus',exact=True).click();expect(page.get_by_role('dialog').get_by_label('Active',exact=True)).to_be_disabled();page.get_by_role('dialog').get_by_role('button',name='Close dialog',exact=True).click();expect(page.get_by_role('dialog')).to_have_count(0);page.reload(wait_until='domcontentloaded');expect(page.get_by_text('Renamed campus',exact=True)).to_be_visible()
  assert not errors,errors;assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');ctx.close();print(json.dumps({'role':role,'width':width,'passed':True,'production_writes':0}),flush=True)
 browser.close()
