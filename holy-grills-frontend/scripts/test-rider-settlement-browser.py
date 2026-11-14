"""Real admin React settlement UI, controlled HTTP; no money is sent."""
import json,os,signal,subprocess,tempfile,time
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
repo=Path(__file__).resolve().parents[1];out=Path(tempfile.mkdtemp(prefix='hg-rider-settle-'))
c='11111111-1111-4111-8111-111111111111';r='22222222-2222-4222-8222-222222222222';b='33333333-3333-4333-8333-333333333333';writes=[]
batch={'batch_id':b,'status':'completed','rider_pay_total':500.25,'rider_paid_at':None,'order_count':2,'zone':'Test gate'}
def fixture(route):
 req=route.request;path=urlparse(req.url).path;data={}
 if path.endswith('/auth/me'):data={'id':'controlled-admin','role':'super_admin','profile':{'id':'controlled-admin','role':'super_admin'}}
 elif path.endswith('/campuses'):data=[{'id':c,'name':'Controlled campus','is_active':True}]
 elif path.endswith('/riders/admin/payments'):data={'riders':[{'rider_id':r,'full_name':'Controlled rider','completed_batches':2,'total_earned':500.25,'total_paid':0,'outstanding':500.25,'unpriced_batches':0}]}
 elif path.endswith('/riders/admin/payments/'+r):data={'batches':[batch]}
 elif path.endswith('/riders/admin/batches/'+b+'/pay'):
  writes.append(req.post_data_json);batch['rider_pay_total']=req.post_data_json['rider_pay_total'];data={'batch_id':b,**writes[-1]}
 elif path.endswith('/riders/admin/payments/mark-paid'):
  writes.append(req.post_data_json);batch['rider_paid_at']='2026-10-28T15:00:00+01:00';data={'updated':[b],'skipped':[],'not_found':[]}
 elif path.endswith('/riders/roster'):data={'riders':[]}
 elif path.endswith('/cart'):data={'items':[]}
 elif '/delivery-' in path or '/ordering-windows' in path or '/abandoned-carts' in path or path.endswith('/hostels') or path.endswith('/gates'):data=[]
 route.fulfill(status=200,json=data)
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5231','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
try:
 time.sleep(2)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);ctx=browser.new_context(viewport={'width':1280,'height':1000});ctx.route('**/api/**',fixture)
  ctx.add_init_script("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_campus_id','"+c+"');localStorage.setItem('hg_admin_campus_id','"+c+"')")
  page=ctx.new_page();page.set_default_timeout(8000);page.goto('http://127.0.0.1:5231/admin?section=delivery');page.get_by_role('button',name='Essential only',exact=True).click();page.get_by_role('button',name='Riders',exact=True).click();page.get_by_role('button',name='Payments',exact=True).click()
  expect(page.get_by_text('Recording payment does not send money.',exact=False)).to_be_visible()
  summary=page.get_by_role('button',name='Controlled rider',exact=False);expect(summary).to_contain_text('500.25');expect(summary).to_contain_text('2 batches');summary.click()
  page.get_by_title('Set pay',exact=True).click();page.get_by_label('Rider pay total (₦)',exact=True).fill('');page.get_by_role('button',name='Save Pay',exact=True).click();expect(page.get_by_text('Enter a valid amount.',exact=False)).to_be_visible();assert not writes
  page.get_by_label('Rider pay total (₦)',exact=True).fill('600.50');page.get_by_role('button',name='Save Pay',exact=True).click();page.wait_for_timeout(200);assert writes[0]['rider_pay_total']==600.5
  page.get_by_role('button',name='Record paid',exact=True).click();page.wait_for_timeout(200);assert writes[1]['batch_ids']==[b]
  expect(page.get_by_role('button',name='Undo paid record',exact=True)).to_be_visible();expect(page.get_by_title('Set pay',exact=True)).to_be_disabled()
  browser.close()
 print(json.dumps({'correct_earnings_and_batch_count':True,'external_payment_explained':True,'blank_price_refused':True,'set_pay_and_record_reflect':True,'paid_price_edit_disabled':True}))
finally:os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
