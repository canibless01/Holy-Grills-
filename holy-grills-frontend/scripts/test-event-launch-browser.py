"""Native launch repairs with controlled APIs; no real tickets or provider writes."""
import os,signal,subprocess,tempfile,time,base64
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
repo=Path(__file__).resolve().parents[1];out=Path(tempfile.mkdtemp(prefix='hg-event-launch-'))
E='11111111-1111-4111-8111-111111111111';T='22222222-2222-4222-8222-222222222222';C='33333333-3333-4333-8333-333333333333';S='44444444-4444-4444-8444-444444444444'
png='data:image/png;base64,'+base64.b64encode((repo/'scripts/fixtures/event-ticket-qr.png').read_bytes()).decode()
expect.set_options(timeout=20000)
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5279','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
try:
 time.sleep(2)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  for width in (393,1280):
   writes=[];requests=[];qr_calls=[];errors=[];state={'saved':None,'lost':True,'guest':False,'support':False,'detail_failed':False}
   event={'id':E,'slug':'launch-night-12345678','title':'Community launch','description':'First paragraph\n\nSecond paragraph','location':'FUTA Hall','starts_at':'2027-12-01T10:00:12Z','ends_at':'2027-12-01T12:00:12Z','is_paid':False,'is_published':True,'campus_id':C,'image_url':png,'capacity':200,'hp_reward':50,'registration_fields':[{'name':'department','label':'Department','type':'select','options':['Computing','Agriculture'],'required':True},{'name':'interests','label':'Interests','type':'multiselect','options':['Music','Food'],'required':True}]}
   def api(route):
    req=route.request;path=urlparse(req.url).path;data={};requests.append((path,req.headers))
    if path.endswith('/auth/me'):data={'id':S,'role':'super_admin','campus_id':C,'is_active':True,'profile':{'id':S,'role':'super_admin','campus_id':C}}
    elif path.endswith('/campuses'):data=[{'id':C,'name':'FUTA','slug':'futa','is_active':True}]
    elif path.endswith('/feature-flags'):data=[{'feature_name':'events','is_active':True}]
    elif path.endswith('/events/admin'):data={'events':[state['saved']] if state['saved'] else []}
    elif path=='/api/events' and req.method=='POST':
     body=req.post_data_json;writes.append(body)
     if not state['saved']:state['saved']={**event,**body,'id':body['request_id']}
     if state['lost']:state['lost']=False;route.fulfill(status=504,json={'error':'Controlled timeout after saved event'});return
     data=state['saved']
    elif path.startswith('/api/events/') and req.method=='PATCH':writes.append(req.post_data_json);state['saved'].update(req.post_data_json);data=state['saved']
    elif path=='/api/events':data=[event]
    elif path.endswith('/tiers'):data=[{'id':T,'name':'Free admission','price_naira':0,'price_naira_full':0,'capacity':100,'sold_count':0},{'id':S,'name':'Optional support','price_naira':200,'price_naira_full':200,'capacity':100,'sold_count':0}]
    elif path.endswith('/register'):
     writes.append(req.post_data_json);assert req.post_data_json['registration_answers']=={'department':'Computing','interests':['Music']}
     data={'authorization_url':'https://checkout.paystack.com/controlled-audit','ticket_id':T,'status':'pending_payment','payment_status':'pending'} if req.post_data_json['tier_id']==S else {'ticket_id':T,'status':'confirmed','payment_status':'not_required'}
    elif path.endswith('/qr'):
     qr_calls.append(req.post_data_json);data={'ticket_id':T,'status':'confirmed','payment_status':'not_required','qr_image':png,'qr_payload':f'hg-event:{E}:{T}'}
    elif path in ('/api/events/'+E,'/api/events/launch-night-12345678'):
     if state['detail_failed']:route.fulfill(status=503,json={'error':'Controlled detail timeout'});return
     data=event
    route.fulfill(json=data)
   ctx=browser.new_context(viewport={'width':width,'height':1000});ctx.route('**/api/**',api)
   ctx.add_init_script("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_role','super_admin');localStorage.setItem('hg_admin_campus_id','"+C+"');localStorage.setItem('hg_user_campus_id','"+C+"');localStorage.setItem('hg_cookie_consent',JSON.stringify({essential:true,analytics:false,date:new Date().toISOString()}));")
   page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto('http://127.0.0.1:5279/admin?section=events')
   page.get_by_role('button',name='Add Event',exact=True).click();dialog=page.get_by_role('dialog',name='New Event',exact=True)
   dialog.get_by_label('Title',exact=True).fill('Community launch');dialog.get_by_label('Location',exact=True).fill('FUTA Hall');dialog.get_by_label('Starts (WAT)',exact=True).fill('2027-12-01T11:00');dialog.get_by_label('Ends (WAT)',exact=True).fill('2027-12-01T13:00')
   dialog.get_by_role('button',name='Add question',exact=True).click();dialog.get_by_label('Question',exact=True).fill('Department');dialog.get_by_label('Answer type',exact=True).select_option('select');dialog.get_by_label('Options, one per line',exact=True).fill('Computing\nAgriculture\n');dialog.get_by_label('Required',exact=True).check()
   dialog.get_by_role('button',name='Create Event',exact=True).click();expect(page.get_by_text('Controlled timeout after saved event',exact=True)).to_be_visible();dialog.get_by_role('button',name='Create Event',exact=True).click();expect(dialog).to_have_count(0)
   assert len(writes)==2 and writes[0]==writes[1] and writes[0]['request_id']==writes[1]['request_id'];assert writes[0]['registration_fields'][0]['options']==['Computing','Agriculture']
   page.get_by_role('button',name='Edit event',exact=True).click();dialog=page.get_by_role('dialog',name='Edit Event',exact=True);dialog.get_by_label('Max attendees',exact=True).fill('300');dialog.get_by_role('button',name='Save Changes',exact=True).click();expect(dialog).to_have_count(0);assert writes[-1]['capacity']==300 and 'starts_at' not in writes[-1] and 'hp_required' not in writes[-1]
   ctx.close()
   ctx=browser.new_context(viewport={'width':width,'height':1000});ctx.route('**/api/**',api);ctx.add_init_script("localStorage.setItem('hg_campus_id','"+C+"');localStorage.setItem('hg_cookie_consent',JSON.stringify({essential:true,analytics:false,date:new Date().toISOString()}));")
   page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto('http://127.0.0.1:5279/events/launch-night-12345678');expect(page.get_by_role('heading',name='Community launch',exact=True)).to_be_visible();assert page.get_by_text('First paragraph\n\nSecond paragraph',exact=True).evaluate('(el)=>getComputedStyle(el).whiteSpace')=='pre-wrap'
   expect(page.get_by_text('Admission is free. Choose a free ticket, or select an optional paid support tier when you register.',exact=True)).to_be_visible();page.get_by_role('button',name='Get Your Ticket',exact=True).click()
   page.get_by_role('button',name='Free admission',exact=False).click();page.get_by_placeholder('Full name *',exact=True).fill('Guest attendee');page.get_by_role('textbox',name='Email',exact=True).fill('guest@example.invalid');page.get_by_placeholder('Phone *',exact=True).fill('08012345678');page.locator('select').select_option('Computing');page.get_by_label('Music',exact=True).check();page.get_by_role('button',name='Confirm registration',exact=True).click();expect(page.get_by_alt_text('Your event ticket QR code',exact=True)).to_be_visible();expect(page.get_by_role('link',name='Create an account',exact=True)).to_be_visible();assert writes[-1]['tier_id']==T
   page.goto('http://127.0.0.1:5279/events/'+E);page.get_by_role('button',name='Get Your Ticket',exact=True).click();page.get_by_role('button',name='Optional support',exact=False).click();page.get_by_placeholder('Full name *',exact=True).fill('Support attendee');page.get_by_role('textbox',name='Email',exact=True).fill('support@example.invalid');page.get_by_placeholder('Phone *',exact=True).fill('08012345678');page.locator('select').select_option('Computing');page.get_by_label('Music',exact=True).check();page.route('https://checkout.paystack.com/controlled-audit',lambda route:route.fulfill(content_type='text/html',body='<h1>Controlled payment gateway</h1>'));page.get_by_role('button',name='Confirm and pay',exact=True).click();expect(page.get_by_role('heading',name='Controlled payment gateway',exact=True)).to_be_visible();assert writes[-1]['tier_id']==S
   page.goto('http://127.0.0.1:5279/events/'+E+'#ticket='+T+'&access=controlled-signed-fixture');expect(page.get_by_alt_text('Your event ticket QR code',exact=True)).to_be_visible();assert qr_calls[-1]=={'access_token':'controlled-signed-fixture'}
   state['detail_failed']=True;page.reload();expect(page.get_by_role('alert')).to_contain_text('The event could not be loaded');state['detail_failed']=False;page.get_by_role('button',name='Retry',exact=True).click();expect(page.get_by_role('heading',name='Community launch',exact=True)).to_be_visible()
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');assert not errors,errors;page.screenshot(path=str(out/f'event-launch-{width}.png'),full_page=True);ctx.close()
   print(f'PASS {width}: one committed create on timeout retry, capacity-only patch, question editor/answers, readable slug, paragraphs, free confirmation and paid-support gateway navigation, guest signup prompt, signed email ticket opening and visible read retry; screenshots={out}',flush=True)
  browser.close()
finally:os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
