"""Native paginated/search/race checks and hidden-report loading isolation."""
import json,os
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('HG_BROWSER_BASE','http://127.0.0.1:4185');C='11111111-1111-4111-8111-111111111111';U='22222222-2222-4222-8222-222222222222'
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);expect.set_options(timeout=15000)
 for width in (393,1280):
  ctx=browser.new_context(viewport={'width':width,'height':1000});errors=[];reads=[];held=[];state={'failure':True,'market':None}
  ctx.add_init_script('for(const[k,v]of Object.entries('+json.dumps({'hg_access_token':'controlled','hg_user_role':'admin','hg_campus_id':C,'hg_user_campus_id':C,'hg_cookie_consent':json.dumps({'essential':True,'analytics':False,'date':'2026-11-25'})})+'))localStorage.setItem(k,v);')
  def api(route):
   req=route.request;url=urlparse(req.url);path=url.path;q=parse_qs(url.query);data={};reads.append((path,q))
   if path.endswith('/auth/me'):data={'id':U,'full_name':'Controlled admin','role':'admin','campus_id':C,'is_active':True}
   elif path.endswith('/campuses'):data=[{'id':C,'name':'FUTA','is_active':True}]
   elif path.endswith('/admin/orders'):
    search=q.get('search',[''])[0];offset=int(q.get('offset',['0'])[0]);count=50 if not search and not offset else 1
    if search=='abc':held.append(route);return
    if search=='bad' and state['failure']:state['failure']=False;route.fulfill(status=503,json={'error':'Controlled order load failure'});return
    name='Recovered search' if search=='bad' else 'Latest search' if search=='def' else 'Next page customer' if offset else 'First page customer'
    data={'orders':[{'id':(search or 'aaa')+'00000-0000-4000-8000-'+str(index+offset).zfill(12),'user_id':U,'customer':{'full_name':name},'customer_phone':'08099999999','order_items':[],'status':'received','payment_status':'paid','total_amount':100,'created_at':'2026-11-25T09:00:00Z'} for index in range(count)],'limit':50,'offset':offset,'has_more':not search and offset==0}
   elif path.endswith('/analytics/sales'):data={'total_revenue':1234,'order_count':1}
   elif path.endswith('/analytics/marketplace'):state['market']=route;return
   elif path.endswith('/analytics/orders'):data={'total_orders':1,'status_funnel':[]}
   elif path.endswith('/analytics/items'):data=[]
   elif path.endswith('/analytics/retention'):data={'retention':[]}
   elif path.endswith('/analytics/brand-partnerships'):data={'brand_partnerships':[]}
   elif 'notifications' in path:data={'notifications':[],'unread_count':0}
   else:data=[]
   route.fulfill(status=200,json=data)
  ctx.route('**/api/**',api);page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto(BASE+'/admin?section=orders',wait_until='domcontentloaded')
  expect(page.get_by_text('First page customer',exact=True).first).to_be_visible();assert not any(path.endswith('/admin/users') for path,_ in reads)
  page.get_by_role('button',name='Next orders',exact=True).click();expect(page.get_by_text('Next page customer',exact=True)).to_be_visible()
  search=page.get_by_placeholder('Search order ID...');search.fill('abc');page.wait_for_timeout(450);assert held
  search.fill('def');expect(page.get_by_text('Latest search',exact=True)).to_be_visible()
  for route in held:route.fulfill(status=200,json={'orders':[{'id':'old','order_items':[],'customer':{'full_name':'Stale result'}}],'has_more':False})
  page.wait_for_timeout(150);expect(page.get_by_text('Stale result',exact=True)).to_have_count(0)
  search.fill('bad');expect(page.get_by_role('alert')).to_contain_text('Controlled order load failure');page.get_by_role('button',name='Retry',exact=True).click();expect(page.get_by_text('Recovered search',exact=True)).to_be_visible()
  assert len([q for path,q in reads if path.endswith('/admin/orders') and q.get('search')==['def']])==1
  page.goto(BASE+'/admin?section=analytics',wait_until='domcontentloaded');expect(page.get_by_text('Revenue (Delivered)',exact=True)).to_be_visible()
  assert state['market'] and not any(path.endswith('/analytics/retention') or path.endswith('/analytics/brand-partnerships') for path,_ in reads)
  page.get_by_role('button',name='Customers & Engagement',exact=True).click();expect(page.get_by_text('Brand Partnerships',exact=True)).to_be_visible()
  state['market'].fulfill(status=200,json={});page.wait_for_timeout(100)
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
  assert not errors,errors
  print(json.dumps({'width':width,'passed':True,'all_user_reads':0,'stale_search_ignored':True,'hidden_reports_deferred':True}),flush=True);ctx.close()
 browser.close()
