"""Native preference reads, six independent partial writes and rollback isolation.
Push registration is a controlled boundary stub; no real device/provider claim.
"""
import json,os
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('HG_BROWSER_BASE','http://127.0.0.1:4185');C='70000001-cafe-cafe-cafe-000000000001';U='11111111-1111-4111-8111-111111111111'
LABELS={'push_enabled':'Push notifications','email_enabled':'Email notifications','order_updates':'Order updates','delivery_updates':'Delivery updates','hp_updates':'HP updates','promotions':'Promotions'}
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for width in (393,1280):
  state={'prefs':{key:key not in ('push_enabled','email_enabled','promotions') for key in LABELS},'read_fail':True,'writes':[],'held':[]};errors=[]
  ctx=browser.new_context(viewport={'width':width,'height':1000});ctx.add_init_script(f"localStorage.setItem('hg_access_token','synthetic');localStorage.setItem('hg_user_role','student');localStorage.setItem('hg_campus_id','{C}');localStorage.setItem('hg_user_campus_id','{C}');localStorage.setItem('hg_cookie_consent',JSON.stringify({{essential:true,analytics:false,date:new Date().toISOString()}}));window.Notification=class {{static permission='granted';static requestPermission=async()=> 'granted';}};")
  def api(route):
   req=route.request;path=urlparse(req.url).path;data={}
   if path.endswith('/auth/me'):data={'id':U,'full_name':'Audit user','role':'student','campus_id':C}
   elif path.endswith('/campuses'):data={'campuses':[{'id':C,'name':'FUTA','slug':'futa','is_active':True}]}
   elif path.endswith('/notifications/preferences'):
    if req.method=='GET':
     if state['read_fail']:route.fulfill(status=503,json={'error':'Controlled preference read failure'});return
     data=state['prefs']
    else:
     body=req.post_data_json;assert len(body)==1;state['writes'].append(body)
     if len(state['writes'])==1:state['held'].append(route);return
     state['prefs'].update(body);data=state['prefs']
   elif path.endswith('/push/fixture-enable'):state['prefs']['push_enabled']=True;data={'success':True}
   elif '/notifications' in path:data={'notifications':[]}
   else:data={}
   route.fulfill(status=200,json=data)
  ctx.route('**/api/**',api);ctx.route('https://*.onesignal.com/**',lambda r:r.abort())
  ctx.route('**/src/lib/webPush.ts*',lambda r:r.fulfill(status=200,content_type='application/javascript',body="export const isWebPushSupported=()=>true;export const subscribeToWebPush=async()=>{await fetch('/api/push/fixture-enable',{method:'POST'});return true;};export const unsubscribeFromWebPush=async()=>true;"))
  page=ctx.new_page();page.set_default_timeout(15000);page.on('pageerror',lambda e:errors.append(str(e)));page.goto(BASE+'/notification-preferences',wait_until='domcontentloaded',timeout=30000);expect(page.get_by_role('button',name='Retry',exact=True)).to_be_visible();assert not page.get_by_role('switch').count();state['read_fail']=False;page.get_by_role('button',name='Retry',exact=True).click();expect(page.get_by_role('switch',name='Promotions',exact=True)).to_have_attribute('aria-checked','false')
  order=page.get_by_role('switch',name='Order updates',exact=True);order.click();expect(order).to_have_attribute('aria-checked','false');expect(page.get_by_role('switch',name='Email notifications',exact=True)).to_be_disabled();page.get_by_role('button',name='Enable',exact=True).click();expect(page.get_by_role('switch',name='Push notifications',exact=True)).to_have_attribute('aria-checked','true');state['held'][0].fulfill(status=503,json={'error':'Controlled preference write failure'});expect(order).to_have_attribute('aria-checked','true');expect(page.get_by_role('switch',name='Push notifications',exact=True)).to_have_attribute('aria-checked','true');assert len(state['writes'])==1
  for key,label in LABELS.items():
   switch=page.get_by_role('switch',name=label,exact=True);expect(switch).to_be_enabled();before=dict(state['prefs']);next_value=not before[key];switch.click();expect(switch).to_have_attribute('aria-checked',str(next_value).lower());expect(switch).to_be_enabled();assert state['writes'][-1]=={key:next_value};assert all(state['prefs'][other]==value for other,value in before.items() if other!=key)
  page.reload(wait_until='domcontentloaded')
  for key,label in LABELS.items():expect(page.get_by_role('switch',name=label,exact=True)).to_have_attribute('aria-checked',str(state['prefs'][key]).lower())
  expect(page.get_by_role('button',name='Back to profile',exact=True)).to_be_visible();assert not errors,errors
  print(json.dumps({'width':width,'passed':True,'partial_preference_writes':len(state['writes']),'real_push_or_provider_calls':0}),flush=True);ctx.close()
 browser.close()
