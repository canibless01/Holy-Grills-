"""Community/admin workspace navigation and rider bulk pickup; controlled transport."""
import json,os,signal,subprocess,tempfile,time
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
repo=Path(__file__).resolve().parents[1];out=Path(tempfile.mkdtemp(prefix='hg-community-bulk-'));c='11111111-1111-4111-8111-111111111111';b='22222222-2222-4222-8222-222222222222';pickups=[]
orders=[{'id':'33333333-3333-4333-8333-333333333333','status':'assigned','items':[]},{'id':'44444444-4444-4444-8444-444444444444','status':'assigned','items':[]},{'id':'55555555-5555-4555-8555-555555555555','status':'out_for_delivery','items':[]}]
fail_second=True
def fixture(route,role):
 global fail_second
 req=route.request;path=urlparse(req.url).path;data={}
 if path.endswith('/auth/me'):data={'id':'controlled-'+role,'role':role,'campus_id':c,'profile':{'id':'controlled-'+role,'role':role,'campus_id':c}}
 elif path.endswith('/campuses'):data=[{'id':c,'name':'Controlled campus','is_active':True}]
 elif '/ambassadors/' in path or path.endswith('/ambassadors'):data=[]
 elif path.endswith('/riders/earnings'):data={'total_earnings':600.5,'total_paid':600.5,'completed_batches':1,'batches':[{'batch_id':b,'zone':'Paid settlement test','amount':600.5,'paid_at':'2026-10-28T10:00:00+01:00','completed_at':'2026-10-28T09:00:00+01:00','order_count':3}]}
 elif path.endswith('/riders/my-batch'):data={'batch':{'id':b,'status':'assigned','zone':'Test gate'},'orders':orders}
 elif '/riders/orders/' in path and path.endswith('/pickup'):
  oid=path.split('/')[-2];pickups.append(oid)
  if oid==orders[1]['id'] and fail_second:
   fail_second=False;route.fulfill(status=409,json={'error':'Controlled state conflict'});return
  next(o for o in orders if o['id']==oid)['status']='out_for_delivery';data={'success':True}
 elif path.endswith('/cart'):data={'items':[]}
 elif path.endswith('/storefront/sections') or path.endswith('/storefront/banners') or path.endswith('/menu') or path.endswith('/gates'):data=[]
 route.fulfill(status=200,json=data)
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5233','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
try:
 time.sleep(2)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  for role in ['community_manager','admin','super_admin']:
   ctx=browser.new_context(viewport={'width':1280,'height':1000});ctx.route('**/api/**',lambda route:fixture(route,role));ctx.add_init_script("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_campus_id','"+c+"');localStorage.setItem('hg_admin_campus_id','"+c+"')")
   page=ctx.new_page();page.set_default_timeout(8000);page.goto('http://127.0.0.1:5233/community-manager');page.get_by_role('button',name='Essential only',exact=True).click();expect(page.get_by_role('heading',name='Campus Ambassadors',exact=True)).to_be_visible()
   if role=='community_manager':
    expect(page.get_by_role('link',name='Kitchen panel',exact=True)).to_have_count(0);page.get_by_role('link',name='View student page',exact=True).click();expect(page).to_have_url('http://127.0.0.1:5233/');page.get_by_role('link',name='Open Community Manager panel',exact=True).click();expect(page).to_have_url('http://127.0.0.1:5233/community-manager')
   else:
    page.get_by_role('link',name='Open Admin panel',exact=True).click();expect(page).to_have_url('http://127.0.0.1:5233/admin');page.get_by_role('link',name='Community manager workspace',exact=True).click();expect(page).to_have_url('http://127.0.0.1:5233/community-manager');expect(page.get_by_role('button',name='Add Ambassador tag',exact=True)).to_be_visible()
   ctx.close()
  ctx=browser.new_context(viewport={'width':1280,'height':1000});ctx.route('**/api/**',lambda route:fixture(route,'rider'));ctx.add_init_script("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_campus_id','"+c+"')")
  page=ctx.new_page();page.set_default_timeout(8000);page.goto('http://127.0.0.1:5233/rider');page.get_by_role('button',name='Essential only',exact=True).click();page.get_by_role('button',name='Collect batch · start deliveries',exact=True).click();expect(page.get_by_text('1 collected · 1 not collected',exact=True)).to_be_visible();assert pickups==[orders[0]['id'],orders[1]['id']]
  page.get_by_role('button',name='Collect batch · start deliveries',exact=True).click();expect(page.get_by_role('button',name='Collect batch · start deliveries',exact=True)).to_have_count(0);assert pickups==[orders[0]['id'],orders[1]['id'],orders[1]['id']];assert all(o['status']=='out_for_delivery' for o in orders);expect(page.get_by_role('button',name='Delivered',exact=True)).to_have_count(3)
  page.get_by_role('button',name='Earnings',exact=True).click();row=page.get_by_text('Paid settlement test',exact=True).locator('..').locator('..');expect(row).to_contain_text('600.5');expect(row.get_by_text('Paid',exact=True)).to_be_visible()
  browser.close()
 print(json.dumps({'community_student_roundtrip':True,'admin_and_super_workspace_access':True,'cm_forbidden_staff_links_hidden':True,'bulk_pickup_partial_and_retry':True,'delivered_remains_individual':True,'rider_settlement_fields_reflect':True}))
finally:os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
