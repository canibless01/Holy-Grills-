"""Browser resume reads and OneSignal/backend contract; controlled providers only."""
import json,os,signal,subprocess,tempfile,time
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import sync_playwright,expect
repo=Path(__file__).resolve().parents[1];out=Path(tempfile.mkdtemp(prefix='hg-resume-push-'))
c='11111111-1111-4111-8111-111111111111';state={'recovered':False,'fail_token':True};counts={'sdk':0,'banners':0};tokens=[];preferences=[]
def api(route):
 req=route.request;u=urlparse(req.url);path=u.path;data={}
 if path.endswith('/campuses'):data=[{'id':c,'name':'Controlled campus','is_active':True}]
 elif path.endswith('/auth/me'):data={'id':'controlled-student','role':'student','campus_id':c,'profile':{'id':'controlled-student','role':'student','campus_id':c,'push_enabled':False}}
 elif path.endswith('/storefront/banners'):
  counts['banners']+=1;data=[{'id':'hero','placement':'hero','title':'Recovered hero','image_url':'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg"/>','is_active':True}] if state['recovered'] else []
 elif path.endswith('/storefront/sections'):data=[]
 elif path.endswith('/notifications/preferences'):
  if req.method=='PATCH':preferences.append(req.post_data_json)
  data={'push_enabled':req.method=='PATCH','email_enabled':True}
 elif path.endswith('/auth/device-token'):
  tokens.append(req.post_data_json)
  if state['fail_token']:state['fail_token']=False;route.fulfill(status=503,json={'error':'Controlled registration outage'});return
  assert req.post_data_json['token']=='controlled-subscription' and 'player_id' not in req.post_data_json
  data={'message':'Device registered'}
 elif path.endswith('/cart'):data={'items':[]}
 route.fulfill(status=200,json=data)
def sdk(route):
 counts['sdk']+=1
 route.fulfill(content_type='text/javascript',body="""(()=>{const events={};const sdk={init:async options=>{window.__pushOptions=options},login:async id=>{window.__pushUser=id},logout:async()=>{},User:{PushSubscription:{id:null,optedIn:false,addEventListener:(key,cb)=>{events[key]=cb},removeEventListener:()=>{},optIn:async()=>{sdk.User.PushSubscription.id='controlled-subscription';sdk.User.PushSubscription.optedIn=true;window.__optedIn=true},optOut:async()=>{sdk.User.PushSubscription.optedIn=false}}},Notifications:{addEventListener:()=>{},removeEventListener:()=>{},requestPermission:async()=>{window.__nativePermissionCalls=(window.__nativePermissionCalls||0)+1}}};window.__pushSdk=sdk;const q=window.OneSignalDeferred||[];q.push=fn=>{queueMicrotask(()=>fn(sdk));return 1};window.OneSignalDeferred=q;})();""")
harness=repo/'src/components/__audit_resume_harness.tsx';harness.write_text("""import React from 'react';import {MemoryRouter} from 'react-router-dom';import {HolyGrillProvider} from '@/lib/HolyGrillContext';import {CampusProvider} from '@/lib/campusContext';import Hero from './HeroCarousel';export default function Harness(){return <MemoryRouter><HolyGrillProvider><CampusProvider><input aria-label="Unsaved input"/><Hero/></CampusProvider></HolyGrillProvider></MemoryRouter>}""")
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5228','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api',VITE_ONESIGNAL_APP_ID='controlled-app-id'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
try:
 time.sleep(2)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);ctx=browser.new_context(viewport={'width':390,'height':844});ctx.route('**/api/**',api);ctx.route('https://cdn.onesignal.com/**',sdk)
  ctx.add_init_script("Object.defineProperty(window,'Notification',{value:class {static permission='granted'}})")
  page=ctx.new_page();page.set_default_timeout(8000);page.goto('http://127.0.0.1:5228/faq');page.get_by_role('button',name='Essential only',exact=True).click();page.wait_for_timeout(100);assert counts['sdk']==0
  page.evaluate("localStorage.setItem('hg_campus_id','"+c+"')")
  page.evaluate("""async()=>{const R=await import('/node_modules/.vite/deps/react.js');const React=R.default||R;const D=await import('/node_modules/.vite/deps/react-dom_client.js');const {default:Harness}=await import('/src/components/__audit_resume_harness.tsx');document.getElementById('root').hidden=true;const host=document.createElement('div');document.body.append(host);(D.createRoot||D.default.createRoot)(host).render(React.createElement(Harness));window.documentMarker='preserved';}""")
  page.get_by_label('Unsaved input').fill('keep this draft');page.wait_for_timeout(100);before=counts['banners'];state['recovered']=True
  page.evaluate("window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}))")
  expect(page.get_by_role('heading',name='Recovered hero',exact=True)).to_be_visible();assert counts['banners']>before and page.evaluate('window.documentMarker')=='preserved';expect(page.get_by_label('Unsaved input')).to_have_value('keep this draft')
  after=counts['banners'];page.evaluate("window.dispatchEvent(new Event('focus'));window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}))");page.wait_for_timeout(100);assert counts['banners']==after
  # Android/browser tab suspension usually resumes via visibilitychange.
  page.evaluate("""()=>{const now=Date.now.bind(Date);let offset=20000;Date.now=()=>now()+offset;let visible='hidden';Object.defineProperty(document,'visibilityState',{configurable:true,get:()=>visible});document.dispatchEvent(new Event('visibilitychange'));offset+=6000;visible='visible';document.dispatchEvent(new Event('visibilitychange'));}""")
  expect(page.get_by_role('heading',name='Recovered hero',exact=True)).to_be_visible();page.wait_for_timeout(150);assert counts['banners']>after
  # A signed-in user with granted browser permission but no subscription must
  # still see Enable; registration failure must remain visible and retryable.
  page.evaluate("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_campus_id','"+c+"')")
  page.goto('http://127.0.0.1:5228/notification-preferences');expect(page.get_by_role('button',name='Enable',exact=True)).to_be_visible();page.wait_for_function('window.__pushUser === "controlled-student"')
  assert page.evaluate('window.__pushOptions.promptOptions.slidedown.prompts[0].autoPrompt') is False
  page.get_by_role('button',name='Enable',exact=True).click();expect(page.get_by_role('alert').filter(has_text='Controlled registration outage')).to_be_visible();expect(page.get_by_text('Push notifications enabled',exact=True)).to_have_count(0)
  page.get_by_role('button',name='Enable',exact=True).click();expect(page.get_by_text('Push notifications enabled',exact=True)).to_be_visible();assert len(tokens)==2 and preferences[-1]=={'push_enabled':True} and page.evaluate('window.__optedIn') is True
  assert page.evaluate('window.__nativePermissionCalls || 0')==0
  browser.close()
 print(json.dumps({'guest_does_not_initialize_sdk_before_campus':True,'resume_recovers_missing_hero':True,'unsaved_input_and_document_preserved':True,'focus_and_duplicate_resume_coalesced':True,'permission_alone_not_success':True,'backend_token_contract':True,'outage_visible_and_retry_succeeds':True,'opt_in_and_delivery_preference_saved':True}))
finally:
 harness.unlink(missing_ok=True);os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
