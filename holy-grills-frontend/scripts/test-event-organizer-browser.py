"""Organizer/admin native journeys; HTTP fully intercepted, no bank/provider writes."""
import os,signal,subprocess,tempfile,time
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import sync_playwright,expect
repo=Path(__file__).resolve().parents[1];out=Path(tempfile.mkdtemp(prefix='hg-organizer-'))
A='11111111-1111-4111-8111-111111111111';OWNER='22222222-2222-4222-8222-222222222222';TIER='33333333-3333-4333-8333-333333333333';TICKET='44444444-4444-4444-8444-444444444444';ADMIN='55555555-5555-4555-8555-555555555555'
ROOT='/api/event-organizer/events';png='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII='
expect.set_options(timeout=20000)
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5270','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
try:
 time.sleep(2)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  for width in (393,1280):
   state={'event':None,'rate':None,'requests':[],'sold':False,'checked':False,'create_loss':True,'admission_loss':True,'payout_loss':True};writes=[];errors=[];role='event_organizer';actor=OWNER;private_reads=[]
   def attendees():return [{'ticket_id':TICKET,'full_name':'=Guest attendee','email':'guest@example.invalid','phone':'08000000000','tier_name':'Regular','status':'confirmed','payment_status':'paid','checked_in':state['checked']}] if state['sold'] else []
   def account():
    paid=sum(row['amount'] for row in state['requests'] if row['state']=='paid');reserved=sum(row['amount'] for row in state['requests'] if row['state'] in ('pending','approved'));earned=1500 if state['sold'] else 0
    return {'event':state['event'],'tiers':[{'id':TIER,'name':'Regular','price_naira':1600,'organizer_amount':state['rate']}],'counts':{'confirmed':int(state['sold']),'checked_in':int(state['checked']),'pending':0},'earned':earned,'paid':paid,'reserved':reserved,'available':max(0,earned-paid-reserved),'overpaid':0,'requests':state['requests']}
   def fixture(route):
    request=route.request;url=urlparse(request.url);path=url.path;q=parse_qs(url.query);data={}
    if path.endswith('/auth/me'):data={'id':actor,'role':role,'campus_id':A,'is_active':True,'profile':{'id':actor,'role':role,'campus_id':A,'is_active':True}}
    elif path.endswith('/campuses'):data=[{'id':A,'name':'Campus A','is_active':True}]
    elif path.endswith('/admin/users/'+OWNER):data={'id':OWNER,'full_name':'Organizer account','email':'organizer@example.invalid','role':'event_organizer','campus_id':A}
    elif path.endswith('/admin/users'):data=[{'id':OWNER,'full_name':'Organizer account','email':'organizer@example.invalid','role':'event_organizer','campus_id':A}]
    elif path.startswith(ROOT):
     private_reads.append((role,path,request.method,q))
     if actor not in (OWNER,ADMIN):route.fulfill(status=403,json={'error':'Controlled ownership denial'});return
     if path==ROOT and request.method=='GET':data={'events':[state['event']] if state['event'] else [],'has_more':False}
     elif path==ROOT and request.method=='POST':
      body=request.post_data_json;writes.append(('create',body));state['event']={'id':body['request_id'],'organizer_id':OWNER,'campus_id':A,'review_status':'draft','is_published':False,**{k:v for k,v in body.items() if k!='request_id'}}
      if state['create_loss']:state['create_loss']=False;route.fulfill(status=409,json={'error':'Controlled committed draft response loss'});return
      data=state['event']
     elif request.method=='PATCH':
      state['event'].update(request.post_data_json);state['event']['review_status']='draft';data=state['event']
     elif path.endswith('/submit'):
      writes.append(('submit',request.post_data_json));state['event']['review_status']='submitted';data=state['event']
     elif path.endswith('/review'):
      body=request.post_data_json;writes.append(('review',body));assert role=='admin'
      if body['action']=='configure':state['rate']=body['tiers'][0]['organizer_amount'];assert body['organizer_id']==OWNER
      elif body['action']=='approve':state['event'].update(review_status='approved',is_published=True)
      elif body['action']=='changes_requested':state['event'].update(review_status='changes_requested',review_notes=body['notes'])
      data=state['event']
     elif path.endswith('/door-qr'):data={'event_id':state['event']['id'],'qr_payload':f"hg-event:{state['event']['id']}:"+'a'*32,'qr_image':png}
     elif path.endswith('/attendees/export'):data={'attendees':attendees()}
     elif path.endswith('/attendees'):
      rows=attendees();search=q.get('q',[''])[0];data={'attendees':[r for r in rows if not search or search.lower() in ' '.join(str(v) for v in r.values()).lower()]}
     elif path.endswith('/checkin'):
      body=request.post_data_json;writes.append(('checkin',body));prior=state['checked'];state['checked']=True
      if state['admission_loss']:state['admission_loss']=False;route.fulfill(status=409,json={'error':'Controlled committed admission response loss'});return
      data={'completed':True,'replayed':prior,'hp_added_to_active':25}
     elif path.endswith('/payouts'):
      body=request.post_data_json;writes.append(('request',body));assert 'amount' not in body and body['account_number']=='0123456789'
      if not state['requests']:state['requests'].append({'id':body['request_id'],'event_id':state['event']['id'],'state':'pending','amount':1500,'bank_details':{k:body[k] for k in ('bank_name','account_name','account_number')}})
      if state['payout_loss']:state['payout_loss']=False;route.fulfill(status=409,json={'error':'Controlled committed payout response loss'});return
      data=state['requests'][0]
     elif '/payouts/' in path:
      body=request.post_data_json;writes.append(('payout',body));assert role=='admin';state['requests'][0]['state']='approved' if body['action']=='approve' else 'paid';state['requests'][0]['bank_transfer_reference']=body.get('reference');data=state['requests'][0]
     elif request.method=='GET':data=account()
    route.fulfill(status=200,json=data)
   def open_page(next_role,next_actor,url=None):
    global role,actor
    role=next_role;actor=next_actor
    ctx=browser.new_context(viewport={'width':width,'height':1000},accept_downloads=True);ctx.route('**/api/**',fixture)
    ctx.add_init_script("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_role','"+role+"');localStorage.setItem('hg_user_campus_id','"+A+"');localStorage.setItem('hg_admin_campus_id','"+A+"');")
    page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto(url or 'http://127.0.0.1:5270/event-manager');page.get_by_role('button',name='Essential only',exact=True).click();return ctx,page
   ctx,page=open_page('event_organizer',OWNER);page.get_by_role('button',name='Create event draft',exact=True).click();form=page.get_by_role('dialog',name='Event draft',exact=True)
   form.get_by_label('Event title',exact=True).fill('Organizer native journey');form.get_by_label('Venue / location',exact=True).fill('FUTA hall');form.get_by_label('Starts (WAT)',exact=True).fill('2026-12-01T10:00');form.get_by_label('Ends (WAT)',exact=True).fill('2026-12-01T12:00')
   form.get_by_role('button',name='Save draft',exact=True).evaluate('(b)=>{b.click();b.click()}');expect(form.get_by_role('alert')).to_contain_text('Controlled committed draft response loss');assert len([w for w in writes if w[0]=='create'])==1
   form.get_by_role('button',name='Save draft',exact=True).click();expect(form).to_have_count(0);creates=[body for kind,body in writes if kind=='create'];assert len(creates)==2 and creates[0]==creates[1]
   page.get_by_role('button',name='Submit for approval',exact=True).click();expect(page.get_by_role('button',name='Edit draft',exact=True)).to_have_count(0);expect(page.get_by_text('Awaiting review',exact=True).first).to_be_visible();event_id=state['event']['id'];url=f'http://127.0.0.1:5270/event-manager?event={event_id}';ctx.close()
   ctx,page=open_page('admin',ADMIN,url);page.get_by_label('Event review notes',exact=True).fill('Please update the venue description');page.get_by_role('button',name='Request event changes',exact=True).click();expect(page.get_by_text('Changes requested',exact=True).first).to_be_visible();ctx.close()
   ctx,page=open_page('event_organizer',OWNER,url);expect(page.get_by_text('Please update the venue description',exact=True)).to_be_visible();page.get_by_role('button',name='Edit draft',exact=True).click();edit=page.get_by_role('dialog',name='Event draft',exact=True);edit.get_by_label('Venue / location',exact=True).fill('Updated FUTA hall');edit.get_by_role('button',name='Save draft',exact=True).click();expect(edit).to_have_count(0);expect(page.get_by_text('Draft',exact=True).first).to_be_visible();page.get_by_role('button',name='Submit for approval',exact=True).click();expect(page.get_by_text('Awaiting review',exact=True).first).to_be_visible();ctx.close()
   ctx,page=open_page('admin',ADMIN,url);page.get_by_label('Organizer amount for Regular',exact=True).fill('1500');page.get_by_role('button',name='Save organizer terms',exact=True).click();expect(page.get_by_text('₦1,500.00 organizer amount per ticket',exact=True)).to_be_visible()
   page.get_by_role('button',name='Approve and publish',exact=True).click();expect(page.get_by_role('link',name='View event page',exact=True)).to_be_visible();assert state['event']['review_status']=='approved';ctx.close()
   state['sold']=True;state['event']['starts_at']='2026-10-01T10:00:00+01:00';state['event']['ends_at']='2026-10-01T12:00:00+01:00'
   ctx,page=open_page('event_organizer',OWNER,url);expect(page.get_by_text('Available to request',exact=True).locator('..')).to_contain_text('₦1,500.00');expect(page.get_by_role('button',name='Approve and publish',exact=True)).to_have_count(0)
   page.get_by_role('button',name='Venue QR',exact=True).click();page.get_by_role('button',name='Generate QR',exact=True).click();qr=page.get_by_role('dialog',name='Venue QR',exact=True);expect(qr.get_by_alt_text('Venue check-in QR code',exact=True)).to_be_visible();assert qr.get_by_alt_text('Venue check-in QR code',exact=True).evaluate('(img)=>img.complete&&img.naturalWidth>0');qr.get_by_role('button',name='Close dialog',exact=True).click()
   page.get_by_label('Find attendee',exact=True).fill('guest@example.invalid');expect(page.get_by_text('=Guest attendee',exact=True)).to_be_visible();page.get_by_role('button',name='Check in attendee',exact=True).click();expect(page.get_by_role('alert').filter(has_text='Controlled committed admission response loss')).to_be_visible()
   page.get_by_role('button',name='Check in attendee',exact=True).click();expect(page.get_by_role('status').filter(has_text='already checked in')).to_be_visible();admissions=[body for kind,body in writes if kind=='checkin'];assert len(admissions)==2 and admissions[0]==admissions[1]
   with page.expect_download() as download:page.get_by_role('button',name='Export attendees',exact=True).click()
   assert "'=Guest attendee" in Path(download.value.path()).read_text()
   page.get_by_label('Bank name',exact=True).fill('Controlled bank');page.get_by_label('Account holder name',exact=True).fill('Controlled owner');page.get_by_label('Account number',exact=True).fill('0123456789');page.get_by_role('button',name='Request available payout',exact=True).click();expect(page.get_by_role('alert').filter(has_text='Controlled committed payout response loss')).to_be_visible()
   page.get_by_role('button',name='Request available payout',exact=True).click();expect(page.get_by_text('Pending approval',exact=True)).to_be_visible();requests=[body for kind,body in writes if kind=='request'];assert len(requests)==2 and requests[0]==requests[1];ctx.close()
   ctx,page=open_page('admin',ADMIN,url);page.get_by_role('button',name='Approve payout',exact=True).click();page.get_by_label('Completed bank transfer reference',exact=True).fill('CONTROLLED-BANK-TRANSFER');page.get_by_role('button',name='Record completed transfer',exact=True).click();page.get_by_role('button',name='Record completed transfer',exact=True).last.click();expect(page.get_by_text('Transfer reference: CONTROLLED-BANK-TRANSFER',exact=True)).to_be_visible();assert state['requests'][0]['state']=='paid';ctx.close()
   ctx,page=open_page('event_organizer',OWNER,url);expect(page.get_by_text('Paid out',exact=True).locator('..')).to_contain_text('₦1,500.00');expect(page.get_by_text('Available to request',exact=True).locator('..')).to_contain_text('₦0.00');expect(page.get_by_role('link',name='View student page',exact=True)).to_be_visible();assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth');page.screenshot(path=f'/workspace/work/organizer-{width}.png',full_page=True);page.get_by_role('link',name='View student page',exact=True).click();expect(page).to_have_url('http://127.0.0.1:5270/');page.get_by_role('link',name='Open Event Organizer panel',exact=True).click();expect(page).to_have_url('http://127.0.0.1:5270/event-manager');expect(page.get_by_text('Organizer settlement',exact=True)).to_be_visible();ctx.close()
   before=len(private_reads);ctx,page=open_page('student',OWNER,url);expect(page.get_by_text('This workspace is for approved event organizers and administrators.',exact=True)).to_be_visible();assert len(private_reads)==before;ctx.close()
   ctx,page=open_page('event_organizer','66666666-6666-4666-8666-666666666666',url);expect(page.get_by_role('alert').filter(has_text='Controlled ownership denial').first).to_be_visible();expect(page.get_by_text('Organizer settlement',exact=True)).to_have_count(0);ctx.close()
   assert not errors,errors;print(f'PASS width={width}: organizer draft/response-loss replay/submission, admin terms/publication, private earnings, venue QR, attendee search/admission replay/CSV, payout request replay/approval/recording, role/ownership gates and student-page navigation')
  browser.close()
finally:
 os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
