"""Native customer and staff controls, controlled HTTP only; no real orders."""
import os,json
from datetime import datetime,timezone
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('HG_BROWSER_BASE','http://127.0.0.1:4195')
C='11111111-1111-4111-8111-111111111111';U='22222222-2222-4222-8222-222222222222';B='33333333-3333-4333-8333-333333333333';D='44444444-4444-4444-8444-444444444444';R='55555555-5555-4555-8555-555555555555'
now=datetime.now(timezone.utc).isoformat()
item={'id':'cart-row','campus_id':C,'guest_campus_id':C,'quantity':1,'menu_item_id':'menu-one','menu_items':{'id':'menu-one','name':'Fixture wings','price':500,'is_available':True}}
payload={'idempotency_key':'checkout-original','guest_email':'guest@example.invalid','guest_phone':'08012345678','items':[{'menu_item_id':'menu-one','quantity':1}],'payment_method':'card'}
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);expect.set_options(timeout=12000)
 for case in ('guest_closed','member_closed','release_failed','already_paid','rider_zones','kitchen_bulk','admin_address'):
  role='rider' if case=='rider_zones' else 'kitchen' if case=='kitchen_bulk' else 'admin' if case=='admin_address' else 'student' if case=='member_closed' else None
  ctx=browser.new_context(viewport={'width':393,'height':960});calls=[];failed=[True]
  orders=[{'id':B,'customer_name':'North customer','guest_name':'North customer','status':'assigned','payment_status':'paid','delivery_type':'off_campus','total_amount':500,'created_at':now,'received_at':now,'delivery_address_snapshot':{'line1':'House 12 near North Gate','landmark':'Blue roof','location_name':'North Gate','latitude':7.303,'longitude':5.14},'delivery_address':{'line1':'House 12 near North Gate','landmark':'Blue roof'},'delivery_location_lat':7.303,'delivery_location_lon':5.14,'order_items':[{'name_snapshot':'Wings','name':'Wings','quantity':1}],'items':[{'name':'Wings','quantity':1}]},
          {'id':D,'customer_name':'West customer','guest_name':'West customer','status':'assigned','payment_status':'paid','delivery_type':'off_campus','total_amount':500,'created_at':now,'received_at':now,'delivery_address_snapshot':{'line1':'House 4 West Gate','landmark':'Green door'},'delivery_address':{'line1':'House 4 West Gate','landmark':'Green door'},'items':[{'name':'Skewer','quantity':1}],'order_items':[{'name_snapshot':'Skewer','quantity':1}]}]
  batches=[{'id':'n-'+B,'zone':'North Gate','status':'assigned' if role=='rider' else 'open','rider_id':R if role=='rider' else None,'orders':[orders[0]],'delivery_date':now[:10]}, {'id':'w-'+D,'zone':'West Gate','status':'assigned' if role=='rider' else 'open','rider_id':R if role=='rider' else None,'orders':[orders[1]],'delivery_date':now[:10]}]
  values={'hg_campus_id':C,'hg_user_campus_id':C,'hg_admin_campus_id':C,'hg_guest_cart':json.dumps([item]),'hg_cookie_consent':json.dumps({'essential':True,'analytics':False,'date':now})}
  if role:values.update({'hg_access_token':'controlled','hg_user_role':role})
  if case in ('guest_closed','member_closed','release_failed','already_paid'):
   values[f'hg_pending_checkout:{U if role else "guest"}:{C}']=json.dumps({'payload':payload,'order_id':B,'created_at':now})
  ctx.add_init_script('for(const[k,v]of Object.entries('+json.dumps(values)+'))localStorage.setItem(k,v);')
  def api(route):
   request=route.request;path=urlparse(request.url).path;data=[]
   if path.endswith('/orders/checkout/abandon'):
    calls.append(('abandon',request.post_data_json))
    if case=='release_failed':route.fulfill(status=503,json={'error':'Retry closing this checkout'});return
    data={'state':'paid','order':{'id':B,'payment_status':'paid','claim_token':'controlled-proof'}} if case=='already_paid' else {'state':'closed','order_id':B}
   elif path.endswith('/orders/'+B):data={**orders[0],'user_id':U if role else None,'payment_status':'paid','campus_id':C,'order_items':[]}
   elif path.endswith('/riders/my-batch'):data={'batch':batches[0],'orders':orders[:1],'batches':batches}
   elif path.endswith('/riders/orders/'+D+'/pickup'):
    calls.append(('pickup',D));orders[1]['status']='out_for_delivery';data={'status':'out_for_delivery'}
   elif path.endswith('/riders/earnings'):data={'total_earnings':0,'batches':[]}
   elif path.endswith('/riders/stats'):data={'is_available':False}
   elif path.endswith('/kitchen/handoff'):data={'batches':batches,'riders':[{'id':R,'full_name':'Fixture rider'}]}
   elif '/kitchen/handoff/' in path and path.endswith('/assign'):
    calls.append(('assign',path.split('/')[-2]));assert request.post_data_json=={'rider_id':R}
    if path.split('/')[-2]==batches[1]['id'] and failed[0]:failed[0]=False;route.fulfill(status=409,json={'error':'Controlled retry'});return
    for batch in batches:
     if batch['id']==path.split('/')[-2]:batch.update(status='assigned',rider_id=R)
    data={'status':'assigned'}
   elif path.endswith('/kitchen/queue'):data=[{**order,'status':'ready'} for order in orders]
   elif path.endswith('/admin/orders'):data={'orders':orders}
   elif path.endswith('/auth/me'):data={'id':U,'full_name':'Fixture student','role':role,'campus_id':C,'phone':'08012345678','is_active':True}
   elif path.endswith('/campuses'):data=[{'id':C,'name':'Fixture campus','is_active':True}]
   elif path.endswith('/cart'):data={'items':[item],'subtotal':500}
   elif path.endswith('/wallet'):data={'cash_balance':1000,'hp_balance':0}
   elif path.endswith('/kitchen/settings'):data={}
   elif 'window-status' in path or 'capacity' in path:data={'is_open':True,'remaining':50}
   elif request.method!='GET':
    assert not path.endswith('/orders') and '/payment' not in path,'Unexpected order/payment mutation: '+path
    data={}
   route.fulfill(status=200,json=data)
  ctx.route('**/api/**',api);page=ctx.new_page();page.set_default_timeout(12000)
  path='/rider' if role=='rider' else '/kitchen' if role=='kitchen' else '/admin?section=orders' if role=='admin' else '/checkout'
  page.goto(BASE+path,wait_until='domcontentloaded')
  if case in ('guest_closed','member_closed','release_failed','already_paid'):
   button=page.get_by_role('button',name='Start a new checkout',exact=True);expect(button).to_be_visible();button.click()
   if case=='release_failed':
    expect(page.get_by_text('Retry closing this checkout',exact=True)).to_be_visible();expect(button).to_be_visible()
    assert page.evaluate(f"localStorage.getItem('hg_pending_checkout:guest:{C}')")
   elif case=='already_paid':
    page.wait_for_url('**/order-confirmation/'+B)
    assert page.evaluate(f"localStorage.getItem('hg_pending_checkout:guest:{C}')")==None
   else:
    expect(button).to_have_count(0)
    assert page.evaluate(f"localStorage.getItem('hg_pending_checkout:{U if role else 'guest'}:{C}')")==None
    assert page.evaluate(f"localStorage.getItem('hg_pending_checkout:{U if role else 'guest'}:{C}:attempt')")
    if not role:assert len(page.evaluate("JSON.parse(localStorage.getItem('hg_guest_cart'))"))==1
   assert len([call for call in calls if call[0]=='abandon'])==1
  elif case=='rider_zones':
   expect(page.get_by_text('North customer',exact=True)).to_be_visible();expect(page.get_by_text('West customer',exact=True)).to_be_visible()
   expect(page.get_by_text('House 4 West Gate, Green door',exact=True)).to_be_visible()
   west=page.get_by_role('region',name='Delivery zone West Gate');west.get_by_role('button',name='Collect batch · start deliveries',exact=True).click()
   expect(west.get_by_role('button',name='Collect batch · start deliveries',exact=True)).to_have_count(0)
   expect(page.get_by_role('region',name='Delivery zone North Gate').get_by_role('button',name='Collect batch · start deliveries',exact=True)).to_be_visible()
   assert calls==[('pickup',D)]
  elif case=='kitchen_bulk':
   expect(page.get_by_text('North Gate · House 12 near North Gate · Blue roof',exact=True)).to_be_visible()
   page.get_by_role('button',name='Handoff',exact=True).click()
   page.get_by_label('Select all batches',exact=True).check();page.get_by_label('Rider for selected batches',exact=True).select_option(R)
   page.get_by_role('button',name='Assign 2 selected batches',exact=True).click()
   expect(page.get_by_text('1 batch assigned · 1 could not be assigned. Review and retry those selected batches.',exact=True)).to_be_visible()
   page.get_by_role('button',name='Assign 1 selected batch',exact=True).click()
   expect(page.get_by_text('1 batch assigned.',exact=True)).to_be_visible()
   assert calls==[('assign',batches[0]['id']),('assign',batches[1]['id']),('assign',batches[1]['id'])]
   expect(page.get_by_role('link',name='View delivery pin on Google Maps',exact=True)).to_have_attribute('href','https://www.google.com/maps/search/?api=1&query=7.303%2C5.14')
  else:
   expect(page.get_by_text('North Gate · House 12 near North Gate · Blue roof',exact=True)).to_be_visible()
   expect(page.get_by_role('link',name='View delivery pin on Google Maps',exact=True)).to_be_visible()
  assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),'Horizontal overflow'
  print('PASS',case,flush=True);ctx.close()
 browser.close()
