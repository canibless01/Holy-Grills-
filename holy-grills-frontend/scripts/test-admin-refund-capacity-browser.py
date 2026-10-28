"""Explicit delivered-refund review, capacity copy, hours preservation and role control."""
import re,json,os,signal,subprocess,tempfile,time
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
repo=Path(__file__).resolve().parents[1];out=Path(tempfile.mkdtemp(prefix='hg-refund-review-'));c='11111111-1111-4111-8111-111111111111';oid='22222222-2222-4222-8222-222222222222';uid='33333333-3333-4333-8333-333333333333';refunds=[];role_changes=[];hours_saves=[]
order={'id':oid,'user_id':uid,'status':'delivered','payment_status':'paid','subtotal':100,'total_amount':100,'wallet_amount_used':100,'card_amount_used':0,'wallet_refund_total':0,'card_refund_total':0,'order_items':[]}
user={'id':uid,'full_name':'Controlled customer','role':'student','campus_id':c,'is_active':True}
def fixture(route):
 req=route.request;path=urlparse(req.url).path;data={}
 if path.endswith('/auth/me'):data={'id':'controlled-super','role':'super_admin','profile':{'id':'controlled-super','role':'super_admin'}}
 elif path.endswith('/campuses'):data=[{'id':c,'name':'Controlled campus','is_active':True}]
 elif path.endswith('/admin/orders'):data={'orders':[order]}
 elif path.endswith('/orders/'+oid+'/history'):data=[]
 elif path.endswith('/orders/'+oid+'/refund'):
  refunds.append(req.post_data_json);amount=req.post_data_json['refund_amount'];order['wallet_refund_total']+=amount;order['payment_status']='partially_refunded' if order['wallet_refund_total']<100 else 'refunded';order['status']='delivered' if order['wallet_refund_total']<100 else 'refunded';data={'success':True,'refund_amount':amount}
 elif path.endswith('/admin/users'):data={'users':[user],'total':1}
 elif path.endswith('/admin/users/'+uid+'/role'):
  role_changes.append(req.post_data_json);user['role']=req.post_data_json['role'];data={'user_id':uid,'role':user['role']}
 elif path.endswith('/storefront/operating-hours'):
  if req.method=='PATCH':hours_saves.append(req.post_data_json)
  data={'schedule':[{'weekday':0,'opens_at':'10:15','closes_at':'22:30','is_closed':False,'campus_id':c}], 'today_override':None,'effective_source':'date','is_open':True}
 elif path.endswith('/storefront/sections') or path.endswith('/storefront/early-supporters'):data=[]
 elif path.endswith('/cart'):data={'items':[]}
 elif '/delivery-' in path or '/ordering-windows' in path or '/abandoned-carts' in path or path.endswith('/hostels') or path.endswith('/gates'):data=[]
 route.fulfill(status=200,json=data)
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5230','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
try:
 time.sleep(2)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);ctx=browser.new_context(viewport={'width':1280,'height':1000});ctx.route('**/api/**',fixture)
  ctx.add_init_script("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_campus_id','"+c+"');localStorage.setItem('hg_admin_campus_id','"+c+"')")
  page=ctx.new_page();page.set_default_timeout(8000);page.goto('http://127.0.0.1:5230/admin?section=orders');page.get_by_role('button',name='Essential only',exact=True).click();page.get_by_text('#'+oid.upper(),exact=True).click();page.get_by_role('button',name='Refund',exact=True).click()
  expect(page.get_by_role('button',name='Confirm Refund',exact=True)).to_be_disabled();expect(page.get_by_label('Refund amount (₦)',exact=True)).to_have_value('')
  page.get_by_label('Refund type',exact=True).select_option('partial');page.get_by_label('Refund amount (₦)',exact=True).fill('25');page.get_by_label('Reason',exact=True).fill('Reviewed delivered complaint')
  expect(page.get_by_role('button',name='Confirm Refund',exact=True)).to_be_disabled();page.get_by_label('I have reviewed the delivered order and authorise this refund.',exact=True).check();page.get_by_role('button',name='Confirm Refund',exact=True).click();page.wait_for_timeout(150)
  assert refunds[0]['refund_amount']==25 and refunds[0]['acknowledge_delivered'] is True
  page.get_by_role('button',name='Refund',exact=True).click();page.get_by_label('Refund type',exact=True).select_option('full');expect(page.get_by_label('Refund amount (₦)',exact=True)).to_have_value('75');expect(page.get_by_label('Refund amount (₦)',exact=True)).to_be_disabled();page.get_by_label('Reason',exact=True).fill('Remaining compensation');page.get_by_label('I have reviewed the delivered order and authorise this refund.',exact=True).check();page.get_by_role('button',name='Confirm Refund',exact=True).click();page.wait_for_timeout(150)
  assert refunds[1]['refund_amount']==75 and refunds[1]['idempotency_key']!=refunds[0]['idempotency_key']
  page.goto('http://127.0.0.1:5230/admin?section=delivery');page.get_by_role('button',name='Delivery times',exact=True).click();expect(page.get_by_text('Daily kitchen slots',exact=True)).to_be_visible();expect(page.get_by_text('Ordering-window slots',exact=True)).to_be_visible();expect(page.get_by_text('Delivery planning target',exact=True)).to_be_visible()
  page.goto('http://127.0.0.1:5230/admin?section=users');role=page.locator('select[title="Change role"]').first;expect(role.locator('option[value="community_manager"]')).to_have_count(1);role.select_option('community_manager');page.wait_for_timeout(150);assert role_changes[-1]['role']=='community_manager'
  page.goto('http://127.0.0.1:5230/admin?section=storefront');page.get_by_role('button',name=re.compile(r'^Hours')).click();expect(page.get_by_text('Today has a date-specific ordering window. Its hours take priority over this override.',exact=True)).to_be_visible();monday=page.get_by_text('Monday',exact=True).locator('..').locator('..');monday.get_by_role('button',name='Save',exact=True).click();page.wait_for_timeout(150);assert hours_saves[-1]['open_time']=='10:15' and hours_saves[-1]['close_time']=='22:30'
  browser.close()
 print(json.dumps({'explicit_partial_full_review':True,'delivered_ack_required':True,'remaining_balance_used':True,'distinct_refund_intents':True,'capacity_terms_distinguished':True,'super_admin_can_select_community_manager':True,'hours_save_preserves_stored_times':True}))
finally:os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
