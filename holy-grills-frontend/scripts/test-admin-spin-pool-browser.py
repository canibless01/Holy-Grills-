"""Real spin-prize editor with controlled lost replies, pending fields and stale edits."""
import copy,json,os
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('HG_BROWSER_BASE','http://127.0.0.1:4185');A='11111111-1111-4111-8111-111111111111';U='22222222-2222-4222-8222-222222222222';P='33333333-3333-4333-8333-333333333333';STAMP='2026-11-15T10:00:00+00:00';NEWSTAMP='2026-11-15T11:00:00+00:00'
expect.set_options(timeout=20000)
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for role,width in [('super_admin',393),('super_admin',1280),('admin',393)]:
  state={'fail_read':True,'fail_create':True,'hold':False,'held':[],'writes':[],'rows':[{'id':P,'name':'Global prize','weight':5,'is_active':True,'campus_id':None,'reward_config':{'kind':'physical'},'updated_at':STAMP}]};errors=[]
  ctx=browser.new_context(viewport={'width':width,'height':1100});ctx.add_init_script(f"localStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_role','{role}');localStorage.setItem('hg_user_campus_id','{A}');localStorage.setItem('hg_admin_scope_all','true');localStorage.setItem('hg_cookie_consent',JSON.stringify({{essential:true,analytics:false,date:new Date().toISOString()}}));")
  def api(route):
   req=route.request;path=urlparse(req.url).path;data={}
   if path.endswith('/auth/me'):data={'id':U,'full_name':'Fixture staff','role':role,'campus_id':A}
   elif path.endswith('/campuses'):data=[{'id':A,'name':'Campus A','is_active':True}]
   elif path.endswith('/admin/exclusive-spin-pool') and req.method=='GET':
    if state['fail_read']:route.fulfill(status=503,json={'error':'Controlled pool outage'});return
    data={'prizes':state['rows'],'credit_validity_days':30}
   elif path.endswith('/admin/exclusive-spin-pool') and req.method=='POST':
    body=req.post_data_json;state['writes'].append(copy.deepcopy(body));data=next((r for r in state['rows'] if r['id']==body['request_id']),None)
    if not data:data={**body,'id':body['request_id'],'updated_at':STAMP};state['rows'].append(data)
    if state['fail_create']:route.fulfill(status=503,json={'error':'Controlled lost create response'});return
    if state['hold']:state['held'].append((route,data));return
   elif '/admin/exclusive-spin-pool/' in path and req.method=='PATCH':
    body=req.post_data_json;state['writes'].append(copy.deepcopy(body));data=next(r for r in state['rows'] if r['id']==path.rsplit('/',1)[-1])
    if body['expected_updated_at']!=data['updated_at']:route.fulfill(status=409,json={'error':'Controlled stale prize'});return
    data.update(body)
   elif path.endswith('/admin/exclusive-spin-prizes'):data=[]
   elif '/notifications' in path:data={'notifications':[]}
   else:data=[]
   route.fulfill(status=200,json=data)
  ctx.route('**/api/**',api);ctx.route('https://*.onesignal.com/**',lambda r:r.abort());page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto(BASE+'/admin?section=exclusivespin',wait_until='domcontentloaded');expect(page.get_by_role('alert').filter(has_text='Controlled pool outage')).to_be_visible();state['fail_read']=False;page.get_by_role('button',name='Retry',exact=True).click();expect(page.get_by_role('button',name='Edit Global prize',exact=True)).to_be_visible()
  if role=='admin':expect(page.get_by_role('button',name='Edit Global prize',exact=True)).to_be_disabled()
  page.get_by_role('button',name='Add Prize',exact=True).click();dialog=page.get_by_role('dialog');name=dialog.get_by_label('Prize Name',exact=True);weight=dialog.get_by_label('Relative weight',exact=True);kind=dialog.get_by_label('Reward category',exact=True);save=dialog.get_by_role('button',name='Save Prize',exact=True);expect(save).to_be_disabled();name.fill('Fixture new prize');weight.fill('15')
  scope=dialog.get_by_label('Campus Scope',exact=True);expect(scope).to_have_value('' if role=='super_admin' else A)
  if role=='admin':expect(scope).to_be_disabled()
  for category,label,value in [('free_delivery','Delivery fee cap (₦)','150'),('hp_multiplier','HP multiplier','2.5'),('hp','HP amount','40')]:
   kind.select_option(category);dialog.get_by_label(label,exact=True).fill(value)
  save.click();expect(page.get_by_text('Controlled lost create response',exact=True)).to_be_visible();expect(name).to_have_value('Fixture new prize');state['fail_create']=False;state['hold']=True;save.click();expect(dialog.get_by_role('button',name='Saving...',exact=True)).to_be_disabled();expect(name).to_be_disabled();expect(weight).to_be_disabled();expect(kind).to_be_disabled();dialog.get_by_role('button',name='Close dialog',exact=True).click();expect(dialog).to_be_visible()
  for _ in range(100):
   if state['held']:break
   page.wait_for_timeout(100)
  assert len(state['writes'])==2 and state['writes'][0]==state['writes'][1] and len(state['rows'])==2;assert state['writes'][0]['reward_config']=={'kind':'hp','amount':40};state['held'][0][0].fulfill(status=200,json=state['held'][0][1]);expect(dialog).to_have_count(0);state['hold']=False
  page.get_by_role('button',name='Edit Fixture new prize',exact=True).click();dialog=page.get_by_role('dialog');dialog.get_by_label('Prize Name',exact=True).fill('My draft');state['rows'][1].update(name='Concurrent name',updated_at=NEWSTAMP);dialog.get_by_role('button',name='Save Prize',exact=True).click();expect(page.get_by_text('Controlled stale prize',exact=True)).to_be_visible();expect(dialog.get_by_label('Prize Name',exact=True)).to_have_value('My draft');dialog.get_by_role('button',name='Reload prize pool',exact=True).click();expect(page.get_by_role('dialog')).to_have_count(0);page.get_by_role('button',name='Edit Concurrent name',exact=True).click();dialog=page.get_by_role('dialog');expect(dialog.get_by_label('Campus Scope',exact=True)).to_be_disabled();dialog.get_by_label('Prize Name',exact=True).fill('Reviewed new name');dialog.get_by_role('button',name='Save Prize',exact=True).click();expect(dialog).to_have_count(0);expect(page.get_by_role('button',name='Edit Reviewed new name',exact=True)).to_be_visible();assert len(state['writes'])==4 and state['writes'][-1]['expected_updated_at']==NEWSTAMP
  page.reload(wait_until='domcontentloaded');expect(page.get_by_role('button',name='Edit Reviewed new name',exact=True)).to_be_visible();assert not errors,errors;assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');ctx.close();print(json.dumps({'role':role,'width':width,'passed':True,'real_writes':0}),flush=True)
 browser.close()
