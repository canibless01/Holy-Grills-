"""Unread notification still opens its destination when mark-read is unavailable."""
import json,os,signal,subprocess,tempfile,time
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
repo=Path(__file__).resolve().parents[1];out=Path(tempfile.mkdtemp(prefix='hg-notification-open-'));c='11111111-1111-4111-8111-111111111111';uid='22222222-2222-4222-8222-222222222222';reads=[]
def fixture(route):
 req=route.request;path=urlparse(req.url).path;data={}
 if path.endswith('/auth/me'):data={'id':uid,'role':'student','campus_id':c,'profile':{'id':uid,'role':'student','campus_id':c}}
 elif path.endswith('/campuses'):data=[{'id':c,'name':'Controlled campus','is_active':True}]
 elif path.endswith('/notifications'):data={'notifications':[{'id':'notice','title':'Cart waiting test','body':'Resume checkout','action_url':'/cart?reminder=1','read_at':None}],'unread_count':1}
 elif path.endswith('/notifications/notice/read'):
  reads.append(True);route.fulfill(status=503,json={'error':'Controlled unavailable read receipt'});return
 elif path.endswith('/cart'):data={'items':[]}
 elif path.endswith('/menu') or path.endswith('/storefront/sections') or path.endswith('/gates'):data=[]
 route.fulfill(status=200,json=data)
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5232','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
try:
 time.sleep(2)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);ctx=browser.new_context(viewport={'width':1280,'height':1000});ctx.route('**/api/**',fixture)
  ctx.add_init_script("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_campus_id','"+c+"')")
  page=ctx.new_page();page.set_default_timeout(8000);page.goto('http://127.0.0.1:5232/notifications');page.get_by_role('button',name='Essential only',exact=True).click();page.get_by_text('Cart waiting test',exact=True).click();expect(page).to_have_url('http://127.0.0.1:5232/cart?reminder=1');assert reads
  browser.close()
 print(json.dumps({'unread_notification_opens_cart_when_read_receipt_fails':True,'query_preserved':True}))
finally:os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
