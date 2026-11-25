"""Native wallet/admin UI with controlled API transport; no real payment/messages."""
import json,os
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('HG_BROWSER_BASE','http://127.0.0.1:4185');WORK=os.environ.get('HG_BROWSER_WORK','/workspace/work/delivery-pass');os.makedirs(WORK,exist_ok=True)
C='11111111-1111-4111-8111-111111111111';U='22222222-2222-4222-8222-222222222222';R='33333333-3333-4333-8333-333333333333';M='44444444-4444-4444-8444-444444444444'
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);expect.set_options(timeout=15000)
 for width in (393,1280):
  for role in ('student','admin'):
   ctx=browser.new_context(viewport={'width':width,'height':1000});errors=[];calls=[];bodies=[];state={'membership':None,'pending':None,'history':[],'available':True,'fail':True,'refund':False}
   ctx.add_init_script('for(const[k,v]of Object.entries('+json.dumps({'hg_access_token':'controlled','hg_user_role':role,'hg_campus_id':C,'hg_user_campus_id':C,'hg_cookie_consent':json.dumps({'essential':True,'analytics':False,'date':'2026-11-25'})})+'))localStorage.setItem(k,v);')
   receipt={'id':R,'membership_id':M,'status':'paid','amount_kobo':100000,'method':'wallet','period_until':'2027-01-01T12:00:00Z','created_at':'2026-11-25T12:00:00Z','full_name':'Controlled member'}
   offer={'price_kobo':100000,'is_active':True,'updated_at':'2026-11-25T12:00:00Z'}
   def api(route):
    req=route.request;path=urlparse(req.url).path;method=req.method;data=[];calls.append((path,method))
    if path.endswith('/auth/me'):data={'id':U,'role':role,'campus_id':C,'full_name':'Controlled member','is_active':True}
    elif path.endswith('/campuses'):data=[{'id':C,'name':'FUTA','is_active':True}]
    elif path.endswith('/wallet'):data={'balance':5000,'hp_balance':0}
    elif path.endswith('/hp/balance'):data={'active':0,'pending':0}
    elif path.endswith('/admin/delivery-pass'):
     if method=='PATCH':
      body=req.post_data_json;bodies.append(body);assert body['campus_id']==C and body['expected_updated_at']==offer['updated_at'];offer.update(price_kobo=round(body['price']*100),is_active=body['is_active']);data={'offer':offer}
     elif state['fail']:state['fail']=False;route.fulfill(status=503,json={'error':'Controlled report retry'});return
     else:data={'offer':offer,'enabled':False,'renewals_ready':False,'active_members':1,'renewing_members':0,'revenue_kobo':0 if state['refund'] else 100000,'refunds_kobo':100000 if state['refund'] else 0,'receipts':[{**receipt,'status':'refunded' if state['refund'] else 'paid'}]}
    elif path.endswith('/refund'):
     body=req.post_data_json;bodies.append(body);assert body['reason']=='Support review' and body['acknowledge'] is True;state['refund']=True;data={'receipt':{**receipt,'status':'refunded'}}
    elif path.endswith('/delivery-pass/buy'):
     body=req.post_data_json;bodies.append(body);assert body['auto_renew'] is False and body['price']==1000
     state['membership']={'id':M,'active':True,'paid_until':receipt['period_until'],'price_kobo':100000,'auto_renew':False};state['history']=[receipt];data={'receipt':receipt}
    elif '/delivery-pass/receipts/' in path and path.endswith('/verify'):
     state['membership']={'id':M,'active':True,'paid_until':receipt['period_until'],'price_kobo':100000,'auto_renew':False};state['pending']=None;data={'receipt':receipt}
    elif path.endswith('/delivery-pass'):
     data={'campus_name':'FUTA','campus_id':C,'available':state['available'],'offer':offer,'renewals_ready':False,'card_available':True,'consent_version':'delivery-pass-wallet-v1','membership':state['membership'],'pending':state['pending'],'history':state['history']}
    elif 'notifications' in path:data={'notifications':[],'unread_count':0}
    elif 'cart' in path:data={'items':[]}
    route.fulfill(status=200,json=data)
   ctx.route('**/api/**',api);ctx.route('https://*.onesignal.com/**',lambda r:r.abort());page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
   if role=='student':
    page.goto(BASE+'/wallet',wait_until='domcontentloaded');page.get_by_role('button',name='See delivery pass',exact=True).click();dialog=page.get_by_role('dialog');expect(dialog.get_by_role('checkbox')).to_be_disabled();page.screenshot(path=f'{WORK}/pass-wallet-{width}.png',full_page=True)
    dialog.get_by_role('button',name='Pay ₦1,000 for one month',exact=True).click();expect(dialog.get_by_text('Your delivery pass is active',exact=True)).to_be_visible();assert len(bodies)==1
    # Reload with original callback and paid coverage despite paused future sales.
    state['available']=False;page.goto(BASE+'/wallet?delivery_pass='+R+'&reference=HG-PASS-'+R,wait_until='domcontentloaded');expect(page.get_by_role('dialog').get_by_text('Your delivery pass is active',exact=True)).to_be_visible()
    assert len([x for x in calls if x[0].endswith('/verify')])==1
    assert not any('/payments/verify' in path or '/wallet/verify' in path for path,_ in calls),calls
   else:
    page.goto(BASE+'/admin?section=deliverypass',wait_until='domcontentloaded');expect(page.get_by_role('alert')).to_contain_text('Controlled report retry');page.get_by_role('button',name='Retry',exact=True).last.click();price=page.get_by_label('Monthly price (₦)',exact=True);expect(price).to_have_value('1000');price.fill('1200');page.get_by_role('button',name='Save delivery plan',exact=True).click();expect(price).to_have_value('1200');page.screenshot(path=f'{WORK}/pass-admin-{width}.png',full_page=True)
    page.get_by_role('button',name='Refund pass',exact=True).click();dialog=page.get_by_role('dialog');submit=dialog.get_by_role('button',name='Refund ₦1,000 to wallet',exact=True);expect(submit).to_be_disabled();dialog.get_by_label('Reason for refund',exact=True).fill('Support review');expect(submit).to_be_disabled();dialog.get_by_role('checkbox').check();submit.click();expect(page.get_by_text('Refunded',exact=True)).to_be_visible();assert len([x for x in calls if x[0].endswith('/refund')])==1
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(width,role)
   assert not errors,errors
   print(json.dumps({'width':width,'role':role,'passed':True}),flush=True);ctx.close()
 browser.close()
