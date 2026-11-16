"""Actual Hall-of-Fame transition modal/actions; fixture requests only, no real prizes."""
import copy,json,os
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('HG_BROWSER_BASE','http://127.0.0.1:4185');A='11111111-1111-4111-8111-111111111111';U='22222222-2222-4222-8222-222222222222';P='33333333-3333-4333-8333-333333333333';Q='44444444-4444-4444-8444-444444444444'
expect.set_options(timeout=20000)
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for width in (393,1280):
  state={'rows':[{'id':P,'full_name':'Alpha winner','status':'pending'},{'id':Q,'full_name':'Beta winner','status':'pending'},{'id':U,'full_name':'Cancelled winner','status':'cancelled'}],'fail':True,'hold':False,'held':[],'writes':[]};errors=[]
  ctx=browser.new_context(viewport={'width':width,'height':1000});ctx.add_init_script(f"localStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_role','admin');localStorage.setItem('hg_user_campus_id','{A}');localStorage.setItem('hg_cookie_consent',JSON.stringify({{essential:true,analytics:false,date:new Date().toISOString()}}));")
  def api(route):
   req=route.request;path=urlparse(req.url).path;data={}
   if path.endswith('/auth/me'):data={'id':U,'full_name':'Fixture admin','role':'admin','campus_id':A}
   elif path.endswith('/campuses'):data=[{'id':A,'name':'Campus A','is_active':True}]
   elif path.endswith('/admin/leaderboard-prizes'):data=[]
   elif path.endswith('/admin/hall-of-fame-rewards'):data=state['rows']
   elif '/admin/hall-of-fame-rewards/' in path:
    assert req.headers.get('x-campus-id')==A;body=req.post_data_json;state['writes'].append(copy.deepcopy(body))
    if state['fail']:route.fulfill(status=409,json={'error':'Controlled stale prize transition'});return
    row=next(r for r in state['rows'] if r['id']==path.rsplit('/',1)[-1]);row.update(body);data={'message':'Fixture transition recorded'}
    if state['hold']:state['held'].append((route,data));return
   elif '/notifications' in path:data={'notifications':[]}
   else:data=[]
   route.fulfill(status=200,json=data)
  ctx.route('**/api/**',api);ctx.route('https://*.onesignal.com/**',lambda r:r.abort());page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto(BASE+'/admin?section=leaderboard',wait_until='domcontentloaded');page.get_by_role('button',name='Hall of Fame',exact=True).click();expect(page.get_by_text('2 pending',exact=True)).to_be_visible();expect(page.get_by_text('Cancelled winner',exact=True)).to_be_visible()
  def card(name):return page.get_by_text(name,exact=True).locator('..').locator('..')
  card('Alpha winner').get_by_role('button',name='Box prepared',exact=True).click();dialog=page.get_by_role('dialog');notes=dialog.get_by_placeholder('e.g. Box handed to student');notes.fill('Prepared at pickup desk');dialog.get_by_role('button',name='Mark box prepared',exact=True).click();expect(page.get_by_text('Controlled stale prize transition',exact=True)).to_be_visible();expect(notes).to_have_value('Prepared at pickup desk');state['fail']=False;state['hold']=True;dialog.get_by_role('button',name='Mark box prepared',exact=True).click();expect(dialog.get_by_role('button',name='Updating...',exact=True)).to_be_disabled();expect(notes).to_be_disabled();dialog.get_by_role('button',name='Close dialog',exact=True).click();expect(dialog).to_be_visible();expect(card('Beta winner').get_by_role('button',name='Cancel',exact=True)).to_be_disabled()
  for _ in range(100):
   if state['held']:break
   page.wait_for_timeout(100)
  assert len(state['writes'])==2 and state['writes'][0]==state['writes'][1];state['held'][0][0].fulfill(status=200,json=state['held'][0][1]);expect(dialog).to_have_count(0);expect(card('Alpha winner').get_by_text('Box prepared',exact=True)).to_be_visible();state['hold']=False
  card('Alpha winner').get_by_role('button',name='Fulfill',exact=True).click();dialog=page.get_by_role('dialog');dialog.get_by_placeholder('e.g. Box handed to student').fill('Handed to verified winner');dialog.get_by_role('button',name='Mark fulfilled',exact=True).click();expect(page.get_by_role('dialog')).to_have_count(0);expect(page.get_by_text('1 pending',exact=True)).to_be_visible();expect(card('Alpha winner').get_by_text('Fulfilled',exact=True)).to_be_visible()
  card('Beta winner').get_by_role('button',name='Cancel',exact=True).click();page.get_by_role('dialog').get_by_placeholder('e.g. Box handed to student').fill('Owner-authorized cancellation');page.get_by_role('dialog').get_by_role('button',name='Mark cancelled',exact=True).click();expect(page.get_by_role('dialog')).to_have_count(0);expect(page.get_by_text('0 pending',exact=True)).to_be_visible();expect(card('Beta winner').get_by_text('Cancelled',exact=True)).to_be_visible();assert len(state['writes'])==4
  page.reload(wait_until='domcontentloaded');page.get_by_role('button',name='Hall of Fame',exact=True).click();expect(page.get_by_text('0 pending',exact=True)).to_be_visible();assert not page.get_by_role('button',name='Box prepared',exact=True).count();assert not page.get_by_role('button',name='Fulfill',exact=True).count();assert not page.get_by_role('button',name='Cancel',exact=True).count();assert not errors,errors;assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');ctx.close();print(json.dumps({'width':width,'passed':True,'production_writes':0}),flush=True)
 browser.close()
