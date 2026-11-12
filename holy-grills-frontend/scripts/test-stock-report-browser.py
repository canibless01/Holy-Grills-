"""Built-app report, CSV, error recovery and All Campuses; controlled HTTP, no writes."""
import os,csv,io
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('HG_BROWSER_BASE','http://127.0.0.1:4195');C='11111111-1111-4111-8111-111111111111';U='22222222-2222-4222-8222-222222222222'
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for case in ('mobile_csv','failed_retry','all_campuses','prize_handover_retry'):
  context=browser.new_context(viewport={'width':393 if case=='mobile_csv' else 1280,'height':960},accept_downloads=True)
  role='super_admin' if case=='all_campuses' else 'admin';failed=case=='failed_retry';calls=[];handover={'saved':False,'writes':[]}
  context.add_init_script(f"localStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_role','{role}');localStorage.setItem('hg_campus_id','{C}');localStorage.setItem('hg_user_campus_id','{C}');localStorage.setItem('hg_admin_campus_id','{C}');localStorage.setItem('hg_admin_scope_all','{'1' if case=='all_campuses' else '0'}');localStorage.setItem('hg_cookie_consent',JSON.stringify({{essential:true,analytics:false,date:new Date().toISOString()}}));")
  if case=='all_campuses':context.add_init_script("localStorage.removeItem('hg_admin_campus_id');")
  def api(route):
   path=urlparse(route.request.url).path;data={}
   if route.request.method=='PATCH' and path.endswith('/admin/exclusive-spin-prizes/'+U):
    body=route.request.post_data_json;assert body=={'status':'fulfilled'};handover['writes'].append(body);handover['saved']=True
    if len(handover['writes'])==1:route.fulfill(status=503,json={'error':'Controlled committed handover response loss'});return
    route.fulfill(json={'record':{'id':U,'status':'fulfilled'},'idempotent':True});return
   if route.request.method!='GET':
    assert path.endswith('/auth/session-activity'),'Unexpected mutation '+path
    route.fulfill(json={});return
   if path.endswith('/auth/me'):data={'id':U,'role':role,'campus_id':C,'full_name':'Controlled admin'}
   elif path.endswith('/campuses'):data=[{'id':C,'name':'FUTA','is_active':True}]
   elif path.endswith('/admin/exclusive-spin-pool'):data={'prizes':[],'credit_validity_days':30}
   elif path.endswith('/admin/exclusive-spin-prizes'):data=[] if handover['saved'] else [{'id':U,'user_id':C,'prize_name':'Frozen physical prize','full_name':'Winner','status':'pending','campus_id':C}]
   elif path.endswith('/admin/stock-items/report'):
    query=parse_qs(urlparse(route.request.url).query);calls.append(query)
    if failed:route.fulfill(status=503,json={'error':'Stock report temporarily unavailable'});return
    data={'items':[{'id':C,'campus_id':C,'campus':'FUTA','name':'=SUM(1,2)','unit':'Spoons','archived':False,'opening':6,'purchased':10,'used':15,'wasted':1,'corrected':2,'closing':2,'current_balance':2,'ledger_balance':2,'drift':0,'purchase_cost':40,'uncosted_purchases':1,'scope_mismatches':0}], 'as_of':'2026-11-12T12:00:00Z'}
   elif path.endswith('/admin/stock-items'):data=[]
   elif path.endswith('/measurement-units'):data=[{'id':C,'name':'Spoons'}]
   elif path.endswith('/feature-flags') or path.endswith('/system-settings'):data=[]
   elif path.endswith('/notifications'):data={'notifications':[],'unread_count':0}
   elif path.endswith('/cart'):data={'items':[]}
   elif 'storefront' in path:data=[] if 'banner' in path or 'hours' in path else {}
   route.fulfill(json=data)
  context.route('**/api/**',api);page=context.new_page();page.set_default_timeout(20000)
  page.goto(BASE+'/admin?section='+('exclusivespin' if case=='prize_handover_retry' else 'store'),wait_until='domcontentloaded')
  if case=='prize_handover_retry':
   button=page.get_by_role('button',name='Fulfil Frozen physical prize',exact=True);button.click()
   expect(page.get_by_text('Controlled committed handover response loss',exact=True)).to_be_visible()
   button.click();expect(button).to_have_count(0)
   assert handover['writes']==[{'status':'fulfilled'},{'status':'fulfilled'}]
   print('PASS',case,flush=True);context.close();continue
  if case!='all_campuses':page.get_by_role('button',name='Stock report & CSV',exact=True).click()
  if case=='failed_retry':
   expect(page.get_by_role('alert').filter(has_text='Stock report temporarily unavailable')).to_be_visible()
   expect(page.get_by_role('button',name='Export stock CSV',exact=True)).to_be_disabled()
   failed=False;page.get_by_role('alert').get_by_role('button',name='Retry',exact=True).click()
  expect(page.get_by_text('=SUM(1,2)',exact=True)).to_be_visible()
  expect(page.get_by_text('0 reconciliation issues',exact=True)).to_be_visible()
  expect(page.get_by_text('Some purchases have no cost recorded.',exact=False)).to_be_visible()
  with page.expect_download() as download:page.get_by_role('button',name='Export stock CSV',exact=True).click()
  content=open(download.value.path(),encoding='utf-8-sig').read();rows=list(csv.DictReader(io.StringIO(content)))
  assert rows[0]['name']=="'=SUM(1,2)" and rows[0]['opening']=='6' and rows[0]['closing']=='2'
  assert ('campus_id' not in calls[-1]) if case=='all_campuses' else calls[-1]['campus_id']==[C]
  assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),'Horizontal overflow'
  if case=='mobile_csv':page.screenshot(path='/workspace/Holy-Grills-/work/stock-report-mobile.png',full_page=True)
  print('PASS',case,flush=True);context.close()
 browser.close()
