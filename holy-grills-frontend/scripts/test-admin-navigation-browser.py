"""Native shared admin navigation and role-scoped search; API transport isolated.
This verifies the shell/registry, not every action within each page.
"""
import json,os,re
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('HG_BROWSER_BASE','http://127.0.0.1:4185')
C='70000001-cafe-cafe-cafe-000000000001';U='11111111-1111-4111-8111-111111111111'
source=(Path(__file__).resolve().parents[1]/'src/lib/adminSections.ts').read_text();section_ids=re.findall(r"\{ id: '([^']+)'",source)
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for width,role in ((1280,'admin'),(393,'super_admin'),(393,'community_manager'),(1280,'community_manager')):
  ctx=browser.new_context(viewport={'width':width,'height':950});ctx.add_init_script(f"localStorage.setItem('hg_access_token','synthetic');localStorage.setItem('hg_user_role','{role}');localStorage.setItem('hg_campus_id','{C}');localStorage.setItem('hg_user_campus_id','{C}');localStorage.setItem('hg_admin_collapsed','true');localStorage.setItem('hg_cookie_consent',JSON.stringify({{essential:true,analytics:false,date:new Date().toISOString()}}));")
  errors=[]
  def api(route):
   path=urlparse(route.request.url).path;data={}
   if path.endswith('/auth/me'):data={'id':U,'full_name':'Audit staff','role':role,'campus_id':C}
   elif path.endswith('/campuses'):data={'campuses':[{'id':C,'name':'FUTA','slug':'futa','is_active':True}]}
   elif path.endswith('/staff/ambassadors'):data={'ambassadors':[]}
   elif path.endswith('/staff/promo-messages'):data={'messages':[]}
   elif path.endswith('/staff/reviews'):data={'reviews':[]}
   elif '/notifications' in path:data={'notifications':[]}
   else:data=[]
   route.fulfill(status=200,json=data)
  ctx.route('**/api/**',api);ctx.route('https://*.onesignal.com/**',lambda r:r.abort())
  page=ctx.new_page();page.set_default_timeout(10000);page.on('pageerror',lambda e:errors.append(str(e)));path='/community-manager' if role=='community_manager' else '/admin'
  page.goto(BASE+path+'?section=ambassadors',wait_until='domcontentloaded',timeout=30000);expect(page.locator('header h1')).to_contain_text('Ambassador',timeout=15000)
  aside=page.locator('aside');nav=aside.locator('nav')
  if width>=1024:
   expect(page.get_by_role('button',name='Expand sidebar',exact=True)).to_be_visible()
   expect(nav.locator('button[title]')).to_have_count(3 if role=='community_manager' else len(section_ids))
   page.get_by_role('button',name='Expand sidebar',exact=True).click();expect(page.get_by_role('button',name='Collapse sidebar',exact=True)).to_be_visible()
   page.get_by_role('button',name='Collapse sidebar',exact=True).click()
   nav.locator('button[title="Promo Distribution"]').click();expect(page).to_have_url(re.compile('section=ambassadorpromo'))
  else:
   page.get_by_role('button',name='Open menu',exact=True).click();expect(aside).to_be_in_viewport();assert page.evaluate('document.body.style.overflow')=='hidden'
   nav.get_by_role('button',name='Ambassador Programme',exact=True).click();button=nav.locator('button[title="Promo Distribution"]');expect(button.locator('span',has_text='Promo Distribution')).to_be_visible();button.click();expect(page).to_have_url(re.compile('section=ambassadorpromo'));expect(aside).not_to_be_in_viewport();assert page.evaluate('document.body.style.overflow')==''
   page.get_by_role('button',name='Open menu',exact=True).click();page.keyboard.press('Escape');expect(aside).not_to_be_in_viewport()
   page.get_by_role('button',name='Open menu',exact=True).click();page.get_by_role('button',name='Close menu',exact=True).click();expect(aside).not_to_be_in_viewport()
  page.get_by_role('button',name='Search admin panel',exact=True).click();search=page.get_by_placeholder('Search admin sections…').last
  search.fill('wallet')
  if role=='community_manager':
   expect(page.get_by_text('No sections match “wallet”.',exact=True)).to_be_visible();assert not page.get_by_role('button',name=re.compile('Wallet.*Transactions')).count()
   search.fill('promo');expect(page.get_by_role('button',name='Promo Distribution Create personalized promotional messages for ambassadors',exact=True)).to_be_visible()
  else:expect(page.get_by_role('button',name=re.compile('Wallet.*Transactions')).last).to_be_visible()
  search.fill('monthly');search.press('Enter');expect(page).to_have_url(re.compile('section=ambassadorreviews'));expect(search).to_have_value('')
  page.reload(wait_until='domcontentloaded');expect(page.locator('header h1')).to_contain_text('Monthly')
  page.go_back(wait_until='domcontentloaded');expect(page).to_have_url(re.compile('section=ambassadorpromo'))
  page.go_forward(wait_until='domcontentloaded');expect(page).to_have_url(re.compile('section=ambassadorreviews'))
  if role=='community_manager':
   page.goto(BASE+path+'?section=wallet',wait_until='domcontentloaded',timeout=30000);expect(page.locator('header h1')).to_contain_text('Ambassador');assert not page.get_by_role('heading',name='Wallet Transactions',exact=True).count()
  expect(page.get_by_role('link',name='View student page',exact=True)).to_have_attribute('href','/')
  if role=='admin':
   page.goto(BASE+'/community-manager?section=ambassadors',wait_until='domcontentloaded',timeout=30000);expect(page.locator('header h1')).to_contain_text('Ambassador')
   page.get_by_role('button',name='Search admin panel',exact=True).click();page.get_by_placeholder('Search admin sections…').last.fill('wallet');expect(page.get_by_text('No sections match “wallet”.',exact=True)).to_be_visible()
  assert not errors,errors
  print(json.dumps({'width':width,'role':role,'registry_sections':len(section_ids),'passed':True}),flush=True);ctx.close()
 browser.close()
