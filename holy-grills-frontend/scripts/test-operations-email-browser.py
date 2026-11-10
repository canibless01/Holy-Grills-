"""Native admin settings/cart controls; controlled transport, no real sends."""
import os,json
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('HG_BROWSER_BASE','http://127.0.0.1:4193')
C='11111111-1111-4111-8111-111111111111';U='22222222-2222-4222-8222-222222222222'
config={'recipients':['ops@example.invalid'],'paid_order_alerts':True,'abandoned_cart_alerts':True,'daily_report':True,'weekly_report':True,'abandoned_minutes':10}
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for case in ('settings_mobile','settings_desktop','cart_contact','status_error','cart_error'):
  ctx=browser.new_context(viewport={'width':393 if case!='settings_desktop' else 1280,'height':960})
  ctx.add_init_script(f"localStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_role','admin');localStorage.setItem('hg_campus_id','{C}');localStorage.setItem('hg_user_campus_id','{C}');localStorage.setItem('hg_admin_campus_id','{C}');localStorage.setItem('hg_cookie_consent',JSON.stringify({{essential:true,analytics:false,date:new Date().toISOString()}}));")
  writes=[];setting={**config}
  def api(route):
   path=urlparse(route.request.url).path;data={}
   if route.request.method!='GET':
    if not path.endswith('/admin/settings/campus_operations_email'):
     assert '/wallet' not in path and '/orders' not in path,'Unexpected money mutation: '+path
     route.fulfill(json={});return
    body=route.request.post_data_json;assert body['campus_id']==C and isinstance(body['value'],dict);writes.append(body);setting.update(body['value']);route.fulfill(json={'success':True});return
   if path.endswith('/auth/me'):data={'id':U,'role':'admin','full_name':'Controlled admin','campus_id':C}
   elif path.endswith('/campuses'):data=[{'id':C,'name':'Campus A','is_active':True}]
   elif path.endswith('/admin/settings'):data=[{'key':'campus_operations_email','value':setting,'campus_id':C,'is_public':False}]
   elif path.endswith('/admin/operations-emails'):
    if case=='status_error':route.fulfill(status=503,json={'error':'Delivery status unavailable'});return
    data={'counts':{'accepted':1},'recent':[{'id':'m','kind':'paid_order','recipient':'ops@example.invalid','state':'accepted','created_at':'2026-11-10T10:00:00Z'}]}
   elif path.endswith('/admin/abandoned-carts'):
    if case=='cart_error':route.fulfill(status=503,json={'error':'Cart service unavailable'});return
    data=[{'id':'cart','user_id':U,'is_recovered':False,'profiles':{'full_name':'Student A','email':'student@example.invalid','phone':'08012345678'},'cart_payload':{'items':[{'name':'Wings','quantity':2}]},'last_active_at':'2026-11-10T10:00:00Z','recovery_attempts':27,'saved_nudges':1,'email_accepted':1,'push_accepted':0,'delivery_pending':0,'delivery_issues':0}]
   elif path.endswith('/feature-flags') or path.endswith('/system-settings'):data=[]
   elif path.endswith('/notifications'):data={'notifications':[],'unread_count':0}
   elif path.endswith('/cart'):data={'items':[]}
   elif 'storefront' in path:data=[] if 'banner' in path or 'hours' in path else {}
   route.fulfill(status=200,json=data)
  ctx.route('**/api/**',api);page=ctx.new_page();page.set_default_timeout(12000)
  page.goto(BASE+'/admin?section='+('abandoned' if case.startswith('cart') else 'settings'))
  if case.startswith('settings'):
   expect(page.get_by_role('button',name='Save operations email')).to_be_visible()
   page.get_by_label('Report and alert recipients').fill('one@example.invalid, two@example.invalid')
   page.get_by_label('Daily summary',exact=True).uncheck()
   page.get_by_role('button',name='Save operations email').click()
   expect(page.get_by_text('Provider accepted',exact=True)).to_be_visible()
   assert len(writes)==1 and writes[0]['value']['recipients']==['one@example.invalid','two@example.invalid'] and not writes[0]['value']['daily_report']
   if case=='settings_mobile':page.screenshot(path='/workspace/Holy-Grills-/work/operations-email-mobile.png',full_page=True)
  elif case=='cart_contact':
   expect(page.get_by_text('1 reminder saved',exact=True)).to_be_visible()
   expect(page.get_by_role('link',name='WhatsApp',exact=True)).to_have_attribute('href','https://wa.me/2348012345678')
   expect(page.get_by_text('Email accepted: 1 · Push accepted: 0',exact=True)).to_be_visible()
   assert page.get_by_text('27 nudges',exact=True).count()==0
   expect(page.get_by_text('2× Wings',exact=True)).to_be_visible()
  elif case=='status_error':expect(page.get_by_role('alert').filter(has_text='Delivery status unavailable')).to_be_visible()
  else:
   expect(page.get_by_role('alert').filter(has_text='Cart service unavailable')).to_be_visible()
   assert page.get_by_text('No abandoned carts found.',exact=True).count()==0
  assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),'Horizontal overflow'
  print('PASS',case,flush=True);ctx.close()
 browser.close()
