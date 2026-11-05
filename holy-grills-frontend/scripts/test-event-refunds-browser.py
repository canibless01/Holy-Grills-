"""Local native admin refund forms. All API and provider traffic is intercepted."""
import json, os, sys
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect
ID='11111111-1111-4111-8111-111111111111'
TICKET='22222222-2222-4222-8222-222222222222'
CHECKED='33333333-3333-4333-8333-333333333333'
GUEST='44444444-4444-4444-8444-444444444444'
C='70000001-cafe-cafe-cafe-000000000001'
mobile='--desktop' not in sys.argv
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 context=browser.new_context(viewport={'width':393 if mobile else 1280,'height':852},is_mobile=mobile)
 context.add_init_script("localStorage.setItem('hg_access_token','synthetic-local-only');localStorage.setItem('hg_user_role','super_admin');localStorage.setItem('hg_campus_id','"+C+"');localStorage.setItem('hg_user_campus_id','"+C+"');localStorage.setItem('hg_install_dismissed',String(Date.now()));")
 calls=[];writes=[];reviews=[];errors=[];allow_success=[False]
 event={'id':ID,'title':'Refund audit','campus_id':C,'is_published':True,'is_paid':True,'max_attendees':10,'checkin_count':1,'location':'FUTA'}
 member={'id':ID,'ticket_id':TICKET,'recipient_name':'Member audit','amount':600,'hp_amount':50,'destination':'wallet','state':'completed'}
 guest={'id':GUEST,'ticket_id':GUEST,'recipient_name':'Guest audit','amount':1000,'hp_amount':0,'destination':'paystack','state':'uncertain'}
 def api(route):
  request=route.request;path=urlparse(request.url).path;calls.append(path);data={}
  if path.endswith('/auth/me'):data={'id':ID,'role':'super_admin','full_name':'Local audit','campus_id':C,'profile':{'campus_id':C},'is_active':True}
  elif 'campuses' in path:data=[{'id':C,'name':'FUTA','slug':'futa','is_active':True}]
  elif path.endswith('/registrants'):data={'registrants':[{'ticket_id':TICKET,'full_name':'Member audit','email':'member@example.invalid','payment_status':'paid','checked_in':False,'refundable':True,'refund_amount':600,'hp_paid':50,'is_guest':False},{'ticket_id':CHECKED,'full_name':'Checked audit','checked_in':True,'refundable':False}]}
  elif path.endswith('/refund') and request.method=='POST':
   writes.append(request.post_data_json)
   if not allow_success[0]:return route.fulfill(status=409,content_type='application/json',body=json.dumps({'error':'Simulated lost-response retry'}))
   data={'id':ID,'state':'completed','destination':'wallet','amount':600,'hp_returned':50}
  elif path.endswith('/review') and request.method=='POST':
   reviews.append(request.post_data_json);guest['state']='processing';guest['provider_refund_id']='123';data={'state':'processing'}
  elif path.endswith('/refunds'):data={'refunds':[member,guest]}
  elif 'events' in path:data={'events':[event]}
  elif '/notifications' in path:data={'notifications':[],'unread_count':0}
  elif any(x in path for x in ('tiers','saved','menu','feature-flags')):data=[]
  elif 'cart' in path:data={'items':[]}
  route.fulfill(status=200,content_type='application/json',body=json.dumps(data))
 context.route('**/api/**',api);context.route('https://*.onesignal.com/**',lambda r:r.abort())
 page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(os.environ.get('HG_BROWSER_BASE_URL','http://127.0.0.1:5177').rstrip('/')+'/admin?section=events',wait_until='domcontentloaded')
 expect(page.get_by_text('Refund audit',exact=True)).to_be_visible(timeout=30000)
 assert not any(path.endswith('/refunds') for path in calls)
 page.get_by_role('button',name='Registrants',exact=True).click()
 regs=page.get_by_role('dialog',name='Event Registrants',exact=True)
 expect(regs.get_by_role('button',name='Refund ticket',exact=True)).to_have_count(1)
 regs.get_by_role('button',name='Refund ticket',exact=True).click()
 form=page.get_by_role('dialog',name='Refund entire ticket',exact=True)
 expect(form.get_by_role('button',name='Confirm full refund',exact=True)).to_be_disabled()
 expect(form.get_by_text('Holy Grills wallet',exact=False)).to_be_visible()
 form.get_by_label('Refund reason').fill('Customer requests cancellation before check-in')
 form.get_by_role('button',name='Confirm full refund',exact=True).click()
 expect(form.get_by_role('alert')).to_be_visible()
 allow_success[0]=True
 form.get_by_role('button',name='Confirm full refund',exact=True).click()
 history=page.get_by_role('dialog',name='Ticket refunds',exact=True)
 expect(history.get_by_text('Member audit',exact=True)).to_be_visible()
 assert len(writes)==2 and writes[0]['request_id']==writes[1]['request_id']
 assert 'amount' not in writes[0]
 history.get_by_role('button',name='Review gateway result',exact=True).click()
 review=page.get_by_role('dialog',name='Review guest refund',exact=True)
 expect(review.get_by_role('button',name='Save gateway review',exact=True)).to_be_disabled()
 review.get_by_label('Paystack refund ID').fill('123')
 review.get_by_label('Provider log evidence').fill('Paystack dashboard confirms refund ID 123 for this charge')
 review.get_by_role('button',name='Save gateway review',exact=True).click()
 expect(history.get_by_text('Paystack refund ID: 123',exact=True)).to_be_visible()
 assert len(reviews)==1 and reviews[0]['outcome']=='lookup' and reviews[0]['provider_refund_id']=='123'
 assert not errors,errors
 print(json.dumps({'mobile':mobile,'native_refund_and_review_forms':True,'checked_in_action_hidden':True,'reason_required':True,'response_loss_same_request_id':True,'amount_server_owned':True,'provider_evidence_required':True,'refresh_result_rendered':True,'console_errors':errors,'production_writes':0}))
 browser.close()
