"""Native webhook log: scope, stale replies, paging, read recovery and replay latch."""
import os,signal,subprocess,tempfile,time
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import sync_playwright,expect
repo=Path(__file__).resolve().parents[1];out=Path(tempfile.mkdtemp(prefix='hg-webhooks-'))
a='11111111-1111-4111-8111-111111111111';b='22222222-2222-4222-8222-222222222222'
reads=[];held=[];writes=[];write_routes=[];errors=[];fail=False;hold=False
expect.set_options(timeout=15000)
def rows(campus,offset):
 label='A' if campus==a else 'B' if campus==b else 'Global'
 return [{'id':str(i),'provider':'paystack','event_type':f'{label} delivery {i}','status':'failed' if i==0 else 'processed','campus_id':campus,'created_at':'2026-11-07T12:00:00Z','reference':f'controlled-{i}'} for i in range(offset,min(offset+50,51))]
def fixture(route):
 req=route.request;url=urlparse(req.url);path=url.path;q=parse_qs(url.query);data={}
 if path.endswith('/auth/me'):data={'id':'controlled','role':'super_admin','campus_id':a,'profile':{'id':'controlled','role':'super_admin','campus_id':a}}
 elif path.endswith('/campuses'):data=[{'id':a,'name':'Campus A','is_active':True},{'id':b,'name':'Campus B','is_active':True}]
 elif '/admin/webhook-events/' in path and path.endswith('/retry'):writes.append(path);write_routes.append(route);return
 elif path.endswith('/admin/webhook-events'):
  campus=q.get('campus_id',[None])[0];offset=int(q.get('offset',['0'])[0]);reads.append((campus,q))
  if fail:route.fulfill(status=503,json={'error':'Controlled log failure'});return
  if hold and campus==a:held.append(route);return
  data={'webhook_events':rows(campus,offset)}
 route.fulfill(status=200,json=data)
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5267','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
try:
 time.sleep(2)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);ctx=browser.new_context(viewport={'width':1280,'height':1000});ctx.route('**/api/**',fixture)
  ctx.add_init_script("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_role','super_admin');localStorage.setItem('hg_user_campus_id','"+a+"');localStorage.removeItem('hg_admin_campus_id');")
  page=ctx.new_page();page.on('pageerror',lambda error:errors.append(str(error)));page.goto('http://127.0.0.1:5267/admin?section=webhooks');expect(page.get_by_text('Global delivery 0',exact=True)).to_be_visible()
  page.get_by_role('button',name='Next deliveries',exact=True).click();expect(page.get_by_text('Global delivery 50',exact=True)).to_be_visible();assert reads[-1][1]['offset']==['50']
  page.get_by_role('button',name='Previous deliveries',exact=True).click();expect(page.get_by_text('Global delivery 0',exact=True)).to_be_visible()
  page.get_by_role('button',name='All Campuses',exact=True).click();page.get_by_role('button',name='Campus A',exact=True).click();expect(page.get_by_text('A delivery 0',exact=True)).to_be_visible();assert reads[-1][0]==a
  page.get_by_text('A delivery 0',exact=True).click();page.get_by_role('button',name='Retry delivery',exact=True).evaluate('(b)=>{b.click();b.click()}');page.wait_for_timeout(200);assert len(writes)==1
  write_routes.pop().fulfill(status=200,json={'status':'processed'});expect(page.get_by_role('button',name='Refresh',exact=True)).to_be_enabled()
  fail=True;page.get_by_role('button',name='Refresh',exact=True).click();expect(page.get_by_role('alert')).to_contain_text('Controlled log failure');expect(page.get_by_text('No webhook events recorded',exact=True)).to_have_count(0)
  fail=False;page.get_by_role('button',name='Retry',exact=True).click();expect(page.get_by_text('A delivery 0',exact=True)).to_be_visible()
  hold=True;page.get_by_placeholder('Provider (e.g. paystack)',exact=True).fill('paystack');page.wait_for_timeout(250);assert held
  page.get_by_role('button',name='Campus A',exact=True).click();page.get_by_role('button',name='Campus B',exact=True).click();expect(page.get_by_text('B delivery 0',exact=True)).to_be_visible()
  for route in held:route.fulfill(status=200,json={'webhook_events':rows(a,0)})
  page.wait_for_timeout(100);expect(page.get_by_text('A delivery 0',exact=True)).to_have_count(0);assert reads[-1][0]==b
  assert not errors,errors
  browser.close();print('PASS: webhook campus scope/stale isolation, paging, failed read Retry, incoming-log empty state and duplicate replay latch; no real provider call')
finally:
 os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
