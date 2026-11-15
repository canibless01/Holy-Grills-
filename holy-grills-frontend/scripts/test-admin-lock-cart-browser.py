"""Actual admin lock filters and cart recovery actions; controlled HTTP, no real reminders."""
import os,json
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('HG_BROWSER_BASE','http://127.0.0.1:4185');A='11111111-1111-4111-8111-111111111111';U='22222222-2222-4222-8222-222222222222';C='33333333-3333-4333-8333-333333333333'
expect.set_options(timeout=20000)
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for page_id in ('orderlocks','abandoned'):
  for width in (393,1280):
   state={'fail':True,'hold':False,'held':[],'reads':[],'nudges':[],'nudge_fail':True};errors=[]
   ctx=browser.new_context(viewport={'width':width,'height':1000});ctx.add_init_script(f"localStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_role','admin');localStorage.setItem('hg_user_campus_id','{A}');localStorage.setItem('hg_campus_id','{A}');localStorage.setItem('hg_cookie_consent',JSON.stringify({{essential:true,analytics:false,date:new Date().toISOString()}}));")
   def api(route):
    req=route.request;path=urlparse(req.url).path;query=parse_qs(urlparse(req.url).query);data={}
    if path.endswith('/auth/me'):data={'id':U,'full_name':'Fixture admin','role':'admin','campus_id':A}
    elif path.endswith('/campuses'):data=[{'id':A,'name':'Campus A','is_active':True}]
    elif path.endswith('/order-locks/admin/all'):
     assert req.headers.get('x-campus-id')==A;state['reads'].append(query)
     if state['fail']:route.fulfill(status=503,json={'error':'Controlled lock outage'});return
     status=query.get('status',['active'])[0];data=[{'id':C,'full_name':status.title()+' fixture','email':'lock@example.invalid','status':status,'locked_date':query.get('date',['2026-11-16'])[0],'reward_type':'hp' if status=='used' else 'discount','reward_hp_amount':125,'discount_pct':10,'order_id':U,'created_at':'2026-11-15T10:00:00Z'}]
     if state['hold']:state['held'].append((route,data));return
    elif path.endswith('/admin/abandoned-carts'):
     assert req.headers.get('x-campus-id')==A;state['reads'].append(query)
     if state['fail']:route.fulfill(status=503,json={'error':'Controlled cart outage'});return
     data=[{'id':C,'user_id':U,'profiles':{'full_name':'Pending fixture','email':'pending@example.invalid','phone':'08012345678'},'is_recovered':False,'subtotal':1250,'saved_nudges':2,'email_accepted':1,'push_accepted':0,'last_active_at':'2026-11-15T10:00:00Z','cart_payload':{'items':[{'name':'Fixture chicken','quantity':2}]}},{'id':U,'user_id':U,'profiles':{'full_name':'Recovered fixture','email':'recovered@example.invalid'},'is_recovered':True,'subtotal':500}]
     status=query.get('status',['pending'])[0]
     if status!='all':data=[r for r in data if r['is_recovered']==(status=='recovered')]
    elif path.endswith('/nudge'):
     state['nudges'].append(req.url)
     if state['hold']:state['held'].append((route,None));return
     route.fulfill(status=409 if state['nudge_fail'] else 200,json={'error':'Controlled reminder not due'} if state['nudge_fail'] else {'message':'Queued'});return
    elif '/notifications' in path:data={'notifications':[]}
    elif 'cart' in path:data={'items':[]}
    elif any(x in path for x in ('orders','feature-flags','tiers','ambassadors','sections','banners')):data=[]
    route.fulfill(status=200,json=data)
   ctx.route('**/api/**',api);ctx.route('https://*.onesignal.com/**',lambda r:r.abort());page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto(BASE+'/admin?section='+page_id,wait_until='domcontentloaded')
   expect(page.get_by_role('alert').filter(has_text='Controlled')).to_be_visible();state['fail']=False
   if page_id=='orderlocks':
    page.get_by_role('button',name='Retry',exact=True).click();expect(page.get_by_text('Active fixture',exact=True)).to_be_visible()
    state['hold']=True;page.get_by_label('Lock status',exact=True).select_option('used');expect(page.get_by_label('Locked date',exact=True)).to_be_visible();page.get_by_label('Locked date',exact=True).fill('2026-11-18')
    for _ in range(100):
     if len(state['held'])>=2:break
     page.wait_for_timeout(100)
    assert len(state['held'])>=2
    latest=state['held'][-1];latest[0].fulfill(status=200,json=latest[1]);expect(page.get_by_text('Used fixture',exact=True)).to_be_visible();expect(page.get_by_text('Locked for 2026-11-18',exact=True)).to_be_visible();expect(page.get_by_text('125 HP',exact=True)).to_be_visible()
    for route,data in state['held'][:-1]:route.fulfill(status=200,json=data)
    expect(page.get_by_text('Locked for 2026-11-18',exact=True)).to_be_visible();state['hold']=False
    for status in ('expired','cancelled','active'):
     page.get_by_label('Lock status',exact=True).select_option(status);expect(page.get_by_text(status.title()+' fixture',exact=True)).to_be_visible()
    page.get_by_label('Locked date',exact=True).fill('');page.get_by_label('Lock status',exact=True).select_option('');expect(page.get_by_text('Active fixture',exact=True)).to_be_visible()
   else:
    page.get_by_role('button',name='Refresh carts',exact=True).click();expect(page.get_by_text('Pending fixture',exact=True)).to_be_visible();expect(page.get_by_text('Recovered fixture',exact=True)).to_be_visible()
    page.get_by_label('Cart recovery status',exact=True).select_option('recovered');expect(page.get_by_text('Pending fixture',exact=True)).to_have_count(0);expect(page.get_by_text('Recovered fixture',exact=True)).to_be_visible();expect(page.get_by_role('button',name='Queue reminder',exact=True)).to_have_count(0)
    page.get_by_label('Cart recovery status',exact=True).select_option('pending');expect(page.get_by_text('Pending fixture',exact=True)).to_be_visible();expect(page.get_by_text('Recovered fixture',exact=True)).to_have_count(0)
    search=page.get_by_label('Search carts by name or email',exact=True);search.fill('absent');expect(page.get_by_text('No abandoned carts found.',exact=True)).to_be_visible();search.fill('pending@example.invalid');expect(page.get_by_text('Pending fixture',exact=True)).to_be_visible();search.fill('')
    expect(page.get_by_role('link',name='WhatsApp',exact=True)).to_have_attribute('href','https://wa.me/2348012345678');expect(page.get_by_role('link',name='08012345678',exact=True)).to_have_attribute('href','tel:08012345678')
    state['hold']=True;queue=page.get_by_role('button',name='Queue reminder',exact=True);queue.click();expect(page.get_by_role('button',name='Queuing…',exact=True)).to_be_disabled()
    for _ in range(100):
     if state['held']:break
     page.wait_for_timeout(100)
    assert len(state['nudges'])==1 and len(state['held'])==1;state['held'].pop()[0].fulfill(status=409,json={'error':'Controlled reminder not due'});expect(page.get_by_text('Controlled reminder not due',exact=True)).to_be_visible();expect(queue).to_be_enabled()
    state['hold']=False;state['nudge_fail']=False;queue.click();expect(page.get_by_text('🔔 Reminder queued',exact=True)).to_be_visible();expect(page.get_by_text('Pending fixture',exact=True)).to_be_visible();assert len(state['nudges'])==2
    assert not page.get_by_role('option',name='Exhausted',exact=True).count();assert not page.get_by_role('option',name='Cleared',exact=True).count()
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');assert not errors,errors;ctx.close();print(json.dumps({'page':page_id,'width':width,'passed':True,'real_writes':0}),flush=True)
 browser.close()
