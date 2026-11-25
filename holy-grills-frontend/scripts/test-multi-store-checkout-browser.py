"""Native pickup controls with controlled transport; no real orders/payment or messages."""
import json, os, re
from datetime import datetime, timezone
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect
BASE=os.environ.get('HG_BROWSER_BASE','http://127.0.0.1:4185')
C='11111111-1111-4111-8111-111111111111';U='22222222-2222-4222-8222-222222222222';O='33333333-3333-4333-8333-333333333333'
now=datetime.now(timezone.utc).isoformat();location={'name':'Campus store','address':'12 Campus road','instructions':'Bring your order number'}
S='44444444-4444-4444-8444-444444444444';S2='55555555-5555-4555-8555-555555555555'
stores=[{'id':S,'campus_id':C,'name':'West counter','address':'West road','instructions':'West collection'}, {'id':S2,'campus_id':C,**location}]
item={'id':'cart-row','campus_id':C,'guest_campus_id':C,'quantity':1,'menu_item_id':'meal','menu_items':{'id':'meal','name':'Fixture wings','price':500,'is_available':True}}
with sync_playwright() as pw:
 browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);expect.set_options(timeout=15000)
 for case,width in [('member',393),('guest',1280)]:
  role='admin' if case=='admin' else 'kitchen' if case=='kitchen' else None if case=='guest' else 'student'
  ctx=browser.new_context(viewport={'width':width,'height':1000});calls=[];quotes=[];errors=[];state={'store_retry':case=='member','status':'received','fail_save':True,'saved':False,'created':False}
  values={'hg_campus_id':C,'hg_user_campus_id':C,'hg_admin_campus_id':C,'hg_guest_cart':json.dumps([item]),'hg_cookie_consent':json.dumps({'essential':True,'analytics':False,'date':now})}
  if role:values.update(hg_access_token='controlled',hg_user_role=role)
  ctx.add_init_script('for(const[k,v]of Object.entries('+json.dumps(values)+'))localStorage.setItem(k,v);')
  def order():return {'id':O,'user_id':U,'order_number':'HG-PICKUP','campus_id':C,'status':state['status'],'payment_status':'paid','delivery_type':'store_pickup','delivery_fee':0,'total_amount':500,'created_at':now,'received_at':now,'delivery_address_snapshot':{'line1':location['address'],'location_name':location['name'],'instructions':location['instructions']},'items':[{'name':'Fixture wings','quantity':1}],'order_items':[{'name_snapshot':'Fixture wings','quantity':1}]}
  def api(route):
   req=route.request;path=urlparse(req.url).path;method=req.method;data=[]
   if path.endswith('/auth/me'):data={'id':U,'full_name':'Fixture person','role':role,'campus_id':C,'phone':'08012345678','is_active':True}
   elif path.endswith('/campuses'):data=[{'id':C,'name':'FUTA','is_active':True}]
   elif path.endswith('/feature-flags'):data=[{'feature_name':'store_pickup','is_active':True,'campus_id':None},{'feature_name':'multi_store_ordering','is_active':True,'campus_id':None}]
   elif path.endswith('/delivery/stores'):
    if state['store_retry']:state['store_retry']=False;route.fulfill(status=503,json={'error':'Controlled store options retry'});return
    data={'enabled':True,'stores':stores,'suggested_store_id':None}
   elif path.endswith('/delivery/store-pickup'):
    calls.append(('capability',None));data={'enabled':True,**location,'fee':0,'requires_store_selection':True} if 'store_id=' not in req.url else {'enabled':True,**(stores[1] if S2 in req.url else stores[0]),'fee':0}
   elif path.endswith('/delivery/admin/store-pickup'):
    if method=='PATCH':
     calls.append(('config',req.post_data_json))
     if state['fail_save']:state['fail_save']=False;route.fulfill(status=503,json={'error':'Controlled save retry'});return
     state['saved']=True;data={'value':req.post_data_json['location'],'updated_at':'2026-11-22T10:01:00+00:00'}
    else:data={'location':location,'updated_at':'2026-11-22T10:00:00+00:00','enabled':False}
   elif path.endswith('/cart'):data={'items':[] if state['created'] else [item],'subtotal':500}
   elif path.endswith('/wallet'):data={'balance':1000,'hp_balance':0}
   elif path.endswith('/orders/reward-options'):data={'hp':[],'delivery':[]}
   elif path.endswith('/orders/quote'):
    quotes.append(req.post_data_json);data={'subtotal':500,'delivery_fee':0,'total_amount':500,'available_hp_rewards':[],'available_delivery_rewards':[],'hp_preview':{'total_hp':50}}
   elif path.endswith('/orders') and method=='POST':
    body=req.post_data_json;calls.append(('order',body));assert body['delivery_type']=='store_pickup' and body['store_id']==S2;assert not body.get('delivery_location_id') and not body.get('delivery_location_lat') and not body.get('delivery_address_id')
    state['created']=True;data={**order(),'user_id':U if role else None,'payment_status':'paid' if role else 'pending','card_amount_used':0 if role else 500,'claim_token':None if role else 'controlled-claim'}
   elif path.endswith('/payments/initialize') or path.endswith('/orders/'+O+'/payment'):
    calls.append(('payment',req.post_data_json));data={'authorization_url':'https://checkout.paystack.com/controlled-pickup'}
   elif '/orders/'+O+'/status' in path:
    calls.append(('status',req.post_data_json));state['status']=req.post_data_json['status'];data=order()
   elif path.endswith('/orders/'+O):data={**order(),'status':'delivered' if case=='track' else state['status']}
   elif path.endswith('/kitchen/queue'):data=[] if state['status']=='delivered' else [order()]
   elif path.endswith('/kitchen/scheduled'):data={'count':0,'scheduled_orders':[]}
   elif path.endswith('/kitchen/handoff'):data={'batches':[],'riders':[]}
   elif path.endswith('/kitchen/settings'):data={}
   elif path.endswith('/notifications'):data={'notifications':[],'unread_count':0}
   elif 'window-status' in path or 'capacity' in path:data={'is_open':True,'remaining':50}
   elif method!='GET':data={}
   route.fulfill(status=200,json=data)
  ctx.route('**/api/**',api);ctx.route('https://checkout.paystack.com/**',lambda route:route.fulfill(status=200,body='Controlled payment gateway'))
  page=ctx.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
  page.goto(BASE+('/admin?section=delivery' if case=='admin' else '/kitchen' if case=='kitchen' else '/orders/'+O if case=='track' else '/checkout'),wait_until='domcontentloaded')
  if case=='off':
   expect(page.get_by_role('heading',name='Checkout',exact=True)).to_be_visible();expect(page.get_by_role('button',name=re.compile('^Store pickup'))).to_have_count(0);assert not calls
  elif case=='admin':
   page.get_by_role('button',name='Store pickup',exact=True).click();form=page.locator('form').filter(has=page.get_by_role('heading',name='Store pickup point',exact=True));fields=form.get_by_role('textbox')
   expect(fields.nth(0)).to_have_value(location['name']);fields.nth(2).fill('Use the collection counter');form.get_by_role('button',name='Save pickup point',exact=True).click()
   expect(form.get_by_role('alert')).to_contain_text('Controlled save retry');expect(fields.nth(2)).to_have_value('Use the collection counter')
   form.get_by_role('button',name='Save pickup point',exact=True).click();expect(page.get_by_text('Pickup point saved',exact=True)).to_be_visible();assert state['saved'];assert len(calls)==2;assert calls[0][1]==calls[1][1]
  elif case=='kitchen':
   page.get_by_role('button',name='Start Preparing',exact=True).click();page.get_by_role('button',name='Mark Ready',exact=True).click();collect=page.get_by_role('button',name='Confirm collection',exact=True);collect.click();page.get_by_role('dialog').get_by_role('button',name='Go back',exact=True).click();assert state['status']=='ready'
   collect.click();page.get_by_role('dialog').get_by_role('button',name='Confirm',exact=True).click();expect(collect).to_have_count(0);assert [body['status'] for kind,body in calls if kind=='status']==['preparing','ready','delivered']
  elif case=='track':
   expect(page.get_by_text('Collected',exact=True)).to_have_count(2);expect(page.get_by_text('Assigned',exact=True)).to_have_count(0);expect(page.get_by_role('link',name='View pickup location on Maps',exact=True)).to_have_attribute('href',re.compile('12%20Campus%20road'))
  else:
   page.get_by_role('button',name=re.compile('^Store pickup')).click()
   if case=='member':page.get_by_role('alert').filter(has_text='Controlled store options retry').get_by_role('button',name='Retry',exact=True).click()
   select=page.get_by_label('Fulfilling store',exact=True);expect(select).to_have_value('');select.select_option(S);expect(page.get_by_text('West road',exact=True).first).to_be_visible();select.select_option(S2)
   expect(page.get_by_text(location['address'],exact=True).first).to_be_visible();expect(page.get_by_role('link',name='View pickup location on Maps',exact=True)).to_be_visible()
   if case=='guest':
    page.get_by_placeholder('Full name').fill('Fixture guest');page.get_by_placeholder(re.compile(r'Email \(for order confirmation\)')).fill('fixture@example.invalid');page.get_by_placeholder('08012345678').fill('08012345678')
   page.get_by_role('button',name=re.compile('^Place Order')).click();page.get_by_role('button',name='Confirm number and continue',exact=True).click()
   if case=='member':page.wait_for_url('**/order-confirmation/'+O)
   else:page.wait_for_url('https://checkout.paystack.com/**')
   assert len([x for x in calls if x[0]=='order'])==1;assert quotes and quotes[-1]['delivery_type']=='store_pickup' and quotes[-1]['store_id']==S2
  assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),case
  assert not errors,(case,errors);page.screenshot(path='/workspace/work/multi-store/checkout-'+case+'.png',full_page=True);ctx.close();print(json.dumps({'case':case,'width':width,'passed':True}),flush=True)
 browser.close()
