"""Native ambassador controls and meal checkout, using controlled transport only."""
import json, os, re
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('HG_BROWSER_BASE','http://127.0.0.1:4185')
C='70000001-cafe-cafe-cafe-000000000001';U='11111111-1111-4111-8111-111111111111';D='22222222-2222-4222-8222-222222222222';M='33333333-3333-4333-8333-333333333333';H='44444444-4444-4444-8444-444444444444'
reports=[]
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for case,role in [('benefit','student'),('checkout','student'),('promo','community_manager'),('review','community_manager'),('grant','admin')]:
  ctx=browser.new_context(viewport={'width':393,'height':852},is_mobile=True)
  ctx.add_init_script(f"localStorage.setItem('hg_access_token','synthetic');localStorage.setItem('hg_campus_id','{C}');localStorage.setItem('hg_user_campus_id','{C}');localStorage.setItem('hg_user_role','{role}');")
  calls=[];writes=[];quotes=[];errors=[];discount_reads=0;reviews={};held=[];hold_recommend=False
  def review(month):return reviews.setdefault(month,{'ambassador_id':U,'month':month,'recommendation':'none','decision':'pending','assigned_count':1,'seen_count':0,'shared_count':0,'completion_rate':0,'signups_count':0,'orders_count':0,'milestones':[]})
  def api(route):
   global discount_reads
   req=route.request;path=urlparse(req.url).path;calls.append(path);data={}
   if path.endswith('/auth/me'):data={'id':U,'full_name':'Synthetic Student','role':role,'campus_id':C,'phone':'08012345678','profile':{'phone':'08012345678'},'hp_earned_120day':100,'active':100}
   elif path.endswith('/campuses'):data={'campuses':[{'id':C,'name':'FUTA','slug':'futa','is_active':True}]}
   elif path.endswith('/ambassadors/meal-discounts'):
    discount_reads+=1
    if discount_reads==1:route.fulfill(status=503,json={'error':'Controlled temporary failure'});return
    data={'discounts':[{'id':D,'status':'active','code':'AUDIT-MEAL','max_meal_value':3000,'uses_remaining':1,'uses_total':1,'expires_at':'2099-01-01T00:00:00Z'}]}
   elif path.endswith('/orders/quote'):
    body=req.post_data_json;quotes.append(body);amount=3000 if body.get('meal_discount_id')==D else 0
    data={'subtotal':4500,'delivery_fee':500,'delivery_fee_original':500,'total_amount':5000-amount,'discount_amount':amount,'meal_discount':{'amount':amount,'code':'AUDIT-MEAL'},'available_delivery_rewards':[],'available_hp_rewards':[],'hp_preview':{'total_hp':0}}
   elif path.endswith('/orders') and req.method=='POST':writes.append(req.post_data_json);route.fulfill(status=400,json={'error':'Stopped before any real order'});return
   elif path.endswith('/cart'):data={'items':[{'id':'cart-row','menu_item_id':M,'quantity':1,'menu_items':{'id':M,'name':'Fixture meal','price':4500,'is_available':True}}] if case=='checkout' else []}
   elif path.endswith('/delivery/hostels'):data={'hostels':[{'id':H,'name':'Fixture hostel','delivery_fee':500,'campus_id':C}]}
   elif path.endswith('/delivery/gates'):data={'gates':[]}
   elif path.endswith('/delivery/calculate-fee'):data={'delivery_fee':500}
   elif 'delivery-window-status' in path:data={'is_open':True}
   elif path.endswith('/auth/addresses'):data=[]
   elif path.endswith('/ambassadors/staff/ambassadors'):data={'ambassadors':[{'ambassador':{'profile_id':U,'campus_id':C},'profile':{'full_name':'Fixture ambassador'}}]}
   elif path.endswith('/ambassadors/staff/promo-messages'):
    if req.method=='POST':
     writes.append(req.post_data_json)
     if len(writes)==1:route.fulfill(status=503,json={'error':'Controlled response loss'});return
     data={'message':{'id':D},'recipient_count':1,'idempotent':True}
    else:data={'messages':[]}
   elif '/recommendation' in path:
    if hold_recommend:held.append(route);return
    body=req.post_data_json;writes.append(body);r=review(body['month']);r.update(recommendation=body['recommendation'],recommendation_note=body['note']);data={'review':r}
   elif path.endswith('/decision'):
    body=req.post_data_json;writes.append(body);r=review(body['month']);r.update(decision=body['decision']);data={'review':r}
   elif path.endswith('/ambassadors/staff/reviews'):
    month=parse_qs(urlparse(req.url).query).get('month',['2026-11'])[0];data={'reviews':[review(month)]}
   elif path.endswith('/ambassadors/staff/grants'):
    if req.method=='POST':
     writes.append(req.post_data_json)
     grant_writes=[w for w in writes if 'reward_type' in w]
     if len(grant_writes)==1:route.fulfill(status=503,json={'error':'Controlled grant response loss'});return
     data={'grant':{'id':D,'idempotent':True}}
    else:data={'grants':[]}
   elif path.endswith('/challenges/my'):data={'badges':[],'challenges_available':[],'challenges_completed':[]}
   elif '/notifications' in path:data={'notifications':[]}
   elif any(x in path for x in ('tiers','saved','global-addons','feature-flags','orders','free-sides','redemptions')):data=[]
   route.fulfill(status=200,json=data)
  ctx.route('**/api/**',api);ctx.route('https://*.onesignal.com/**',lambda r:r.abort())
  page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
  target='/rewards' if case=='benefit' else '/checkout' if case=='checkout' else '/community-manager?section=ambassadorpromo' if case=='promo' else ('/admin' if role=='admin' else '/community-manager')+'?section=ambassadorreviews'
  page.goto(BASE+target,wait_until='domcontentloaded')
  if page.get_by_role('button',name='Essential only').count():page.get_by_role('button',name='Essential only').click()
  if case=='benefit':
   expect(page.get_by_text('Your meal discounts could not be loaded.')).to_be_visible(timeout=15000)
   page.get_by_text('Your meal discounts could not be loaded.').get_by_role('button',name='Retry').click()
   expect(page.get_by_text('AUDIT-MEAL · ₦3,000',exact=True)).to_be_visible()
   expect(page.get_by_role('link',name='Choose a meal',exact=True)).to_have_attribute('href','/menu')
   expect(page.get_by_text('Choose any eligible meal. Pay the amount above your discount plus delivery at checkout.')).to_be_visible()
  elif case=='checkout':
   expect(page.get_by_text('Your meal discounts could not be loaded.')).to_be_visible(timeout=15000)
   page.get_by_text('Your meal discounts could not be loaded.').get_by_role('button',name='Retry').click()
   page.get_by_role('radio',name=re.compile('AUDIT-MEAL')).check()
   page.get_by_role('button',name=re.compile('On Campus')).click()
   page.get_by_role('button',name=re.compile('Fixture hostel')).click()
   submit=page.get_by_role('button',name='Place Order · ₦2,000',exact=True)
   expect(submit).to_be_enabled(timeout=15000)
   assert quotes[-1]['meal_discount_id']==D
   submit.click();dialog=page.get_by_role('dialog');dialog.get_by_role('button',name='Confirm number and continue').click()
   expect(page.get_by_text('Stopped before any real order')).to_be_visible()
   assert len(writes)==1 and writes[0]['meal_discount_id']==D and writes[0]['items'][0]['menu_item_id']==M
  elif case=='promo':
   page.get_by_role('button',name='New promotional message',exact=True).click();dialog=page.get_by_role('dialog')
   dialog.get_by_label(re.compile('Caption')).fill('Share {{link}}')
   dialog.get_by_role('button',name='Generate personalized messages',exact=True).click()
   expect(page.get_by_text('Controlled response loss')).to_be_visible()
   dialog.get_by_role('button',name='Generate personalized messages',exact=True).click()
   expect(dialog).not_to_be_visible()
   assert len(writes)==2 and writes[0]['request_id']==writes[1]['request_id']
  else:
   page.get_by_role('button',name=re.compile(U[:8])).first.click()
   if role=='community_manager':
    assert page.get_by_role('button',name='Issue reward',exact=True).count()==0
    page.once('dialog',lambda d:d.dismiss());page.get_by_role('button',name='Recommend benefit',exact=True).click();assert not writes
    page.once('dialog',lambda d:d.accept('Good progress'));page.get_by_role('button',name='Recommend benefit',exact=True).click()
    expect(page.get_by_text('Good progress',exact=False)).to_be_visible()
    assert len(writes)==1 and writes[0]['recommendation']=='recommend'
   else:
    page.once('dialog',lambda d:d.accept('Approved review'));page.get_by_role('button',name='Approve review',exact=True).click()
    assert len(writes)==1 and 'reward_type' not in writes[0]
    page.get_by_role('button',name='Issue reward',exact=True).click();dialog=page.get_by_role('dialog')
    dialog.get_by_label('Reason',exact=True).fill('Programme reward')
    uses=dialog.get_by_label('Number of uses',exact=True);uses.fill('0')
    dialog.get_by_role('button',name='Issue reward',exact=True).click();assert len(writes)==1
    uses.fill('2');dialog.get_by_role('button',name='Issue reward',exact=True).click()
    expect(page.get_by_text('Controlled grant response loss')).to_be_visible()
    dialog.get_by_role('button',name='Issue reward',exact=True).click();expect(dialog).not_to_be_visible()
    assert len(writes)==3 and writes[-1]==writes[-2] and writes[-1]['uses_count']==2
  assert not errors,(case,errors)
  reports.append({'case':case,'role':role,'passed':True,'production_writes':0});print(json.dumps(reports[-1]),flush=True);ctx.close()
 browser.close()
print(json.dumps(reports))
