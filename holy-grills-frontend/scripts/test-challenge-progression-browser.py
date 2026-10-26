"""Native install UI with controlled browser events/API; no remote writes."""
import json,os,signal,subprocess,tempfile,time
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
repo=Path(__file__).resolve().parents[1];out=Path(tempfile.mkdtemp(prefix='hg-install-ui-'));campus='11111111-1111-4111-8111-111111111111';claimed=False
def fixture(route):
 global claimed
 p=urlparse(route.request.url).path;data=[]
 if p.endswith('/auth/me'):data={'id':'controlled-user','role':'student','campus_id':campus,'full_name':'Controlled user','profile':{'id':'controlled-user','role':'student','campus_id':campus}}
 elif p.endswith('/challenges/my'):
  rows=[{'id':'one','title':'Invite one friend','trigger_type':'referral_count','trigger_value':1,'hp_awarded':10,'progress':1},{'id':'five','title':'Invite five friends','trigger_type':'referral_count','trigger_value':5,'hp_awarded':50,'progress':1},{'id':'ten','title':'Invite ten friends','trigger_type':'referral_count','trigger_value':10,'hp_awarded':100,'progress':1},{'id':'orders','title':'New weekly order challenge','trigger_type':'order_count','time_window':'weekly','trigger_value':3,'hp_awarded':25,'progress':1}]
  data={'milestones_available':rows[1:] if claimed else rows,'milestones_completed':[rows[0]] if claimed else [],'challenges_available':[],'challenges_completed':[]}
 elif p.endswith('/challenges/one/complete'):
  claimed=True;data={'hp_awarded':10}
 elif p.endswith('/challenges/pwa-push-bonus-status'):data={'pwa_install':True,'push_subscribe':True,'bonus_completed':True}
 elif p.endswith('/campuses'):data=[{'id':campus,'name':'Controlled campus','is_active':True}]
 elif p.endswith('/cart'):data={'items':[]}
 elif any(x in p for x in ('messages','config','feature-flags','balance','streak')):data={}
 route.fulfill(status=200,json=data)
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5216','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
try:
 time.sleep(2)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox']);ctx=browser.new_context(viewport={'width':390,'height':844});ctx.route('**/api/**',fixture)
  ctx.add_init_script("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_campus_id','"+campus+"');localStorage.setItem('hg_user_campus_id','"+campus+"');localStorage.setItem('hg_install_dismissed','1');")
  p=ctx.new_page();p.goto('http://127.0.0.1:5216/rewards?tab=challenges');p.get_by_role('button',name='Essential only',exact=True).click()
  first=p.get_by_role('heading',name='Invite one friend',exact=True);expect(first).to_be_visible();expect(p.get_by_role('heading',name='Invite five friends',exact=True)).to_have_count(0);expect(p.get_by_role('heading',name='Invite ten friends',exact=True)).to_have_count(0);expect(p.get_by_role('heading',name='New weekly order challenge',exact=True)).to_be_visible()
  first.locator('xpath=../..').locator('xpath=..').get_by_role('button',name='Claim',exact=True).click();expect(p.get_by_role('heading',name='Invite five friends',exact=True)).to_be_visible();expect(p.get_by_role('heading',name='Invite ten friends',exact=True)).to_have_count(0);expect(first).to_have_count(0);expect(p.locator('summary').filter(has_text='Completed (1)')).to_be_visible();expect(p.get_by_role('heading',name='New weekly order challenge',exact=True)).to_be_visible()
  browser.close()
 print(json.dumps({'only_next_referral_visible':True,'claim_reveals_next_step':True,'unrelated_challenge_retained':True,'completed_history_collapsed':True}))
finally:os.killpg(proc.pid,signal.SIGTERM)
