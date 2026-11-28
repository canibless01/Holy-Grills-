"""Actual student pages with delayed controlled HTTP; never uses production data."""
import json, os
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect
C='70000001-cafe-cafe-cafe-000000000001';U='11111111-1111-4111-8111-111111111111'
BASE=os.environ.get('HG_BROWSER_BASE','http://127.0.0.1:4185')
reports=[]
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for case in ['dashboard','wallet','funding','catalogue','ranking']:
  ctx=browser.new_context(viewport={'width':393,'height':852},is_mobile=True)
  script=f"localStorage.setItem('hg_campus_id','{C}');"
  if case!='catalogue':script+=f"localStorage.setItem('hg_access_token','synthetic');localStorage.setItem('hg_user_role','student');localStorage.setItem('hg_user_campus_id','{C}');"
  ctx.add_init_script(script);held=[];calls=[];errors=[]
  def api(route):
   path=urlparse(route.request.url).path;calls.append(path);data={}
   blocker={'dashboard':'/order-locks','wallet':'/hp/transactions','funding':'/wallet/fund/card/verify'}.get(case)
   if blocker and path.endswith(blocker):held.append(route);return
   if path.endswith('/auth/me'):data={'id':U,'role':'student','campus_id':C,'full_name':'Synthetic Student','wallet':{'balance':1000},'hp_earned_120day':100,'active':100}
   elif path.endswith('/hp/balance'):data={'active':100,'pending':0,'hp_earned_120day':100}
   elif path.endswith('/wallet'):data={'balance':1000}
   elif path.endswith('/campuses'):data={'campuses':[{'id':C,'name':'FUTA','slug':'futa','is_active':True}]}
   elif path.endswith('/leaderboard/my-rank'):data={'rank_entry':{'rank':3}}
   elif path.endswith('/menu/items'):data={'items':[{'id':U,'name':'Synthetic meal','price':100,'is_available':True,'is_featured':True,'image_url':'/favicon.ico'}]}
   elif '/notifications' in path:data={'notifications':[]}
   elif 'cart' in path:data={'items':[]}
   elif any(x in path for x in ('orders','tiers','transactions','saved','feature-flags','categories')):data=[]
   route.fulfill(status=200,json=data)
  ctx.route('**/api/**',api);ctx.route('https://*.onesignal.com/**',lambda r:r.abort())
  page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
  target='home' if case in ('catalogue','ranking') else 'wallet?reference=synthetic' if case=='funding' else case
  page.goto(BASE+('/' if target=='home' else '/'+target),wait_until='domcontentloaded')
  if case in ('dashboard','wallet','funding'):
   for _ in range(50):
    if held:break
    page.wait_for_timeout(100)
   assert held,(case,calls)
   if case=='dashboard':expect(page.get_by_role('heading',name='Welcome back',exact=False)).to_be_visible(timeout=1000)
   elif case=='wallet':
    expect(page.get_by_text('Wallet Balance',exact=True)).to_be_visible(timeout=1000)
    assert not page.get_by_text('No transactions yet',exact=True).count()
   else:assert not page.get_by_text('Wallet Balance',exact=True).count()
   for route in held:route.fulfill(status=200,json={'payment_status':'paid'} if case=='funding' else [])
   if case=='funding':expect(page.get_by_text('Wallet Balance',exact=True)).to_be_visible()
  else:
   expect(page.get_by_text('Synthetic meal',exact=True).first).to_be_visible(timeout=15000)
   if page.get_by_role('button',name='Essential only').count():page.get_by_role('button',name='Essential only').click()
   if case=='catalogue':
    before=calls.count('/api/menu/items');assert before==1,calls
    page.get_by_role('link',name='Menu',exact=True).first.click()
    expect(page.get_by_text('Synthetic meal',exact=True).first).to_be_visible()
    assert calls.count('/api/menu/items')==before,calls
   else:
    expect(page.get_by_role('link',name='Dashboard',exact=True)).to_be_visible()
    before=calls.count('/api/leaderboard/my-rank');assert before==1,calls
    page.get_by_role('link',name='Dashboard',exact=True).click()
    expect(page.get_by_role('heading',name='Welcome back',exact=False)).to_be_visible()
    page.wait_for_timeout(250)
    assert calls.count('/api/leaderboard/my-rank')==before,calls
  assert not errors,(case,errors)
  reports.append({'case':case,'passed':True,'production_writes':0})
  print(json.dumps(reports[-1]),flush=True);ctx.close()
 browser.close()
print(json.dumps(reports))
