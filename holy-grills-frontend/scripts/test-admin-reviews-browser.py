"""Reviews campus isolation, paging/filter/search, expansion and read recovery."""
import os,signal,subprocess,tempfile,time
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import sync_playwright,expect
repo=Path(__file__).resolve().parents[1];out=Path(tempfile.mkdtemp(prefix='hg-reviews-'))
a='11111111-1111-4111-8111-111111111111';b='22222222-2222-4222-8222-222222222222'
role='super_admin';reads=[];hold=False;held=[];fail=False;errors=[]
expect.set_options(timeout=15000)

def fixture(route):
 req=route.request;url=urlparse(req.url);path=url.path;q=parse_qs(url.query);data={}
 if path.endswith('/auth/me'):data={'id':'controlled','role':role,'campus_id':a,'profile':{'id':'controlled','role':role,'campus_id':a}}
 elif path.endswith('/campuses'):data=[{'id':a,'name':'Campus A','is_active':True},{'id':b,'name':'Campus B','is_active':True}]
 elif path.endswith('/admin/reviews'):
  campus=q.get('campus_id',[None])[0];reads.append((campus,q))
  if fail:route.fulfill(status=503,json={'error':'Controlled review read failure'});return
  if hold and campus==a:held.append(route);return
  label='A' if campus==a else 'B' if campus==b else 'Global'
  rows=[{'id':str(i),'rating':5 if i%2 else 1,'is_flagged':not i%2,'profiles':{'full_name':f'{label} customer {i}'},'review_text':f'{label} review text {i}','kitchen_rating':4,'rider_rating':3,'created_at':'2026-11-05T12:00:00Z'} for i in range(26)]
  if 'rating' in q:rows=[r for r in rows if r['rating']==int(q['rating'][0])]
  if 'is_flagged' in q:rows=[r for r in rows if r['is_flagged']==(q['is_flagged'][0]=='true')]
  offset=int(q.get('offset',['0'])[0]);limit=int(q.get('limit',['25'])[0]);data={'reviews':rows[offset:offset+limit],'total':len(rows)}
 route.fulfill(status=200,json=data)
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5263','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
try:
 time.sleep(2)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);ctx=browser.new_context(viewport={'width':1280,'height':1000});ctx.route('**/api/**',fixture)
  ctx.add_init_script("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_role','super_admin');localStorage.setItem('hg_user_campus_id','"+a+"');localStorage.removeItem('hg_admin_campus_id');")
  page=ctx.new_page();page.on('pageerror',lambda error: errors.append(str(error)));page.goto('http://127.0.0.1:5263/admin?section=reviews');expect(page.get_by_text('Global customer 0',exact=True)).to_be_visible();assert reads[-1][0] is None
  page.get_by_role('button',name='All Campuses',exact=True).click();page.get_by_role('button',name='Campus A',exact=True).click();expect(page.get_by_text('A customer 0',exact=True)).to_be_visible();assert reads[-1][0]==a
  expect(page.get_by_text('This page: 25 reviews · average 2.9★',exact=True)).to_be_visible();page.get_by_text('A customer 0',exact=True).click();expect(page.get_by_text('A review text 0',exact=True)).to_be_visible()
  page.get_by_role('button',name='Next',exact=True).click();expect(page.get_by_text('A customer 25',exact=True)).to_be_visible();assert reads[-1][1]['offset']==['25']
  page.get_by_label('Rating filter',exact=True).select_option('5');expect(page.get_by_text('A customer 1',exact=True)).to_be_visible();assert reads[-1][1]['offset']==['0'] and reads[-1][1]['rating']==['5']
  page.get_by_label('Flag filter',exact=True).select_option('unflagged');expect(page.get_by_text('A customer 1',exact=True)).to_be_visible();assert reads[-1][1]['is_flagged']==['false']
  page.get_by_label('Search this page…',exact=True).fill('A customer 25');expect(page.get_by_text('A customer 25',exact=True)).to_be_visible();expect(page.get_by_text('A customer 1',exact=True)).to_have_count(0)
  hold=True;page.get_by_role('button',name='Refresh reviews',exact=True).click();page.wait_for_timeout(150);assert held
  page.get_by_role('button',name='Campus A',exact=True).click();page.get_by_role('button',name='Campus B',exact=True).click();expect(page.get_by_text('B customer 0',exact=True)).to_be_visible();assert reads[-1][0]==b and reads[-1][1]['offset']==['0'] and 'rating' not in reads[-1][1]
  for route in held:route.fulfill(status=200,json={'reviews':[{'id':'late','profiles':{'full_name':'LATE A'}}],'total':1})
  expect(page.get_by_text('LATE A',exact=True)).to_have_count(0)
  fail=True;page.get_by_role('button',name='Refresh reviews',exact=True).click();expect(page.get_by_text("We couldn't load this page. Please try again.",exact=True)).to_be_visible();expect(page.get_by_text('No reviews found.',exact=True)).to_have_count(0)
  fail=False;page.get_by_role('button',name='Retry',exact=True).click();expect(page.get_by_text('B customer 0',exact=True)).to_be_visible();ctx.close()
  role='admin';hold=False;ctx=browser.new_context(viewport={'width':1280,'height':1000});ctx.route('**/api/**',fixture);ctx.add_init_script("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_role','admin');localStorage.setItem('hg_user_campus_id','"+a+"');localStorage.setItem('hg_admin_campus_id','"+b+"');")
  page=ctx.new_page();page.on('pageerror',lambda error: errors.append(str(error)));page.goto('http://127.0.0.1:5263/admin?section=reviews');expect(page.get_by_text('A customer 0',exact=True)).to_be_visible();assert reads[-1][0]==a
  ctx.close();browser.close();assert not errors,errors
 print('PASS: review campus scope, regular-admin profile scope, page summary, expansion, paging, rating/flag filters, page search, campus state reset, late reply isolation and read Retry')
finally:
 os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
