"""Run against a local Vite server; all API/provider calls are intercepted."""
import json, os, sys
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
ID='11111111-1111-4111-8111-111111111111'
C='70000001-cafe-cafe-cafe-000000000001'
mobile='--desktop' not in sys.argv
requests=[];writes=[];errors=[]
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 context=browser.new_context(viewport={'width':393 if mobile else 1280,'height':852},is_mobile=mobile)
 context.add_init_script("localStorage.setItem('hg_access_token','synthetic-local-only');localStorage.setItem('hg_user_role','super_admin');localStorage.setItem('hg_campus_id','"+C+"');localStorage.setItem('hg_user_campus_id','"+C+"');localStorage.setItem('hg_install_dismissed',String(Date.now()));")
 def api(route):
  request=route.request;path=urlparse(request.url).path;requests.append(path)
  data={}
  if path.endswith('/auth/me'):data={'id':ID,'role':'super_admin','full_name':'Local audit','campus_id':C,'profile':{'campus_id':C},'is_active':True}
  elif 'campuses' in path:data={'campuses':[{'id':C,'name':'FUTA','slug':'futa','is_active':True}]}
  elif path.endswith('/dispatch/recovery'):data={'deliveries':[] if writes else [{'id':ID,'channel':'email','status':'uncertain','provider':'resend','title':'Local synthetic receipt','recipient':'audit@example.invalid','attempts':'1'}]}
  elif path.endswith('/review'):
   writes.append(request.post_data_json);data={'status':'queued','idempotent':False}
  elif 'blasts' in path:data={'blasts':[]}
  elif '/notifications' in path:data={'notifications':[],'unread_count':0}
  elif any(x in path for x in ('tiers','saved','menu','feature-flags')):data=[]
  elif 'cart' in path:data={'items':[]}
  route.fulfill(status=200,content_type='application/json',body=json.dumps(data))
 context.route('**/api/**',api)
 # Never send third-party registration/provider requests from the controlled check.
 context.route('https://*.onesignal.com/**',lambda r:r.abort())
 page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
 page.goto(os.environ.get('HG_BROWSER_BASE_URL','http://127.0.0.1:5177').rstrip('/')+'/admin?section=notifications',wait_until='domcontentloaded')
 try: expect(page.get_by_role('button',name='Delivery recovery',exact=True)).to_be_visible(timeout=15000)
 except Exception:
  print(json.dumps({'errors':errors,'requests':requests,'body':page.locator('body').inner_text()[:1600]}),flush=True);raise
 assert not any(x.endswith('/dispatch/recovery') for x in requests)
 page.get_by_role('button',name='Delivery recovery',exact=True).click()
 page.get_by_role('button',name='Review provider result',exact=True).click()
 dialog=page.get_by_role('dialog');expect(dialog).to_be_visible()
 expect(dialog.get_by_role('button',name='Save provider review',exact=True)).to_be_disabled()
 dialog.get_by_label('Confirmed result').select_option('not_sent')
 dialog.get_by_label('Provider log evidence').fill('Provider log confirms sender rejected; no send occurred.')
 dialog.get_by_role('button',name='Save provider review',exact=True).click()
 expect(page.get_by_text('No deliveries need recovery.',exact=True)).to_be_visible()
 assert len(writes)==1 and writes[0]['outcome']=='not_sent' and writes[0]['review_id']
 assert not errors,errors
 print(json.dumps({'mobile':mobile,'native_form':True,'lazy_fetch':True,'evidence_required':True,'review_payload_valid':True,'queue_response_rendered':True,'console_errors':errors,'production_writes':0}))
 browser.close()
