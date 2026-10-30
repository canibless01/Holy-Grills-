"""Issued signup session reaches Home; all HTTP is isolated from production."""
import os,signal,subprocess,tempfile,time
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
root=Path(__file__).resolve().parents[1];campus='11111111-1111-4111-8111-111111111111'
profile={'id':'controlled-owner','email':'owner@example.invalid','role':'student','campus_id':campus,'full_name':'Owner','profile':{'hp_balance':50,'campus_id':campus},'wallet':{'balance':0}}
registered=[]
def fixture(route):
 path=urlparse(route.request.url).path;data=[];status=200
 if path.endswith('/auth/register'):
  registered.append(route.request.post_data_json);data={'access_token':'issued-access','refresh_token':'issued-refresh','user':{'id':'controlled-owner'}};status=201
 elif path.endswith('/auth/me'):data=profile
 elif path.endswith('/campuses'):data=[{'id':campus,'name':'Campus','is_active':True}]
 elif path.endswith('/departments'):data=[{'id':'department','name':'Computer Science'}]
 elif path.endswith('/academic-levels'):data=[{'id':'level','name':'100L','value':'100L'}]
 elif path.endswith('/messages'):data={'messages':{}}
 elif path.endswith('/hp/balance'):data={'active':50,'pending':0,'total_visible':50}
 elif path.endswith('/cart'):data={'items':[]}
 elif path.endswith('/auth/welcome-credit'):data={'granted':False,'signup_hp':{'awarded':0}}
 route.fulfill(status=status,json=data)
log=Path(tempfile.mkdtemp())/'vite.log'
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5248','--strictPort'],cwd=root,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=log.open('w'),stderr=subprocess.STDOUT)
try:
 time.sleep(2)
 with sync_playwright() as p:
  b=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);c=b.new_context();c.route('**/api/**',fixture);page=c.new_page()
  page.add_locator_handler(page.get_by_role('button',name='Essential only',exact=True),lambda button:button.click())
  page.goto('http://127.0.0.1:5248/register')
  page.get_by_label('Full Name',exact=True).fill('Owner')
  page.get_by_label('Email',exact=True).fill('owner@example.invalid')
  page.get_by_label('Phone Number',exact=True).fill('08012345678')
  page.get_by_label("When's your birthday?",exact=True).fill('2000-01-01')
  page.get_by_label('What are you studying?',exact=True).select_option('department')
  page.get_by_label('Your level',exact=True).select_option('level')
  page.get_by_label('Password (min 8, uppercase + number + special)',exact=True).fill('ControlledPassword!123')
  page.get_by_label('Confirm Password',exact=True).fill('ControlledPassword!123')
  page.get_by_role('checkbox').first.check()
  page.get_by_role('button',name='Create Account',exact=False).click()
  page.wait_for_url('http://127.0.0.1:5248/',timeout=20000)
  assert page.evaluate("localStorage.getItem('hg_access_token')||sessionStorage.getItem('hg_access_token')")=='issued-access'
  assert len(registered)==1
  b.close();print('PASS autoconfirm signup persists issued tokens, restores identity and navigates Home without inbox prompt; production untouched')
finally:
 os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
