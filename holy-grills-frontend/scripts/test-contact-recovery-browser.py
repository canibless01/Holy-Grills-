"""Real Contact/ContactActions/Footer shared reads and scoped links; no navigation to providers."""
import json,os
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
expect.set_options(timeout=20000)
BASE=os.environ.get('HG_BROWSER_BASE','http://127.0.0.1:4185');A='11111111-1111-4111-8111-111111111111';B='22222222-2222-4222-8222-222222222222';U='33333333-3333-4333-8333-333333333333'
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for width,member in ((393,True),(1280,True),(393,False)):
  state={'fail':True,'reads':[]};errors=[]
  ctx=browser.new_context(viewport={'width':width,'height':1000});ctx.add_init_script("localStorage.setItem('hg_cookie_consent',JSON.stringify({essential:true,analytics:false,date:new Date().toISOString()}));")
  if member:ctx.add_init_script(f"localStorage.setItem('hg_access_token','synthetic');localStorage.setItem('hg_user_role','student');localStorage.setItem('hg_user_campus_id','{A}');localStorage.setItem('hg_campus_id','{B}');")
  def api(route):
   req=route.request;path=urlparse(req.url).path;scope=req.headers.get('x-campus-id') or None;data={}
   if path.endswith('/auth/me'):data={'id':U,'full_name':'Fixture member','role':'student','campus_id':A}
   elif path.endswith('/campuses'):data={'campuses':[{'id':A,'name':'Campus A','is_active':True},{'id':B,'name':'Campus B','is_active':True}]}
   elif path.endswith('/storefront/config/public'):
    state['reads'].append(scope)
    if state['fail']:route.fulfill(status=503,json={'error':'Controlled contact outage'});return
    data={'global_support_email':'support@example.invalid','global_social_links':{'instagram':'https://www.instagram.com/holygrills','tiktok':'javascript:alert(1)'},'support_address':'Address A' if scope==A else 'Address B' if scope==B else '', 'whatsapp_support_number':'2348011111111' if scope==A else '2348022222222' if scope==B else None,'whatsapp_support_message':'Hello campus support'}
   elif path.endswith('/cart'):data={'items':[]}
   elif '/notifications' in path:data={'notifications':[]}
   else:data=[]
   route.fulfill(status=200,json=data)
  ctx.route('**/api/**',api);ctx.route('https://*.onesignal.com/**',lambda r:r.abort())
  page=ctx.new_page();page.set_default_timeout(15000);page.on('pageerror',lambda e:(errors.append(str(e)),print('PAGEERROR',e,flush=True)));page.goto(BASE+'/contact',wait_until='domcontentloaded',timeout=30000);section=page.locator('main section').filter(has=page.get_by_role('heading',name='Contact us',exact=True)).first
  error=section.get_by_role('alert');expect(error).to_contain_text('Contact details could not be loaded. Please retry.');assert not section.get_by_role('link',name='Message us on WhatsApp',exact=True).count();state['fail']=False;error.get_by_role('button',name='Retry',exact=True).click();expect(section.get_by_role('link',name='support@example.invalid',exact=True)).to_have_attribute('href','mailto:support@example.invalid');expect(section.get_by_role('link',name='Instagram',exact=True)).to_have_attribute('href','https://www.instagram.com/holygrills');assert not section.get_by_role('link',name='TikTok',exact=True).count()
  if member:
   expect(section.get_by_text('Address A',exact=True)).to_be_visible();expect(section.get_by_role('link',name='Message us on WhatsApp',exact=True)).to_have_attribute('href','https://wa.me/2348011111111?text=Hello%20campus%20support');assert not section.get_by_role('button',name='Choose campus for WhatsApp support',exact=True).count();assert state['reads'][-1]==A
   if width==1280:
    footer=page.locator('footer');expect(footer.get_by_role('link',name='support@example.invalid',exact=True)).to_be_visible();expect(footer.get_by_text('Address A',exact=True)).to_be_visible();expect(footer.get_by_role('link',name='Instagram',exact=True)).to_be_visible();assert not footer.get_by_role('alert').count()
  else:
   section.get_by_role('button',name='Choose campus for WhatsApp support',exact=True).click();page.get_by_role('button',name='Campus B',exact=True).last.click();expect(section.get_by_text('Address B',exact=True)).to_be_visible();expect(section.get_by_role('link',name='Message us on WhatsApp',exact=True)).to_have_attribute('href','https://wa.me/2348022222222?text=Hello%20campus%20support');assert state['reads'][-1]==B
  page.reload(wait_until='domcontentloaded');expect(section.get_by_role('link',name='Message us on WhatsApp',exact=True)).to_have_attribute('href','https://wa.me/'+('2348011111111' if member else '2348022222222')+'?text=Hello%20campus%20support');assert not errors,errors
  print(json.dumps({'width':width,'member':member,'passed':True,'provider_navigation':0}),flush=True);ctx.close()
 browser.close()
