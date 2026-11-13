"""Built checkout UI with controlled HTTP; never creates an order or payment."""
import json, os, re
from datetime import datetime, timezone
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect
BASE=os.environ.get('HG_BROWSER_BASE','http://127.0.0.1:4195')
C='11111111-1111-4111-8111-111111111111'; U='22222222-2222-4222-8222-222222222222'; G='33333333-3333-4333-8333-333333333333'
now=datetime.now(timezone.utc).isoformat()
item={'id':'cart-row','campus_id':C,'quantity':1,'menu_item_id':'meal','menu_items':{'id':'meal','name':'Fixture wings','price':500,'is_available':True}}
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']); expect.set_options(timeout=15000)
 for case in ('empty_mobile','available_mobile','gate_guest','saved_pin_desktop','free_side_retry'):
  member=case!='gate_guest'; available=case=='available_mobile'; free_error=[case=='free_side_retry']; quotes=[]; selection=[]
  ctx=browser.new_context(viewport={'width':1280 if case=='saved_pin_desktop' else 393,'height':900},geolocation={'latitude':7.3,'longitude':5.14},permissions=['geolocation'])
  values={'hg_campus_id':C,'hg_user_campus_id':C,'hg_guest_cart':json.dumps([item]),'hg_cookie_consent':json.dumps({'essential':True,'analytics':False,'date':now})}
  if member: values.update({'hg_access_token':'controlled','hg_user_role':'student'})
  ctx.add_init_script('for(const[k,v]of Object.entries('+json.dumps(values)+'))localStorage.setItem(k,v);')
  def api(route):
   path=urlparse(route.request.url).path; method=route.request.method; data=[]
   if path.endswith('/auth/me'):data={'id':U,'full_name':'Fixture student','role':'student','campus_id':C,'phone':'08012345678','is_active':True}
   elif path.endswith('/campuses'):data=[{'id':C,'name':'FUTA','is_active':True,'lat':7.3,'lon':5.14}]
   elif path.endswith('/cart'):data={'items':[item],'subtotal':500}
   elif path.endswith('/wallet'):data={'balance':1000,'hp_balance':0}
   elif path.endswith('/feature-flags'):data=[{'feature_name':'free_side_credits','is_active':True,'campus_id':None}]
   elif path.endswith('/free-sides'):
    if free_error[0]:route.fulfill(status=503,json={'error':'Controlled free side retry'});return
    data={'total_credits':1 if available else 0,'available_sides':[{'id':'fries','name':'Fries'}],'active_selections':selection}
   elif path.endswith('/free-sides/select'):
    selection.append({'id':'side-selection','free_side_item_id':'fries','free_side_items':{'id':'fries','name':'Fries'}});data={'id':'side-selection'}
   elif '/free-sides/deselect/' in path:selection.clear();data={}
   elif path.endswith('/auth/addresses'):data=[{'id':'home','label':'Saved home','line1':'House 12','delivery_type':'off_campus','delivery_location_id':G,'latitude':7.3,'longitude':5.14}]
   elif path.endswith('/delivery/gates'):data=[{'id':G,'name':'West Gate','base_fee':500,'is_active':True}]
   elif path.endswith('/delivery/hostels'):data=[{'id':'hostel','name':'Fixture hostel','delivery_fee':300}]
   elif path.endswith('/delivery/calculate-fee'):data={'delivery_fee':500,'fee':500,'gate':{'id':G,'name':'West Gate'}}
   elif path.endswith('/orders/quote'):
    quotes.append(route.request.post_data_json)
    data={'subtotal':500,'delivery_fee':500,'total_amount':1000,'available_hp_rewards':[{'id':'hp-one','name':'Double food HP','multiplier':2}] if available else [],'available_delivery_rewards':[{'id':'delivery-one','name':'Delivery treat','discount':200}] if available else []}
   elif path.endswith('/notifications'):data={'notifications':[],'unread_count':0}
   elif 'window-status' in path or 'capacity' in path:data={'is_open':True,'remaining':50}
   elif method!='GET':
    assert not path.endswith('/orders') and '/payment' not in path, 'Unexpected money/order mutation '+path
    data={}
   route.fulfill(json=data)
  ctx.route('**/api/**',api); page=ctx.new_page();page.set_default_timeout(15000)
  page.goto(BASE+'/checkout',wait_until='domcontentloaded')
  if case=='gate_guest':
   page.get_by_role('button',name=re.compile('Off Campus')).click()
   page.get_by_role('button',name=re.compile('^West Gate')).click()
   dialog=page.get_by_role('dialog');expect(dialog.get_by_role('heading',name='Pick up at West Gate')).to_be_visible()
   expect(dialog.get_by_text(re.compile('they will not deliver to your home or lodge'))).to_be_visible()
   dialog.get_by_role('button',name=re.compile('Got it')).click()
   expect(page.get_by_text('Gate pickup · West Gate',exact=True)).to_be_visible()
   page.get_by_role('button',name='Use my location',exact=True).click()
   expect(page.get_by_text(re.compile('Home delivery to your selected pin'))).to_be_visible()
   expect(page.get_by_text('Gate pickup · West Gate',exact=True)).to_have_count(0)
  else:
   perks=page.get_by_role('region',name='Available rewards')
   expect(perks.get_by_role('button',name=re.compile('Free sides'))).to_be_visible()
   if case=='free_side_retry':
    perks.get_by_role('button',name=re.compile('Free sides')).click()
    dialog=page.get_by_role('dialog');expect(dialog.get_by_role('alert')).to_contain_text('Controlled free side retry')
    free_error[0]=False;dialog.get_by_role('button',name='Retry',exact=True).click()
    expect(dialog.get_by_text(re.compile('No free side credits yet'))).to_be_visible();dialog.get_by_role('button',name='Done',exact=True).click()
   elif available:
    perks.get_by_role('button',name=re.compile('Free sides')).click()
    page.get_by_role('button',name=re.compile('Add free side')).click()
    expect(perks.get_by_text('1 added ✓',exact=True)).to_be_visible()
   else:
    perks.get_by_role('button',name=re.compile('Free sides')).click()
    dialog=page.get_by_role('dialog');expect(dialog.get_by_text(re.compile('No free side credits yet'))).to_be_visible();dialog.get_by_role('button',name='Done',exact=True).click()
   page.get_by_role('button',name=re.compile('Saved home')).click()
   expect(page.get_by_text(re.compile('Home delivery to your selected pin'))).to_be_visible()
   expect(page.get_by_role('dialog')).to_have_count(0)
   expect(perks.get_by_role('button',name=re.compile('Delivery rewards'))).to_contain_text('1 available' if available else '0 available')
   for label, select, option in [('Delivery rewards','Delivery reward','delivery-one'),('Food HP','Food HP reward','hp-one')]:
    perks.get_by_role('button',name=re.compile(label)).click();dialog=page.get_by_role('dialog')
    if available:dialog.get_by_role('combobox',name=select,exact=True).select_option(option)
    else:expect(dialog.get_by_text(re.compile('No eligible'))).to_be_visible()
    dialog.get_by_role('button',name='Done',exact=True).click()
   if available:
    expect(perks.get_by_role('button',name=re.compile('Food HP'))).to_contain_text('Selected ✓')
    page.wait_for_timeout(700)
    assert any(q.get('hp_reward_id')=='hp-one' and q.get('delivery_reward_id')=='delivery-one' for q in quotes), quotes
   expect(perks.get_by_role('button',name=re.compile('Free sides'))).to_be_visible()
   boxes=perks.get_by_role('button').evaluate_all('(buttons)=>buttons.map(b=>b.getBoundingClientRect().top)')
   assert len(set(boxes))==1,boxes
   if case=='empty_mobile':page.screenshot(path='/workspace/Holy-Grills-/work/checkout-perks-mobile.png',full_page=True)
  if case=='saved_pin_desktop':
   page.get_by_role('button',name='Use gate pickup instead',exact=True).click()
   expect(page.get_by_role('dialog').get_by_role('heading',name='Pick up at West Gate')).to_be_visible()
   page.get_by_role('dialog').get_by_role('button',name='Choose home delivery instead',exact=True).click()
   expect(page.get_by_text('Gate pickup · West Gate',exact=True)).to_have_count(0)
  assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),'Horizontal overflow'
  print('PASS',case,flush=True);ctx.close()
 browser.close()
