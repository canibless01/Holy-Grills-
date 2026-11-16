"""Native report date/race/failure/export recovery. Controlled HTTP, no real data writes."""
import json,os,re
from datetime import datetime,timezone
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('HG_BROWSER_BASE','http://127.0.0.1:4185')
C='70000001-cafe-cafe-cafe-000000000001';U='11111111-1111-4111-8111-111111111111'
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for width in (393,1280):
  state={'fail':True,'hold':False,'held':[],'reads':[],'brands':0,'brand_fail':True,'export_fail':True,'exports':[]};errors=[]
  ctx=browser.new_context(viewport={'width':width,'height':1000},accept_downloads=True);ctx.add_init_script(f"localStorage.setItem('hg_access_token','synthetic');localStorage.setItem('hg_user_role','admin');localStorage.setItem('hg_campus_id','{C}');localStorage.setItem('hg_user_campus_id','{C}');localStorage.setItem('hg_cookie_consent',JSON.stringify({{essential:true,analytics:false,date:new Date().toISOString()}}));")
  def api(route):
   req=route.request;url=urlparse(req.url);path=url.path;q=parse_qs(url.query);data={}
   if path.endswith('/auth/me'):data={'id':U,'full_name':'Audit admin','role':'admin','campus_id':C}
   elif path.endswith('/campuses'):data={'campuses':[{'id':C,'name':'FUTA','slug':'futa','is_active':True}]}
   elif path.endswith('/analytics/brand-partnerships'):
    state['brands']+=1
    if state['brand_fail']:route.fulfill(status=503,json={'error':'Controlled brand failure'});return
    data={'brand_partnerships':[]}
   elif path.endswith('/analytics/export'):
    state['exports'].append(q)
    if state['export_fail']:route.fulfill(status=503,json={'error':'Controlled export failure'});return
    route.fulfill(status=200,content_type='text/csv',body='id,total\nfixture,1234\n');return
   elif '/analytics/' in path:
    state['reads'].append((path,q))
    if path.endswith('/sales'):
     if state['fail']:route.fulfill(status=503,json={'error':'Controlled report failure'});return
     if state['hold']:state['held'].append(route);return
     data={'total_revenue':1234,'order_count':2,'average_order_value':617}
    elif path.endswith('/orders'):data={'total_orders':2,'status_funnel':[]}
    elif path.endswith('/items'):data=[]
    elif path.endswith('/retention'):data={'retention':[]}
   elif '/notifications' in path:data={'notifications':[]}
   else:data=[]
   route.fulfill(status=200,json=data)
  ctx.route('**/api/**',api);ctx.route('https://*.onesignal.com/**',lambda r:r.abort())
  page=ctx.new_page();page.set_default_timeout(15000);page.clock.set_fixed_time(datetime(2026,11,14,23,30,tzinfo=timezone.utc));page.on('pageerror',lambda e:errors.append(str(e)));page.goto(BASE+'/admin?section=analytics',wait_until='domcontentloaded',timeout=30000)
  alert=page.get_by_role('alert').filter(has_text='Analytics could not be loaded completely.');expect(alert).to_be_visible();expect(page.get_by_label('To date',exact=True)).to_have_value('2026-11-15');expect(page.get_by_label('From date',exact=True)).to_have_value('2026-10-16');assert not page.get_by_text('Revenue (Delivered)',exact=True).count()
  state['fail']=False;alert.get_by_role('button',name='Retry',exact=True).click();expect(page.get_by_text('Revenue (Delivered)',exact=True)).to_be_visible();assert '₦1,234' in page.locator('body').inner_text();assert state['brands']==1
  state['hold']=True;page.get_by_role('button',name='7d',exact=True).click();page.wait_for_timeout(150);assert state['held'];expect(page.get_by_label('From date',exact=True)).to_be_visible()
  state['hold']=False;page.get_by_role('button',name='90d',exact=True).click();expect(page.get_by_text('Revenue (Delivered)',exact=True)).to_be_visible()
  for route in state['held']:route.fulfill(status=200,json={'total_revenue':9999,'order_count':999})
  page.wait_for_timeout(150);assert '₦9,999' not in page.locator('body').inner_text();assert state['brands']==1
  before=len(state['reads']);page.get_by_label('From date',exact=True).fill('2026-12-01');expect(page.get_by_role('alert')).to_contain_text('Choose a valid start and end date');assert len(state['reads'])==before
  page.get_by_role('button',name='30d',exact=True).click();expect(page.get_by_text('Revenue (Delivered)',exact=True)).to_be_visible()
  page.get_by_role('button',name='orders',exact=True).click();expect(page.get_by_text('Export failed. Please retry.',exact=True)).to_be_visible();state['export_fail']=False
  with page.expect_download() as info:page.get_by_role('button',name='orders',exact=True).click()
  download=info.value;assert download.suggested_filename=='orders_2026-11-15.csv';assert open(download.path()).read().startswith('id,total');assert state['exports'][-1]['to_date']==['2026-11-15']
  page.get_by_role('button',name='Customers & Engagement',exact=True).click();brand_alert=page.get_by_role('alert').filter(has_text='Brand requests could not be loaded.');expect(brand_alert).to_be_visible();assert not page.get_by_text('No brand partnership requests yet',exact=True).count();state['brand_fail']=False;brand_alert.get_by_role('button',name='Retry',exact=True).click();expect(page.get_by_text('No brand partnership requests yet',exact=True)).to_be_visible();assert state['brands']==2
  assert not errors,errors
  print(json.dumps({'width':width,'passed':True,'writes':0}),flush=True);ctx.close()
 browser.close()
