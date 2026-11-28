"""Native reporting controls with mocked transport; no production writes or sends."""
import csv,io,json,os
from datetime import datetime,timedelta,timezone
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('HG_BROWSER_BASE','http://127.0.0.1:4193')
A='11111111-1111-4111-8111-111111111111';B='22222222-2222-4222-8222-222222222222';U='33333333-3333-4333-8333-333333333333'
TODAY=datetime.now(timezone(timedelta(hours=1))).date()
def report(campus,query=None):
 query=query or {};start=query.get('from_date',[(TODAY-timedelta(days=29)).isoformat()])[0];end=query.get('to_date',[TODAY.isoformat()])[0]
 return {'as_of':TODAY.isoformat()+'T09:00:00Z','timezone':'Africa/Lagos','currency':'NGN','campus_id':campus,'excluded_roles':['super_admin'],
  'period':{'from_date':start,'to_date':end},'balances':{'outstanding':700 if campus==B else 640.75,'wallet_accounts':20,'funded_accounts':3,'inactive_balance':100.25,'average_funded_balance':213.58,'balance_issues':0},
  'activity':{'funding_received':1200,'automatic_received':200,'automatic_contributions':1,'manual_funding_received':1000,'refunds_credited':50,'other_credits':25,'wallet_debits':100,'adjustments':0},
  'transfers':{'count':1,'volume':50},'automatic_funding':{'owners':14,'plans':14,'states':{'active':10,'draft':1,'attention':1,'stopped':1,'completed':1},'lifetime_credited':2000,'lifetime_contributions':10},
  'payment_health':{'awaiting_first_payment':1,'awaiting_confirmation':1,'unconfirmed_amount':300,'failed_in_period':1},
  'projection':{'eligible_plans':4,'excluded_active_plans':6,'overdue_plans':1,'horizons':[{'days':d,'through_date':(TODAY+timedelta(days=d-1)).isoformat(),'amount':v,'contributions':n} for d,v,n in [(7,1200,9),(30,1900,16),(90,3900,36)]],
   'daily':[{'date':(TODAY+timedelta(days=i)).isoformat(),'amount':500 if i==0 else 100,'contributions':4 if i==0 else 1} for i in range(30)]},
  'daily_history':[{'date':(TODAY-timedelta(days=i)).isoformat(),'manual_funding':100 if i==0 else 0,'automatic_funding':200 if i==0 else 0,'refunds':0,'wallet_debits':0} for i in range(3)]}
