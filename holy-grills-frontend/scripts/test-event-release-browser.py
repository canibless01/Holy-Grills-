"""Native install UI with controlled browser events/API; no remote writes."""
import json,os,signal,subprocess,tempfile,time
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
repo=Path(__file__).resolve().parents[1];out=Path(tempfile.mkdtemp(prefix='hg-install-ui-'));campus='11111111-1111-4111-8111-111111111111';events_enabled=False;event_reads=[]
def fixture(route):
 p=urlparse(route.request.url).path;data=[]
 if p.endswith('/auth/me'):data={'id':'controlled-user','role':'student','campus_id':campus,'full_name':'Controlled user','profile':{'id':'controlled-user','role':'student','campus_id':campus}}
 elif p.endswith('/storefront/feature-flags'):data=[{'feature_name':'events','is_active':events_enabled}]
 elif p.endswith('/events'):event_reads.append(p);data=[]
 elif p.endswith('/campuses'):data=[{'id':campus,'name':'Controlled campus','is_active':True}]
 elif p.endswith('/cart'):data={'items':[]}
 elif any(x in p for x in ('messages','config','feature-flags','balance','streak')):data={}
 route.fulfill(status=200,json=data)
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5215','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
try:
 time.sleep(2)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox']);ctx=browser.new_context(viewport={'width':390,'height':844});ctx.route('**/api/**',fixture)
  ctx.add_init_script("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_campus_id','"+campus+"');localStorage.setItem('hg_user_campus_id','"+campus+"');localStorage.setItem('hg_install_dismissed','1');")
  p=ctx.new_page();p.goto('http://127.0.0.1:5215/events');p.get_by_role('button',name='Essential only',exact=True).click();expect(p.get_by_role('heading',name='Events are coming soon',exact=True)).to_be_visible();assert not event_reads
  p.goto('http://127.0.0.1:5215/events/some-event');expect(p.get_by_role('heading',name='Events are coming soon',exact=True)).to_be_visible();assert not event_reads
  events_enabled=True;p.goto('http://127.0.0.1:5215/events');expect(p.get_by_role('heading',name='Somewhere to be.',exact=True)).to_be_visible();assert event_reads
  browser.close()
 print(json.dumps({'off_list_coming_soon_without_event_read':True,'off_direct_detail_coming_soon':True,'on_restores_events':True}))
finally:os.killpg(proc.pid,signal.SIGTERM)
