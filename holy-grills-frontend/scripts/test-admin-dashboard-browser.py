"""Actual dashboard populated/read-failure/scope controls with controlled HTTP only."""
import os,json
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('HG_BROWSER_BASE','http://127.0.0.1:4185')
A='11111111-1111-4111-8111-111111111111';B='22222222-2222-4222-8222-222222222222';U='33333333-3333-4333-8333-333333333333'
expect.set_options(timeout=20000)
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for case,width in [('populated',393),('populated',1280),('all_failed',393),('partial_failed',1280),('tier_fallback',393),('campus_race',1280),('manager_denied',393)]:
  role='community_manager' if case=='manager_denied' else 'super_admin' if case=='campus_race' else 'admin'
  state={'fail':case in ('all_failed','partial_failed','tier_fallback'),'hold':case=='campus_race','reads':[],'held':[]};errors=[]
  ctx=browser.new_context(viewport={'width':width,'height':1100})
  ctx.add_init_script(f"localStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_role','{role}');localStorage.setItem('hg_user_campus_id','{A}');localStorage.setItem('hg_admin_campus_id','{A}');localStorage.setItem('hg_campus_id','{B}');localStorage.setItem('hg_cookie_consent',JSON.stringify({{essential:true,analytics:false,date:new Date().toISOString()}}));")
  ctx.add_init_script("const NativeDate=Date;window.Date=class extends NativeDate { constructor(...a){super(...(a.length?a:['2026-11-14T23:30:00Z']));} static now(){return new NativeDate('2026-11-14T23:30:00Z').getTime();} };")
  def api(route):
   req=route.request;path=urlparse(req.url).path;query=parse_qs(urlparse(req.url).query);scope=req.headers.get('x-campus-id');data={}
   if req.method!='GET':
    assert '/analytics/' not in path and not path.endswith('/menu/kitchen-capacity'),'Read-only dashboard must not write'
    route.fulfill(status=200,json={});return
   if path.endswith('/auth/me'):data={'id':U,'full_name':'Fixture admin','role':role,'campus_id':A}
   elif path.endswith('/campuses'):data=[{'id':A,'name':'Campus A','is_active':True},{'id':B,'name':'Campus B','is_active':True}]
   elif '/analytics/' in path or path.endswith('/menu/kitchen-capacity'):
    feed=path.rsplit('/',1)[-1];state['reads'].append((feed,scope,query))
    if state['fail'] and (case=='all_failed' or case=='partial_failed' and feed in ('dashboard','hp','items') or case=='tier_fallback' and feed=='users'):
     route.fulfill(status=503,json={'error':'Controlled report outage'});return
    if feed=='dashboard':
     data={'today':{'total_orders':7 if scope!=B else 19,'active_orders':4,'delivered_orders':2,'revenue_delivered':4100,'orders_by_status':{'delivered':2,'preparing':4,'cancelled':1},'orders_by_payment_method':{'wallet':5,'card':2}},'delivery_pipeline':{'open_windows':[{'id':'w1'},{'id':'w2'}],'active_batches':[{'id':'b1'},{'id':'b2'},{'id':'b3'}],'unassigned_orders':4}}
     if state['hold'] and scope==A:state['held'].append((route,data));return
    elif feed=='sales':data={'total_revenue':12000,'order_count':8,'average_order_value':1500}
    elif feed=='users':data={'tier_breakdown':{'Ember':11,'Flame':4}}
    elif feed=='hp':data={'hp_earned_active':1250,'hp_spent':250,'hp_expired':100,'hp_in_circulation':900,'tier_distribution':[{'tier':'Ember','count':11},{'tier':'Flame','count':4}]}
    elif feed=='items':data=[{'item_name':'Fixture chicken','qty_sold':8}]
    elif feed=='kitchen-capacity':data={'daily_order_capacity':50}
   elif '/notifications' in path:data={'notifications':[]}
   elif 'cart' in path:data={'items':[]}
   elif path.endswith('/hp/balance'):data={'active':0,'pending':0}
   elif any(x in path for x in ('feature-flags','orders','tiers','ambassadors','sections','banners','early-supporters')):data=[]
   route.fulfill(status=200,json=data)
  ctx.route('**/api/**',api);ctx.route('https://*.onesignal.com/**',lambda r:r.abort());ctx.route('https://res.cloudinary.com/**',lambda r:r.abort())
  page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto(BASE+'/admin?section=dashboard',wait_until='domcontentloaded');main=page.locator('body')
  def tile(label,value):
   element=main.get_by_text(label,exact=True);expect(element).to_be_visible();expect(element.locator('..')).to_contain_text(value)
  if case=='manager_denied':
   expect(main.get_by_role('heading',name='Campus Ambassadors',exact=True).first).to_be_visible();assert not state['reads']
  elif case=='all_failed':
   expect(main.get_by_text("We couldn't load this page. Please try again.",exact=True)).to_be_visible();assert not main.get_by_text('Orders Today',exact=True).count();state['fail']=False;main.get_by_role('button',name='Retry',exact=True).click();tile('Open delivery windows','2')
  elif case=='partial_failed':
   expect(main.get_by_role('alert')).to_be_visible();tile('Delivered Today','—');tile('Open delivery windows','—');expect(main.get_by_text('This insight could not be loaded. Retry to refresh it.',exact=True).first).to_be_visible();assert not main.get_by_text('No item sales yet',exact=True).count();tile('Earned (active)','—');state['fail']=False;main.get_by_role('button',name='Retry',exact=True).click();tile('Open delivery windows','2');expect(main.get_by_role('alert')).to_have_count(0)
  elif case=='campus_race':
   expect(page.get_by_role('button',name='Campus A',exact=True)).to_be_visible()
   for _ in range(100):
    if state['held']:break
    page.wait_for_timeout(100)
   assert state['held'];page.get_by_role('button',name='Campus A',exact=True).click();page.get_by_role('button',name='Campus B',exact=True).click();tile('Orders Today','19')
   for route,data in state['held']:route.fulfill(status=200,json=data)
   tile('Orders Today','19');state['hold']=False
  else:
   tile('Orders Today','7');tile('Open delivery windows','2');tile('Active batches','3');tile('Unassigned orders','4');tile('Kitchen capacity','50/day');tile('Earned (active)','1,250');expect(main.get_by_text('Ember',exact=True)).to_be_visible();expect(main.get_by_text('Flame',exact=True)).to_be_visible()
   if case=='tier_fallback':
    expect(main.get_by_role('alert')).to_be_visible();state['fail']=False;main.get_by_role('button',name='Retry',exact=True).click();expect(main.get_by_role('alert')).to_have_count(0)
   else:
    main.get_by_role('button',name='Refresh now',exact=True).click();expect(main.get_by_role('button',name='Refresh now',exact=True)).to_be_visible()
  if case!='manager_denied':
   for feed,scope,query in state['reads']:
    assert scope in (A,B),(feed,scope)
    if feed in ('sales','users','items','hp'):assert query.get('from_date')==['2026-10-17'] and query.get('to_date')==['2026-11-15'],(feed,query)
   assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),(case,width)
  assert not errors,errors;ctx.close();print(json.dumps({'case':case,'width':width,'passed':True,'real_writes':0}),flush=True)
 browser.close()
