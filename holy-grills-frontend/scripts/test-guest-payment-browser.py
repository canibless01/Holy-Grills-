"""Controlled native React routes; no accounts, provider calls, or remote writes."""
import json, os, signal, subprocess, time, tempfile
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright, expect
root=Path(tempfile.mkdtemp(prefix='hg-guest-return-')); repo=Path(__file__).resolve().parents[1]
oid='bbbb0000-0000-4000-8000-000000000099';token='cccc0000-0000-4000-8000-000000000099';campus='11111111-1111-4111-8111-111111111111';checks={};calls=[]
row={'id':'paid-cart-row','guest_campus_id':campus,'quantity':1,'menu_item_id':'menu-one','menu_items':{'name':'Fixture lunch','price':100,'is_available':True}}
other={'id':'new-cart-row','guest_campus_id':campus,'quantity':1,'menu_item_id':'menu-two','menu_items':{'name':'New lunch','price':200,'is_available':True}}
state={'paid':True,'verify_paid':False}
def fixture(route):
 req=route.request;u=urlparse(req.url);path=u.path;query=parse_qs(u.query);data=[];status=200
 if '/orders/'+oid in path or path.endswith('/orders/track'):
  proof=query.get('claim_token',[''])[0]
  if req.method=='POST':proof=(req.post_data_json or {}).get('claim_token')
  calls.append((path,proof==token))
  if proof!=token:status=404;data={'error':'Order not found'}
  elif path.endswith('/payment/verify'):
   if state['verify_paid']:state['paid']=True
   data={'payment_status':'paid' if state['paid'] else 'pending'}
  else:data={'id':oid,'order_number':'HG-RETURN','user_id':None,'status':'received','payment_status':'paid' if state['paid'] else 'pending','total_amount':100,'card_amount_used':100,'order_items':[],'campus_id':campus}
 elif path.endswith('/campuses'):data=[{'id':campus,'name':'Local Campus','is_active':True}]
 elif path.endswith('/messages') or path.endswith('/feature-flags') or path.endswith('/storefront/config/public'):data={}
 elif path.endswith('/delivery-window-status'):data={'is_open':True}
 route.fulfill(status=status,json=data)
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5210','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=(root/'guest-return-vite.log').open('w'),stderr=subprocess.STDOUT)
try:
 time.sleep(2)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox']);expect.set_options(timeout=15000)
  def open_page(path,receipt=False,legacy=False):
   ctx=browser.new_context(viewport={'width':390,'height':844});ctx.route('**/api/**',fixture)
   values={'hg_campus_id':campus,'hg_guest_cart':json.dumps([row,other])}
   if legacy:values['hg_guest_orders_old_tab']=json.dumps([{'id':oid,'claim_token':token}])
   records=[{'id':oid,'claim_token':token,'payment_status':'pending','cart_items':[row],'campus_id':campus}] if receipt else []
   ctx.add_init_script('for(const[k,v]of Object.entries('+json.dumps(values)+'))localStorage.setItem(k,v);sessionStorage.setItem("hg_guest_order_receipts",'+json.dumps(json.dumps(records))+');')
   page=ctx.new_page();page.goto('http://127.0.0.1:5210'+path);return ctx,page
  ctx,p=open_page('/order-confirmation/'+oid+'?payment_return=1',True);expect(p.get_by_role('heading',name='Order Confirmed!',exact=True)).to_be_visible();assert p.evaluate("JSON.parse(localStorage.getItem('hg_guest_cart')).map(x=>x.id)")==['new-cart-row'];checks['paid_return_recovers_tab_token_and_clears_only_submitted_rows']=True;ctx.close()
  ctx,p=open_page('/order-confirmation/'+oid+'?payment_return=1#claim_token='+token);expect(p.get_by_role('heading',name='Order Confirmed!',exact=True)).to_be_visible();assert p.evaluate("JSON.parse(sessionStorage.getItem('hg_guest_order_receipts'))[0].id")==oid;checks['fresh_context_callback_fragment_restores_specific_guest_proof']=True;ctx.close()
  state['paid']=False
  ctx,p=open_page('/order-confirmation/'+oid+'?payment_return=1',True);expect(p.get_by_role('heading',name='Order saved — payment required',exact=True)).to_be_visible();assert len(p.evaluate("JSON.parse(localStorage.getItem('hg_guest_cart'))"))==2
  state['verify_paid']=True;p.get_by_role('button',name='I have paid — check payment',exact=True).click();expect(p.get_by_role('heading',name='Order Confirmed!',exact=True)).to_be_visible();assert len(p.evaluate("JSON.parse(localStorage.getItem('hg_guest_cart'))"))==1;checks['pending_payment_retains_cart_then_verified_payment_settles_it']=True;ctx.close()
  before=len(calls);ctx,p=open_page('/order-confirmation/'+oid,False,True);expect(p.get_by_text('Order not found',exact=True)).to_be_visible();assert all(not good for _,good in calls[before:]);checks['another_tabs_local_storage_proof_is_not_discovered']=True;ctx.close()
  ctx,p=open_page('/track-orders?order_number=HG-RETURN&claim_token='+token);p.wait_for_url('**/orders/'+oid+'?claim_token=*');expect(p.get_by_text('Order not found',exact=True)).to_have_count(0);checks['email_link_auto_tracks_without_prior_device_history']=True;ctx.close()
  state['paid']=False;state['verify_paid']=True
  ctx,p=open_page('/checkout',True);p.wait_for_url('**/order-confirmation/'+oid);expect(p.get_by_role('heading',name='Order Confirmed!',exact=True)).to_be_visible();assert len(p.evaluate("JSON.parse(localStorage.getItem('hg_guest_cart'))"))==1;checks['checkout_left_open_recovers_bank_payment_without_callback']=True;ctx.close()
  browser.close()
 (root/'guest-return-results.json').write_text(json.dumps(checks,indent=2));print(json.dumps(checks,indent=2))
finally:os.killpg(proc.pid,signal.SIGTERM)
