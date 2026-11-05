"""Native install UI with controlled browser events/API; no remote writes."""
import json,os,signal,subprocess,tempfile,time
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
repo=Path(__file__).resolve().parents[1];out=Path(tempfile.mkdtemp(prefix='hg-install-ui-'));campus='11111111-1111-4111-8111-111111111111'
def fixture(route):
 p=urlparse(route.request.url).path;data=[]
 if p.endswith('/auth/me'):data={'id':'controlled-user','role':'student','campus_id':campus,'full_name':'Controlled user','profile':{'id':'controlled-user','role':'student','campus_id':campus}}
 elif p.endswith('/campuses'):data=[{'id':campus,'name':'Controlled campus','is_active':True}]
 elif p.endswith('/cart'):data={'items':[]}
 elif any(x in p for x in ('messages','config','feature-flags','balance','streak')):data={}
 route.fulfill(status=200,json=data)
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5212','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
try:
 time.sleep(2)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox']);ctx=browser.new_context(viewport={'width':390,'height':844});ctx.route('**/api/**',fixture)
  ctx.add_init_script("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_campus_id','"+campus+"');localStorage.setItem('hg_user_campus_id','"+campus+"');localStorage.setItem('hg_install_dismissed','1');")
  p=ctx.new_page();p.goto('http://127.0.0.1:5212/');p.get_by_role('button',name='Essential only',exact=True).click();p.wait_for_timeout(700)
  p.evaluate("window.__prompts=0;const e=new Event('beforeinstallprompt',{cancelable:true});e.prompt=async()=>{window.__prompts++};e.userChoice=Promise.resolve({outcome:'accepted'});window.dispatchEvent(e)")
  install=p.get_by_role('button',name='Install',exact=True);expect(install).to_be_visible();install.click();expect(install).to_have_count(0);assert p.evaluate('window.__prompts')==1
  p.goto('http://127.0.0.1:5212/profile');p.get_by_role('button',name='Install Holy Grills on this device',exact=True).click();expect(p.get_by_text('Open this site in Chrome or Edge',exact=False)).to_be_visible();p.get_by_role('button',name='Got it',exact=True).click()
  p.evaluate("const e=new Event('beforeinstallprompt',{cancelable:true});e.prompt=async()=>{};e.userChoice=Promise.resolve({outcome:'dismissed'});window.dispatchEvent(e)")
  expect(p.get_by_role('button',name='Install',exact=True)).to_have_count(0)
  p.get_by_role('button',name='Install Holy Grills on this device',exact=True).click();expect(p.get_by_role('button',name='Install',exact=True)).to_be_visible()
  p.evaluate("window.dispatchEvent(new Event('appinstalled'))");expect(p.get_by_role('button',name='Install',exact=True)).to_have_count(0)
  browser.close()
 print(json.dumps({'early_prompt_after_legacy_dismissal':True,'native_prompt_consumed_once':True,'profile_fallback_help':True,'manual_action_after_dismissal':True,'installed_event_hides_banner':True}))
finally:os.killpg(proc.pid,signal.SIGTERM)
