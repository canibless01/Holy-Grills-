"""Native economics scope, late replies and partial failure. Controlled HTTP only."""
import os, signal, subprocess, tempfile, time
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import sync_playwright,expect
repo=Path(__file__).resolve().parents[1];out=Path(tempfile.mkdtemp(prefix='hg-econ-'))
a='11111111-1111-4111-8111-111111111111';b='22222222-2222-4222-8222-222222222222'
role='super_admin';partial=False;hold=False;held=[];reads=[]
def fixture(route):
 req=route.request;url=urlparse(req.url);path=url.path;q=parse_qs(url.query);data={}
 if path.endswith('/auth/me'):data={'id':'controlled','role':role,'campus_id':a,'profile':{'id':'controlled','role':role,'campus_id':a}}
 elif path.endswith('/campuses'):data=[{'id':a,'name':'Campus A','is_active':True},{'id':b,'name':'Campus B','is_active':True}]
 elif '/admin/economics/' in path:
  campus=q.get('campus_id',[None])[0];reads.append((path,campus,q));assert 'start_date' in q and 'end_date' in q
  if hold and campus==a:held.append(route);return
  if partial and path.endswith('/tier-breakdown'):route.fulfill(status=503,json={'error':'controlled failure'});return
  data={'food_revenue':111 if campus==a else 222 if campus==b else 333} if path.endswith('/overview') else [] if path.endswith('/tier-breakdown') else {}
 route.fulfill(status=200,json=data)
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5262','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
try:
 time.sleep(2)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);ctx=browser.new_context(viewport={'width':1280,'height':1000});ctx.route('**/api/**',fixture)
  ctx.add_init_script("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_role','super_admin');localStorage.setItem('hg_user_campus_id','"+a+"');localStorage.removeItem('hg_admin_campus_id');")
  page=ctx.new_page();page.clock.set_fixed_time(datetime(2026,11,5,23,30,tzinfo=timezone.utc));page.goto('http://127.0.0.1:5262/admin?section=economics');expect(page.get_by_text('Food Revenue',exact=True)).to_be_visible();assert reads[-1][1] is None
  expect(page.get_by_label('To date',exact=True)).to_have_value('2026-11-06');expect(page.get_by_label('From date',exact=True)).to_have_value('2026-10-07')
  page.get_by_role('button',name='All Campuses',exact=True).click();page.get_by_role('button',name='Campus A',exact=True).click();expect(page.get_by_text('Food Revenue',exact=True)).to_be_visible();assert reads[-1][1]==a
  hold=True;page.get_by_role('button',name='Refresh',exact=True).click();page.wait_for_timeout(150);assert len(held)==3
  page.get_by_role('button',name='Campus A',exact=True).click();page.get_by_role('button',name='Campus B',exact=True).click();expect(page.get_by_text('Food Revenue',exact=True)).to_be_visible();assert reads[-1][1]==b
  for route in held:route.fulfill(status=200,json={'food_revenue':999} if route.request.url.split('?')[0].endswith('/overview') else [] if '/tier-breakdown' in route.request.url else {})
  expect(page.locator('body')).not_to_contain_text('₦999');expect(page.locator('body')).to_contain_text('₦222')
  partial=True;page.get_by_role('button',name='Refresh',exact=True).click();expect(page.get_by_text('Economics data unavailable',exact=True)).to_be_visible();expect(page.get_by_text('Food Revenue',exact=True)).to_have_count(0)
  expect(page.get_by_label('From date',exact=True)).to_be_visible();expect(page.get_by_label('To date',exact=True)).to_be_visible()
  partial=False;page.get_by_role('button',name='Retry',exact=True).click();expect(page.get_by_text('Food Revenue',exact=True)).to_be_visible();ctx.close()
  role='admin';hold=False;ctx=browser.new_context(viewport={'width':1280,'height':1000});ctx.route('**/api/**',fixture)
  ctx.add_init_script("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_role','admin');localStorage.setItem('hg_user_campus_id','"+a+"');localStorage.setItem('hg_admin_campus_id','"+b+"');")
  page=ctx.new_page();page.goto('http://127.0.0.1:5262/admin?section=economics');expect(page.get_by_text('Food Revenue',exact=True)).to_be_visible();assert reads[-1][1]==a
  ctx.close();browser.close()
 print('PASS: all-campus and selected-campus economics; three shared scoped/date reads; late replies ignored; partial failure hides incomplete totals and preserves date controls; retry recovery; regular admin pinned to profile campus')
finally:
 os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