expect.set_options(timeout=15000)
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for case in ('normal_mobile','normal_desktop','initial_failure','refresh_failure','malformed','campus_race','manager_denied'):
  role='community_manager' if case=='manager_denied' else 'super_admin' if case=='campus_race' else 'admin'
  ctx=browser.new_context(viewport={'width':393 if case=='normal_mobile' else 1280,'height':960})
  ctx.add_init_script(f"localStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_role','{role}');localStorage.setItem('hg_campus_id','{A}');localStorage.setItem('hg_user_campus_id','{A}');localStorage.setItem('hg_admin_campus_id','{A}');localStorage.setItem('hg_cookie_consent',JSON.stringify({{essential:true,analytics:false,date:new Date().toISOString()}}));")
  reads=[];held=[];fail=[case=='initial_failure'];malformed=[case=='malformed']
  def api(route):
   path=urlparse(route.request.url).path;query=parse_qs(urlparse(route.request.url).query);data={}
   if path.endswith('/analytics/wallet'):assert route.request.method=='GET'
   if route.request.method!='GET':
    assert '/wallet' not in path and 'auto-funding' not in path,'Reporting must not trigger money writes'
    route.fulfill(status=200,json={});return
   if path.endswith('/auth/me'):data={'id':U,'full_name':'Controlled Admin','role':role,'campus_id':A}
   elif path.endswith('/campuses'):data=[{'id':A,'name':'Campus A','is_active':True},{'id':B,'name':'Campus B','is_active':True}]
   elif path.endswith('/analytics/wallet'):
    reads.append(query);campus=query.get('campus_id',[None])[0]
    if case=='campus_race' and campus==A:held.append((route,query));return
    if fail[0]:route.fulfill(status=503,json={'error':'Wallet analytics temporarily unavailable'});return
    if malformed[0]:data={}
    else:data=report(campus,query)
   elif '/notifications' in path:data={'notifications':[]}
   elif path.endswith('/wallet'):data={'balance':0}
   elif path.endswith('/hp/balance'):data={'active':0,'pending':0}
   elif 'cart' in path:data={'items':[]}
   elif any(s in path for s in ('feature-flags','orders','tiers','ambassadors','sections','banners','early-supporters','saved')):data=[]
   route.fulfill(status=200,json=data)
  ctx.route('**/api/**',api);ctx.route('https://*.onesignal.com/**',lambda r:r.abort());ctx.route('https://res.cloudinary.com/**',lambda r:r.abort())
  page=ctx.new_page();page.goto(BASE+'/admin?section=walletanalytics',wait_until='domcontentloaded')
  if case=='manager_denied':
   expect(page.get_by_role('heading',name='Campus Ambassadors',exact=True).first).to_be_visible()
   assert not reads;expect(page.get_by_role('heading',name='Wallet & Funding',exact=True)).to_have_count(0)
  elif case=='campus_race':
   for _ in range(50):
    if held:break
    page.wait_for_timeout(100)
   assert held
   page.get_by_role('button',name='Campus A',exact=True).click();page.get_by_role('button',name='Campus B',exact=True).click()
   expect(page.get_by_text('₦700',exact=True)).to_be_visible()
   for route,query in held:route.fulfill(status=200,json=report(A,query))
   expect(page.get_by_text('₦640.75',exact=True)).to_have_count(0)
   assert reads[-1]['campus_id']==[B]
  elif case in ('initial_failure','malformed'):
   expect(page.get_by_role('alert')).to_be_visible()
   expect(page.get_by_text('Outstanding wallet credit',exact=True)).to_have_count(0)
   fail[0]=False;malformed[0]=False;page.get_by_role('button',name='Retry wallet report',exact=True).click()
   expect(page.get_by_text('₦640.75',exact=True)).to_be_visible();assert len(reads)==2
  else:
   expect(page.get_by_text('₦640.75',exact=True)).to_be_visible()
   assert len(reads)==1
   expect(page.get_by_text('Super-admin accounts are excluded throughout this report.',exact=True)).to_be_visible()
   if case=='refresh_failure':
    fail[0]=True;page.get_by_role('button',name='Refresh',exact=True).click()
    expect(page.get_by_role('alert')).to_contain_text('previous snapshot')
    expect(page.get_by_text('₦640.75',exact=True)).to_be_visible()
    fail[0]=False;page.get_by_role('button',name='Retry wallet report',exact=True).click()
    expect(page.get_by_role('alert')).to_have_count(0);assert len(reads)==3
   else:
    page.get_by_label('Funding from date').fill((TODAY-timedelta(days=6)).isoformat())
    assert len(reads)==1
    page.get_by_role('button',name='Apply dates',exact=True).click()
    expect(page.get_by_role('button',name='Apply dates',exact=True)).to_be_enabled()
    assert len(reads)==2 and reads[-1]['from_date']==[(TODAY-timedelta(days=6)).isoformat()]
    page.get_by_text('Daily projection · next 30 days',exact=True).click()
    expect(page.get_by_role('columnheader',name='Projected credit',exact=True)).to_be_visible()
    with page.expect_download() as download:page.get_by_role('button',name='Download report',exact=True).click()
    text=open(download.value.path()).read();rows=list(csv.reader(io.StringIO(text)))
    assert 'Super-admin accounts excluded' in text and 'AUTH_' not in text
    assert any(row[1]=='automatic_contributions' and row[2]=='' and row[3]=='1' for row in rows)
    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth'),case
    if case=='normal_mobile':page.screenshot(path='work/wallet-analytics-mobile.png',full_page=True)
  ctx.close();print('PASS:',case,flush=True)
 browser.close()
