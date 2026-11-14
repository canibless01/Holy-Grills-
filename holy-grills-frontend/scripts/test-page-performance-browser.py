"""Bounded delayed HTTP tests. No production writes or provider requests."""
import json, os
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright, expect

BASE = os.environ.get('HG_BROWSER_BASE', 'http://127.0.0.1:4188')
U = '11111111-1111-4111-8111-111111111111'; C = '70000001-cafe-cafe-cafe-000000000001'
expect.set_options(timeout=15000)
with sync_playwright() as p:
 browser = p.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox'])
 for case in ('menu', 'dashboard', 'cms', 'settings', 'settings_admin', 'rewards'):
  role = 'student' if case in ('menu', 'rewards') else 'admin' if case == 'settings_admin' else 'super_admin'
  ctx = browser.new_context(viewport={'width':393 if case=='menu' else 1280,'height':950})
  ctx.add_init_script(f"localStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_role','{role}');localStorage.setItem('hg_campus_id','{C}');localStorage.setItem('hg_user_campus_id','{C}');localStorage.setItem('hg_admin_campus_id','{C}');")
  calls=[]; held=[]; settings_fail=[True]; settings_value=[False]; writes=[]
  meal={'id':U,'name':'Grill Wings','price':2000,'is_available':True,'category_id':'chicken','menu_categories':{'slug':'chicken'},'image_url':'https://res.cloudinary.com/demo/image/upload/v123/food.jpg'}
  def api(route):
   req=route.request; path=urlparse(req.url).path; query=parse_qs(urlparse(req.url).query);calls.append((path,query));data={}
   if path.endswith('/auth/me'):data={'id':U,'role':role,'campus_id':C,'full_name':'Controlled Student'}
   elif path.endswith('/campuses'):data={'campuses':[{'id':C,'name':'FUTA','is_active':True}]}
   elif path.endswith('/wallet'):data={'balance':0}
   elif path.endswith('/hp/balance'):data={'active':0,'pending':0}
   elif case=='rewards' and ('exclusive' in path or '/challenges/my' in path):
    route.fulfill(status=403,json={'error':'Feature disabled'});return
   elif path.endswith('/menu/items'):
    assert 'authorization' not in {k.lower():v for k,v in req.headers.items()}
    if query.get('q'): held.append(route);return
    data={'items':[meal,{**meal,'id':'other','name':'Fries','category_id':'sides','menu_categories':{'slug':'sides'}}]}
   elif path.endswith('/menu/categories'):data=[{'id':'chicken','slug':'chicken','name':'Chicken'},{'id':'sides','slug':'sides','name':'Sides'}]
   elif path.endswith('/analytics/dashboard'):data={'total_orders':7,'active_orders':2}
   elif case=='dashboard' and any(path.endswith(suffix) for suffix in ('/analytics/sales','/analytics/hp','/analytics/items')):held.append(route);return
   elif case=='cms' and ('newsletter' in path):held.append(route);return
   elif path.endswith('/admin/settings'):
    if req.method == 'POST':
     writes.append(req.post_data_json);route.fulfill(status=200,json={'message':'Created'});return
    if case=='settings' and settings_fail[0]:route.fulfill(status=503,json={'error':'Controlled settings outage'});return
    data={'settings':[{'key':'controlled_toggle','value':settings_value[0],'campus_id':C,'is_public':True}]+([{'key':'foreign_toggle','value':False,'campus_id':'other-campus'},{'key':'global_toggle','value':False,'campus_id':None}] if case=='settings_admin' else [])}
   elif path.endswith('/admin/settings/controlled_toggle'):
    writes.append(req.post_data_json);settings_value[0]=req.post_data_json['value'];data={'message':'Saved'}
   elif '/notifications' in path:data={'notifications':[]}
   elif 'cart' in path:data={'items':[]}
   elif any(x in path for x in ('orders','tiers','transactions','saved','feature-flags','sections','early-supporters','banners')):data=[]
   route.fulfill(status=200,json=data)
  ctx.route('**/api/**',api);ctx.route('https://*.onesignal.com/**',lambda r:r.abort());ctx.route('https://res.cloudinary.com/**',lambda r:r.abort())
  page=ctx.new_page()
  target={'menu':'/menu','dashboard':'/admin','cms':'/admin?section=storefront','settings':'/admin?section=settings','settings_admin':'/admin?section=settings','rewards':'/rewards'}[case]
  page.goto(BASE+target,wait_until='domcontentloaded')
  if case=='menu':
   expect(page.get_by_role('heading',name='Grill Wings',exact=True)).to_be_visible()
   expect(page).to_have_title('Grilled Chicken, Wings & Sides at FUTA, Akure | Holy Grills')
   if page.get_by_role('button',name='Essential only').count():page.get_by_role('button',name='Essential only').click()
   before=sum(path.endswith('/menu/items') for path,q in calls)
   # Expire the catalogue cache: category filtering still needs no HTTP.
   page.evaluate('() => { const now = Date.now.bind(Date); Date.now = () => now() + 16000; }')
   page.get_by_role('button',name='Chicken',exact=True).click()
   expect(page.get_by_role('heading',name='Grill Wings',exact=True)).to_be_visible(timeout=500)
   expect(page.get_by_role('heading',name='Fries',exact=True)).to_have_count(0)
   assert sum(path.endswith('/menu/items') for path,q in calls)==before
   page.get_by_role('button',name='All Items',exact=True).click()
   page.get_by_placeholder('Search the grill...').fill('Grill')
   expect(page.get_by_role('heading',name='Grill Wings',exact=True)).to_be_visible(timeout=500)
   page.wait_for_timeout(400);assert held
   for route in held:route.fulfill(status=200,json={'items':[meal,{**meal,'id':'secret','name':'Secret Grill','is_secret':True}]})
   expect(page.get_by_role('heading',name='Secret Grill',exact=True)).to_be_visible()
   image=page.get_by_role('img',name='Grill Wings',exact=True)
   assert 'f_auto,q_auto,c_limit,w_480' in image.get_attribute('src')
   assert '768w' in image.get_attribute('srcset')
   resume_before=sum(path.endswith('/menu/items') for path,q in calls)
   page.evaluate("() => window.dispatchEvent(new Event('online'))")
   page.wait_for_timeout(250)
   assert sum(path.endswith('/menu/items') for path,q in calls)==resume_before+1
  elif case=='dashboard':
   expect(page.get_by_text('Orders Today',exact=True)).to_be_visible(timeout=3000)
   assert held
   assert 'Loading sales' in page.locator('body').inner_text()
   for route in held:route.fulfill(status=200,json=[])
  elif case=='cms':
   expect(page.get_by_role('button',name='Hero',exact=True)).to_be_visible(timeout=3000)
   assert held
   page.get_by_role('button',name='Newsletter',exact=False).click()
   assert page.get_by_role('button',name='New campaign',exact=False).count()==0
   for route in held:route.fulfill(status=503,json={'error':'Controlled report outage'})
   expect(page.get_by_role('alert')).to_contain_text('Newsletter reports could not be loaded')
   page.get_by_role('button',name='Hero',exact=True).click()
   expect(page.get_by_role('button',name='Hero',exact=True)).to_be_visible()
  elif case=='settings':
   expect(page.get_by_role('alert')).to_be_visible()
   assert page.get_by_text('controlled_toggle',exact=True).count()==0
   settings_fail[0]=False
   page.get_by_role('button',name='Retry',exact=True).click()
   expect(page.get_by_text('controlled_toggle',exact=True)).to_be_visible()
   switch=page.get_by_role('switch').last
   switch.click()
   expect(switch).to_have_attribute('aria-checked','true')
   assert writes==[{'value':True,'campus_id':C}],writes
  elif case=='rewards':
   expect(page.get_by_role('heading',name='Rewards',exact=False).first).to_be_visible()
   assert not page.get_by_text('Rewards or tier details could not be loaded.',exact=True).count()
  else:
   expect(page.get_by_text('controlled_toggle',exact=True)).to_be_visible()
   expect(page.get_by_role('switch')).to_have_count(1)
   page.get_by_role('button',name='New Setting',exact=True).click()
   dialog=page.get_by_role('dialog')
   dialog.get_by_placeholder('new_setting_key').fill('campus_setting')
   dialog.get_by_role('textbox').nth(1).fill('12')
   dialog.get_by_role('button',name='Create Setting',exact=False).click()
   for _ in range(30):
    if writes:break
    page.wait_for_timeout(50)
   assert writes and writes[-1]['campus_id']==C,writes
  print(json.dumps({'case':case,'passed':True,'production_writes':0}),flush=True)
  ctx.close()
 browser.close()
