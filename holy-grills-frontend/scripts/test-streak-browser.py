"""Native install UI with controlled browser events/API; no remote writes."""
import json,os,signal,subprocess,tempfile,time
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
repo=Path(__file__).resolve().parents[1];out=Path(tempfile.mkdtemp(prefix='hg-install-ui-'));campus='11111111-1111-4111-8111-111111111111';summary_available=True
def fixture(route):
 p=urlparse(route.request.url).path;data=[]
 if p.endswith('/auth/me'):data={'id':'controlled-user','role':'student','campus_id':campus,'full_name':'Controlled user','profile':{'id':'controlled-user','role':'student','campus_id':campus}}
 elif p.endswith('/auth/streak'):data={'streak_count':1,'consecutive_weeks':99,'week_progress':{'days':{'Mon':'checked','Tue':'reclaimed','Wed':'missed','Thu':'upcoming','Fri':'upcoming','Sat':'upcoming','Sun':'upcoming'}},'order_streak':{'streak_weeks':3,'longest_streak':6,'counted_this_week':True,'repeat_after_week':12,'rewards':[{'weeks':3,'hp_awarded':100},{'weeks':6,'hp_awarded':200},{'weeks':12,'hp_awarded':350}]} if summary_available else None}
 elif p.endswith('/campuses'):data=[{'id':campus,'name':'Controlled campus','is_active':True}]
 elif p.endswith('/cart'):data={'items':[]}
 elif any(x in p for x in ('messages','config','feature-flags','balance','streak')):data={}
 route.fulfill(status=200,json=data)
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5213','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
try:
 time.sleep(2)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox']);ctx=browser.new_context(viewport={'width':390,'height':844});ctx.route('**/api/**',fixture)
  ctx.add_init_script("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_campus_id','"+campus+"');localStorage.setItem('hg_user_campus_id','"+campus+"');localStorage.setItem('hg_install_dismissed','1');")
  p=ctx.new_page();p.goto('http://127.0.0.1:5213/dashboard');p.get_by_role('button',name='Essential only',exact=True).click()
  order_card=p.locator('a[href="/streak#ordering-streak"]');expect(order_card).to_be_visible();expect(order_card).to_contain_text('3');expect(order_card).not_to_contain_text('99');order_card.click()
  section=p.locator('#ordering-streak');expect(section).to_be_visible();expect(section).to_contain_text('3');expect(section).to_contain_text('Week 3');expect(section).to_contain_text('Week 6');expect(section).to_contain_text('Week 12');expect(section).to_contain_text('Week secured');expect(p.get_by_role('heading',name='Login streak',exact=True)).to_be_visible();expect(p.get_by_role('heading',name='Missed a day? Reclaim it.',exact=True)).to_be_visible();expect(p.get_by_role('heading',name='Install & Push Bonuses',exact=True)).to_have_count(0)
  flames=p.get_by_role('list',name='Daily check-in flames',exact=True);expect(flames.get_by_role('listitem')).to_have_count(7);expect(flames.locator('[data-checked="true"]')).to_have_count(2);expect(flames.get_by_label('Wed: missed',exact=True)).to_be_visible()
  assert p.evaluate("getComputedStyle(document.documentElement).overscrollBehaviorY")=="auto"
  assert p.evaluate("getComputedStyle(document.body).overscrollBehaviorY")=="auto"
  p.wait_for_timeout(900)
  p.screenshot(path='/tmp/hg-streak-design-mobile.png',full_page=True)
  p.set_viewport_size({'width':1280,'height':900});p.screenshot(path='/tmp/hg-streak-design-desktop.png',full_page=True)
  summary_available=False;p.reload();expect(p.get_by_text('Your ordering streak could not be loaded.',exact=True)).to_be_visible();expect(p.locator('#ordering-streak').get_by_role('button',name='Retry',exact=True)).to_be_visible()
  browser.close()
 print(json.dumps({'dashboard_uses_order_not_login_weeks':True,'click_opens_both_streaks':True,'configured_milestone_rewards_visible':True,'unavailable_summary_shows_retry_not_zero':True,'seven_flames_follow_saved_checkins':True,'native_vertical_overscroll_restored':True}))
finally:os.killpg(proc.pid,signal.SIGTERM)
