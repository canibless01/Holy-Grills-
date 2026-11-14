"""Native desktop/mobile menu closure; controlled API, no remote writes."""
import json,os,signal,subprocess,tempfile,time
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
repo=Path(__file__).resolve().parents[1];out=Path(tempfile.mkdtemp(prefix='hg-menu-'));campus='11111111-1111-4111-8111-111111111111'
def fixture(route):
 p=urlparse(route.request.url).path;data=[]
 if p.endswith('/auth/me'):data={'id':'controlled-user','role':'student','campus_id':campus,'full_name':'Controlled user','profile':{'id':'controlled-user','role':'student','campus_id':campus}}
 elif p.endswith('/campuses'):data=[{'id':campus,'name':'Controlled campus','is_active':True}]
 elif p.endswith('/cart'):data={'items':[]}
 elif any(x in p for x in ('messages','config','feature-flags','balance','streak')):data={}
 route.fulfill(status=200,json=data)
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5214','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
try:
 time.sleep(2)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
  for width in (1366,390):
   ctx=browser.new_context(viewport={'width':width,'height':900});ctx.route('**/api/**',fixture);ctx.add_init_script("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_campus_id','"+campus+"');localStorage.setItem('hg_user_campus_id','"+campus+"')")
   p=ctx.new_page();p.goto('http://127.0.0.1:5214/');p.get_by_role('button',name='Essential only',exact=True).click();account=p.get_by_role('button',name='Your account',exact=True);account.click();menu=p.get_by_role('button',name='Profile & Settings',exact=True);expect(menu).to_be_visible();menu.click();p.wait_for_url('**/profile');expect(menu).to_have_count(0);expect(p.get_by_role('button',name='Install Holy Grills on this device',exact=True)).to_be_visible()
   account.click();expect(menu).to_be_visible();menu.click();expect(menu).to_have_count(0)
   account.click();expect(menu).to_be_visible();p.keyboard.press('Escape');expect(menu).to_have_count(0)
   account.click();expect(menu).to_be_visible();p.get_by_role('button',name='Close menu',exact=True).click();expect(menu).to_have_count(0)
   ctx.close()
  browser.close()
 print(json.dumps({'desktop_and_mobile_navigation_closes':True,'same_page_closes':True,'escape_closes':True,'close_button_on_both_sizes':True}))
finally:os.killpg(proc.pid,signal.SIGTERM)
