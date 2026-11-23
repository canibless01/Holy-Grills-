"""Native group registration/questions/payment recovery; controlled HTTP only."""
import json,os,re
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('HG_BROWSER_BASE','http://127.0.0.1:4185')
E='11111111-1111-4111-8111-111111111111';C='22222222-2222-4222-8222-222222222222';U='33333333-3333-4333-8333-333333333333';G='44444444-4444-4444-8444-444444444444';T='55555555-5555-4555-8555-555555555555';T2='66666666-6666-4666-8666-666666666666'
PNG='data:image/png;base64,'+__import__('base64').b64encode((Path(__file__).parent/'fixtures/event-ticket-qr.png').read_bytes()).decode()
fields=[{'name':kind,'label':label,'type':kind,'options':['A','B'],'required':True} for kind,label in [('text','Short answer'),('textarea','Long answer'),('select','Choice'),('radio','Preference'),('multiselect','Interests'),('checkbox','Consent'),('date','Date'),('email','Contact email'),('number','Number')]]
with sync_playwright() as pw:
 browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);expect.set_options(timeout=15000)
 for width in (393,1280):
  for case in ('member','guest_card','split','timeout','settled_race','free_friend','questions_changed'):
   member=case not in ('guest_card','free_friend');count=1 if case=='free_friend' else 2;calls=[];errors=[];state={'group':None,'lost':case=='timeout','charged':False,'qr':[]}
   ctx=browser.new_context(viewport={'width':width,'height':1000},permissions=['clipboard-read','clipboard-write'])
   values={'hg_campus_id':C,'hg_user_campus_id':C,'hg_cookie_consent':json.dumps({'essential':True,'analytics':False,'date':'2026-11-23'})}
   if member:values.update(hg_access_token='controlled',hg_user_role='student')
   ctx.add_init_script('for(const[k,v]of Object.entries('+json.dumps(values)+'))localStorage.setItem(k,v);')
   event={'id':E,'title':'Controlled group event','location':'Campus Hall','starts_at':'2027-12-01T10:00:00Z','ends_at':'2027-12-01T12:00:00Z','capacity':30,'is_published':True,'campus_id':C,'hp_reward':50,'registration_fields':fields}
   def api(route):
    request=route.request;path=urlparse(request.url).path;method=request.method;data={}
    if path.endswith('/auth/me'):data={'id':U,'role':'student','campus_id':C,'email':'buyer@example.invalid','phone':'08012345678','full_name':'Controlled buyer','is_active':True}
    elif path.endswith('/campuses'):data=[{'id':C,'name':'FUTA','is_active':True}]
    elif path.endswith('/feature-flags'):data=[{'feature_name':'events','is_active':True}]
    elif path.endswith('/events/'+E+'/tiers'):data=[{'id':T,'name':'Standard','price_naira_full':0 if case=='free_friend' else 100,'price_naira':0 if case=='free_friend' else 80,'capacity':20,'sold_count':0},{'id':T2,'name':'Support','price_naira_full':200,'price_naira':160,'capacity':20,'sold_count':0}]
    elif path.endswith('/events/my-tickets'):data={'upcoming':[{'id':'own-ticket','event_id':E,'status':'confirmed','payment_status':'not_required'}] if member else []}
    elif path.endswith('/events/'+E):data=event
    elif path.endswith('/events/'+E+'/groups') and method=='GET':data={'groups':[]}
    elif path.endswith('/events/'+E+'/groups') and method=='POST':
     body=request.post_data_json;calls.append(('register',body))
     assert len(body['attendees'])==count and body['expected_subtotal']==(0 if case=='free_friend' else 300)
     assert body['registration_answers']['radio']=='A'
     assert body['registration_answers']['textarea']=='First paragraph\n\nSecond paragraph'
     assert body['registration_answers']['multiselect']==['A','B'] and body['registration_answers']['checkbox'] is True
     assert body['booking_notes']=='2 vegetarian and 3 regular'
     assert all('answers' not in row and 'name' not in row and 'phone' not in row for row in body['attendees'])
     assert body.get('use_hp') in (None,False)
     if case=='questions_changed' and len([entry for entry in calls if entry[0]=='register'])==1:
      route.fulfill(status=400,json={'error':'Attendee 1: New question','registration_fields':fields+[{'name':'new_question','label':'New question','type':'text','required':True}]});return
     if case=='questions_changed':assert body['registration_answers']['new_question']=='Kept shared answers'
     pending=case in ('guest_card','split','settled_race')
     if state['group'] is None:
      state['group']={'id':G,'event_id':E,'payment_status':'pending' if pending else 'not_required' if case=='free_friend' else 'paid','total':0 if case=='free_friend' else 300,'wallet_amount':150 if case=='split' else 0 if pending or case=='free_friend' else 300,'card_amount':150 if case=='split' else 300 if pending else 0,'expires_at':'2027-12-01T09:00:00Z','access_token':'private-buyer-proof','tickets':[{'id':T if index==0 else T2,'name':row['email'],'email':row['email'],'tier_name':'Standard' if index==0 else 'Support','status':'pending_payment' if pending else 'confirmed','payment_status':'pending' if pending else 'not_required' if case=='free_friend' else 'paid','price':0 if case=='free_friend' else 100 if index==0 else 200,**({} if pending else {'access_token':'attendee-'+str(index)})} for index,row in enumerate(body['attendees'])]}
     if state['lost']:state['lost']=False;route.fulfill(status=504,json={'error':'Controlled response lost after booking committed'});return
     data=state['group']
    elif path.endswith('/groups/'+G):data=state['group']
    elif path.endswith('/groups/'+G+'/payment'):
     calls.append(('initialize',request.post_data_json));assert request.post_data_json.get('access_token')==('private-buyer-proof' if not member else '')
     if case=='settled_race':
      state['group']['payment_status']='paid'
      for index,row in enumerate(state['group']['tickets']):row.update(status='confirmed',payment_status='paid',access_token='attendee-'+str(index))
      data=state['group']
     else:data={'authorization_url':'https://checkout.paystack.com/controlled-group'}
    elif path.endswith('/groups/'+G+'/verify'):
     calls.append(('verify',request.post_data_json));state['group']['payment_status']='paid'
     for index,row in enumerate(state['group']['tickets']):row.update(status='confirmed',payment_status='paid',access_token='attendee-'+str(index))
     data=state['group']
    elif path.endswith('/qr'):
     state['qr'].append((path,request.post_data_json));data={'qr_image':PNG}
    elif '/notifications' in path:data={'notifications':[],'unread_count':0}
    route.fulfill(status=200,json=data)
   ctx.route('**/api/**',api);ctx.route('https://checkout.paystack.com/**',lambda route:route.fulfill(content_type='text/html',body='<h1>Controlled group payment</h1>'))
   page=ctx.new_page();page.on('pageerror',lambda error:errors.append(str(error)));page.goto(BASE+'/events/'+E,wait_until='domcontentloaded')
   page.get_by_role('button',name='Book for a group',exact=True).click();dialog=page.get_by_role('dialog',name='Book for a group',exact=True)
   if not member:
    buyer=dialog.locator('section').first
    buyer.get_by_label('Name',exact=True).fill('Guest purchaser');buyer.get_by_label('Email',exact=True).fill('buyer@example.invalid');buyer.get_by_label('Phone',exact=True).fill('08012345678')
   if count==1:dialog.locator('details').nth(1).get_by_role('button',name='Remove attendee',exact=True).click()
   for index in range(count):
    attendee=dialog.locator('details').nth(index)
    assert attendee.get_by_label('Name',exact=True).count()==0 and attendee.get_by_label('Phone',exact=True).count()==0
    attendee.get_by_label('Email',exact=True).fill('attendee-'+str(index+1)+'@example.invalid')
    attendee.get_by_label('Ticket tier',exact=True).select_option(T if index==0 else T2)
   dialog.get_by_label('Short answer *',exact=True).fill('Shared booking answer');dialog.get_by_label('Long answer *',exact=True).fill('First paragraph\n\nSecond paragraph')
   dialog.get_by_role('combobox',name='Choice',exact=True).select_option('A')
   dialog.get_by_role('group',name='Preference *',exact=True).get_by_label('A',exact=True).check()
   interests=dialog.get_by_role('group',name='Interests *',exact=True);interests.get_by_label('A',exact=True).check();interests.get_by_label('B',exact=True).check()
   dialog.get_by_label('Date *',exact=True).fill('2026-11-23');dialog.get_by_label('Contact email *',exact=True).fill('contact@example.invalid');dialog.get_by_label('Number *',exact=True).fill('2.5')
   dialog.get_by_label('Group notes (optional)',exact=True).fill('2 vegetarian and 3 regular')
   dialog.get_by_role('button',name='Continue to group booking',exact=True).click();assert not calls
   dialog.get_by_label('Consent *',exact=True).check()
   if case=='settled_race':dialog.get_by_label('Payment method',exact=True).select_option('card')
   if case=='split':dialog.get_by_label('Payment method',exact=True).select_option('split');dialog.get_by_label('Wallet contribution',exact=True).fill('150')
   dialog.get_by_role('button',name='Continue to group booking',exact=True).click()
   if case=='questions_changed':
    expect(dialog.get_by_role('alert')).to_contain_text('New question')
    dialog.get_by_label('New question *',exact=True).fill('Kept shared answers')
    dialog.get_by_role('button',name='Continue to group booking',exact=True).click()
   if case=='timeout':
    expect(dialog.get_by_role('alert')).to_contain_text('Controlled response lost');expect(dialog.get_by_role('button',name='Recover group booking',exact=True)).to_be_visible();page.reload();page.get_by_role('button',name='Book for a group',exact=True).click();page.get_by_role('button',name='Recover group booking',exact=True).click()
   page.wait_for_url('**/events/'+E+'/group/'+G)
   if case in ('guest_card','split','settled_race'):

    expect(page.get_by_text('Payment not yet confirmed',exact=True)).to_be_visible();expect(page.get_by_role('button',name='View ticket',exact=True)).to_have_count(0)
    page.get_by_role('button',name=re.compile('^Pay ₦')).click()
    if case!='settled_race':page.wait_for_url('https://checkout.paystack.com/**')
    if case!='settled_race':page.goto(BASE+'/events/'+E+'/group/'+G+'?reference=controlled-reference',wait_until='domcontentloaded')
   expect(page.get_by_text('1 ticket confirmed' if count==1 else '2 tickets confirmed',exact=True)).to_be_visible()
   page.get_by_role('button',name='View ticket',exact=True).first.click();expect(page.get_by_alt_text('Your event ticket QR code',exact=True)).to_be_visible();assert state['qr'][-1][1]=={'access_token':'attendee-0'}
   if count==2:
    page.get_by_role('button',name='View ticket',exact=True).last.click();expect(page.get_by_alt_text('Your event ticket QR code',exact=True)).to_be_visible();assert state['qr'][-1][1]=={'access_token':'attendee-1'}
   requests=[body for kind,body in calls if kind=='register'];assert len(requests)==(2 if case in ('timeout','questions_changed') else 1)
   if case=='timeout':assert requests[0]==requests[1]
   if case=='questions_changed':assert requests[0]['idempotency_key']!=requests[1]['idempotency_key']
   page.get_by_role('button',name='Copy private booking link',exact=True).click();expect(page.get_by_role('button',name='Private booking link copied',exact=True)).to_be_visible()
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(width,case);assert not errors,errors
   page.screenshot(path=f'/workspace/work/group-events/{case}-{width}.png',full_page=True);ctx.close();print(json.dumps({'width':width,'case':case,'passed':True,'external_writes':0}),flush=True)
 browser.close()
