"""Actual prompt + SDK wrapper, controlled provider/browser permission and API only."""
import os,signal,subprocess,tempfile,time,json
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
root=Path(__file__).resolve().parents[1];campus='11111111-1111-4111-8111-111111111111'
log=Path(tempfile.mkdtemp())/'vite.log'
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5278','--strictPort'],cwd=root,env=dict(os.environ,VITE_API_BASE_URL='/api',VITE_ONESIGNAL_APP_ID='11111111-1111-4111-8111-111111111111'),start_new_session=True,stdout=log.open('w'),stderr=subprocess.STDOUT)
SDK='''
const events=()=>{const handlers={};return {addEventListener:(k,f)=>(handlers[k]??=new Set()).add(f),removeEventListener:(k,f)=>handlers[k]?.delete(f)}};
const saved=localStorage.getItem('audit_push_allowed')==='1';
const sub={id:saved?'controlled-sub':null,optedIn:saved,...events(),optIn:async()=>{},optOut:async()=>{sub.optedIn=false}};
const sdk={init:async()=>{window.auditPush.init++},login:async id=>{window.auditPush.login.push(id)},logout:async()=>{},User:{PushSubscription:sub},Notifications:{...events(),requestPermission:async()=>{window.auditPush.permission++;localStorage.setItem('audit_push_allowed','1');sub.id='controlled-sub';sub.optedIn=true}}};
const old=window.OneSignalDeferred||[];window.OneSignalDeferred={push:fn=>fn(sdk)};old.forEach(fn=>fn(sdk));
'''
INIT=f'''
localStorage.setItem('hg_cookie_consent',JSON.stringify({{essential:true,analytics:false,date:new Date().toISOString()}}));localStorage.setItem('hg_campus_id','{campus}');
window.auditPush={{init:0,login:[],permission:0}};
Object.defineProperty(window,'Notification',{{configurable:true,value:class {{static get permission(){{return localStorage.getItem('audit_permission')||(localStorage.getItem('audit_push_allowed')==='1'?'granted':'default')}}}}}});
'''
try:
 time.sleep(2)
 with sync_playwright() as p:
  expect.set_options(timeout=12000)
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  for width in (393,1280):
   state={'member':False,'private':[]};errors=[]
   def api(route):
    req=route.request;path=urlparse(req.url).path;data=[]
    if path.endswith('/auth/me'):data={'id':'member','full_name':'Member','role':'student','campus_id':campus,'is_active':True,'profile':{'id':'member','role':'student','campus_id':campus},'wallet':{'balance':0}}
    elif path.endswith('/campuses'):data=[{'id':campus,'name':'Campus','is_active':True}]
    elif path.endswith('/messages'):data={'messages':{}}
    elif path.endswith('/auth/device-token') or path.endswith('/notifications/preferences'):
     if req.method!='GET':state['private'].append({'path':path,'body':req.post_data_json})
     data={}
    elif path.endswith('/cart'):data={'items':[]}
    elif path.endswith('/hp/balance'):data={'active':0,'pending':0}
    route.fulfill(json=data)
   def context():
    c=browser.new_context(viewport={'width':width,'height':900});c.add_init_script(INIT);c.route('**/api/**',api);c.route('https://cdn.onesignal.com/sdks/web/v16/OneSignalSDK.page.js',lambda r:r.fulfill(body=SDK,content_type='application/javascript'));return c
   c=context();page=c.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.set_default_timeout(12000)
   page.goto('http://127.0.0.1:5278/',wait_until='domcontentloaded')
   allow=page.get_by_role('button',name='Allow notifications',exact=True);expect(allow).to_be_enabled()
   assert page.evaluate('window.auditPush.permission')==0
   assert not state['private']
   page.get_by_role('button',name='Maybe later',exact=True).click();expect(allow).to_have_count(0)
   page.reload(wait_until='domcontentloaded');page.wait_for_timeout(3500);expect(allow).to_have_count(0)
   # A fresh account is offered its own prompt despite the guest dismissal.
   page.evaluate("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_role','student');localStorage.setItem('hg_user_campus_id',%s)"%json.dumps(campus))
   page.reload(wait_until='domcontentloaded');expect(allow).to_be_enabled();allow.click();expect(allow).to_have_count(0)
   assert page.evaluate('window.auditPush.permission')==1
   assert any(x['body'].get('push_enabled') is True for x in state['private'])
   c.close()
   # Guest Allow needs no account writes; subsequent login adopts that consent.
   state['private'].clear();c=context();page=c.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
   page.goto('http://127.0.0.1:5278/',wait_until='domcontentloaded');allow=page.get_by_role('button',name='Allow notifications',exact=True);expect(allow).to_be_enabled();allow.click();expect(allow).to_have_count(0)
   assert not state['private'];assert page.evaluate("localStorage.getItem('hg_guest_push_consent_v1')")
   page.evaluate("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_role','student');localStorage.setItem('hg_user_campus_id',%s)"%json.dumps(campus))
   page.reload(wait_until='domcontentloaded')
   page.wait_for_function("localStorage.getItem('hg_guest_push_consent_v1')===null")
   assert page.evaluate('window.auditPush.permission')==0
   assert any(x['body'].get('push_enabled') is True for x in state['private'])
   assert page.evaluate('window.auditPush.login').count('member')==1
   assert not errors,errors
   c.close();print(f'PASS {width}: guest suggestion only, dismiss/reload cooldown, account prompt, anonymous Allow without private writes, login adoption without another permission request',flush=True)
  browser.close()
finally:
 os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
