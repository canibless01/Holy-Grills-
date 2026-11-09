"""Mock HTTP only. Native confirmation, recovery and receipt ownership UX."""
import os,json,uuid
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('HG_BROWSER_BASE','http://127.0.0.1:4191')
U='11111111-1111-4111-8111-111111111111';R='22222222-2222-4222-8222-222222222222';C='70000001-cafe-cafe-cafe-000000000001'
expect.set_options(timeout=15000)
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for case in ('normal_mobile','normal_desktop','uncertain_retry','uncertain_reload','denied','flag_off_receipt'):
  ctx=browser.new_context(viewport={'width':1280 if case=='normal_desktop' else 393,'height':900})
  ctx.add_init_script(f"localStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_role','student');localStorage.setItem('hg_campus_id','{C}');localStorage.setItem('hg_user_campus_id','{C}');")
  ctx.add_init_script("localStorage.setItem('hg_cookie_consent',JSON.stringify({essential:true,analytics:false,date:new Date().toISOString()}));")
  calls=[];posts=[];done=[None];balance=[1000];ref=str(uuid.uuid4())
  def receipt_value(id):return {'id':id,'amount':250.25,'fee':0,'sender_id':U,'recipient_id':R,'sender_name':'Alice','recipient_name':'Bob','direction':'sent','balance_after':749.75,'note':'Dinner together','created_at':'2026-11-09T12:00:00Z','status':'completed'}
  def api(route):
   path=urlparse(route.request.url).path;method=route.request.method;calls.append((method,path));data={}
   if path.endswith('/auth/me'):data={'id':U,'role':'student','campus_id':C,'full_name':'Alice'}
   elif path.endswith('/campuses'):data={'campuses':[{'id':C,'name':'FUTA','is_active':True}]}
   elif path.endswith('/wallet/transfers/recipient'):data={'recipient':{'id':R,'name':'Bob','code':'BOB123'}}
   elif path.endswith('/wallet/transfers'):
    if method=='GET':data={'enabled':True,'minimum_amount':1,'maximum_amount':1000000,'daily_remaining':1000000,'available_balance':balance[0],'fee':0,'same_campus_only':True,'my_code':'ALICE123'}
    else:
     body=route.request.post_data_json;posts.append(body)
     assert body['recipient_id']==R and body['recipient_code']=='BOB123' and body['amount']==250.25
     assert 'sender_id' not in body
     if case=='denied':route.fulfill(status=400,json={'code':'insufficient_wallet_balance','error':'Insufficient wallet balance.'});return
     if case=='uncertain_retry' and len(posts)==1:route.fulfill(status=503,json={'code':'transfer_uncertain','error':'Transfer result unknown.'});return
     done[0]=receipt_value(body['request_id']);balance[0]=749.75
     if case=='uncertain_reload' and len(posts)==1:route.fulfill(status=503,json={'code':'transfer_uncertain','error':'Transfer result unknown.'});return
     data={'transfer':done[0]}
   elif '/wallet/transfers/' in path:
    if case=='flag_off_receipt':route.fulfill(status=404,json={'code':'transfer_not_found','error':'This transfer was not found for your account.'});return
    if not done[0]:route.fulfill(status=404,json={'code':'transfer_not_found','error':'Not found.'});return
    data={'transfer':done[0]}
   elif path.endswith('/wallet'):data={'balance':balance[0]}
   elif path.endswith('/wallet/transactions'):
    data={'transactions':[] if not done[0] else [{'id':'ledger','type':'debit','amount':250.25,'balance_after':749.75,'reason':'Sent to Bob','reference_type':'wallet_transfer','reference_id':done[0]['id'],'created_at':'2026-11-09T12:00:00Z'}]}
   elif path.endswith('/hp/balance'):data={'active':0,'pending':0}
   elif 'feature-flags' in path:data=[{'feature_name':'wallet_transfer','is_active':case!='flag_off_receipt'}]
   elif '/notifications' in path:data={'notifications':[]}
   elif 'cart' in path:data={'items':[]}
   elif any(x in path for x in ('orders','tiers','transactions','saved','sections','early-supporters','banners')):data=[]
   route.fulfill(status=200,json=data)
  ctx.route('**/api/**',api);ctx.route('https://*.onesignal.com/**',lambda r:r.abort());ctx.route('https://res.cloudinary.com/**',lambda r:r.abort())
  page=ctx.new_page();page.goto(BASE+'/wallet'+('?transfer='+ref if case=='flag_off_receipt' else ''),wait_until='domcontentloaded')
  if page.get_by_role('button',name='Essential only').count():page.get_by_role('button',name='Essential only').click()
  if case=='flag_off_receipt':
   dialog=page.get_by_role('dialog');expect(dialog.get_by_role('alert')).to_contain_text('could not be loaded for your account')
   expect(page.get_by_role('button',name='Send money',exact=True)).to_have_count(0)
   assert not posts;ctx.close();print('PASS:',case);continue
  expect(page.get_by_role('button',name='Send money',exact=True)).to_be_visible()
  if page.get_by_role('button',name='Essential only').count():page.get_by_role('button',name='Essential only').click()
  assert not any('/wallet/transfers' in path for method,path in calls),'Transfer data must be lazy'
  page.get_by_role('button',name='Send money',exact=True).click();dialog=page.get_by_role('dialog')
  dialog.get_by_label('Friend’s referral code').fill('bob123');dialog.get_by_role('button',name='Find recipient',exact=True).click()
  expect(dialog.get_by_text('Bob',exact=True)).to_be_visible()
  dialog.get_by_label('Amount (₦)').fill('250.251');dialog.get_by_role('button',name='Review transfer',exact=True).click();assert not posts
  expect(dialog.get_by_label('Amount (₦)')).to_be_visible()
  dialog.get_by_label('Amount (₦)').fill('250.25');dialog.get_by_label('Note (optional)').fill('Dinner together')
  dialog.get_by_role('button',name='Review transfer',exact=True).click();expect(dialog.get_by_text('Review your transfer',exact=True)).to_be_visible();assert not posts
  dialog.get_by_role('button',name='Send ₦250.25',exact=True).click()
  if case=='denied':
   expect(dialog.get_by_role('alert')).to_contain_text('Insufficient')
   expect(dialog.get_by_label('Friend’s referral code')).to_be_visible()
   assert page.evaluate(f"sessionStorage.getItem('hg_pending_wallet_transfer_v1:{U}')")==None
  else:
   if case.startswith('uncertain'):
    expect(dialog.get_by_role('button',name='Retry this same transfer',exact=True)).to_be_visible()
    assert len(posts)==1
    saved=json.loads(page.evaluate(f"sessionStorage.getItem('hg_pending_wallet_transfer_v1:{U}')"));assert saved['request_id']==posts[0]['request_id']
    if case=='uncertain_retry':
     dialog.get_by_role('button',name='Check transfer',exact=True).click();expect(dialog.get_by_role('alert')).to_contain_text('No completed receipt')
     dialog.get_by_role('button',name='Retry this same transfer',exact=True).click()
     expect(dialog.get_by_text('Sent successfully',exact=True)).to_be_visible()
     assert len(posts)==2 and posts[0]==posts[1]
    else:
     page.reload(wait_until='domcontentloaded');page.get_by_role('button',name='Send money',exact=True).click();dialog=page.get_by_role('dialog')
     expect(dialog.get_by_text('Sent successfully',exact=True)).to_be_visible();assert len(posts)==1
   expect(dialog.get_by_text('Sent successfully',exact=True)).to_be_visible()
   expect(dialog.get_by_text('₦749.75',exact=True)).to_be_visible()
   assert page.evaluate(f"sessionStorage.getItem('hg_pending_wallet_transfer_v1:{U}')")==None
   assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
   if case=='normal_mobile':page.screenshot(path='work/wallet-transfer-mobile-receipt.png',full_page=True)
   dialog.get_by_role('button',name='Done',exact=True).click()
   expect(page.get_by_role('button',name='View receipt',exact=True)).to_be_visible()
   page.get_by_role('button',name='View receipt',exact=True).click();expect(page.get_by_role('dialog').get_by_text('Sent successfully',exact=True)).to_be_visible()
  ctx.close();print('PASS:',case)
 browser.close()
