"""Native customer ticket QR, guest recovery and unpaid/refund display checks."""
import os,signal,subprocess,tempfile,time,base64
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
repo=Path(__file__).resolve().parents[1];out=Path(tempfile.mkdtemp(prefix='hg-ticket-qr-'));E='11111111-1111-4111-8111-111111111111';T='22222222-2222-4222-8222-222222222222';U='33333333-3333-4333-8333-333333333333';C='44444444-4444-4444-8444-444444444444'
png='data:image/png;base64,'+base64.b64encode((repo/'scripts/fixtures/event-ticket-qr.png').read_bytes()).decode()
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5276','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
try:
 time.sleep(2)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  for width in (393,1280):
   state={'payment':'paid','cancelled':False,'fail_qr':True};qr_calls=[];errors=[]
   def api(route):
    r=route.request;path=urlparse(r.url).path;data={}
    if path.endswith('/auth/me'):data={'id':U,'role':'student','campus_id':C,'is_active':True,'profile':{'id':U,'role':'student','campus_id':C}}
    elif path.endswith('/campuses'):data=[{'id':C,'name':'FUTA','slug':'futa','is_active':True}]
    elif path.endswith('/feature-flags'):data=[{'feature_name':'events','is_active':True}]
    elif path=='/api/events/'+E:data={'id':E,'title':'Private QR event','starts_at':'2027-12-01T10:00:00Z','ends_at':'2027-12-01T12:00:00Z','is_paid':True,'is_published':True,'location':'FUTA hall','campus_id':C,'metadata':{'lifecycle_status':'cancelled','change_reason':'The host has cancelled the event.'} if state['cancelled'] else {}}
    elif path.endswith('/events/my-tickets'):data={'upcoming':[{'ticket_id':T,'event_id':E,'status':'pending_payment' if state['payment']=='pending' else 'confirmed','payment_status':state['payment'],'tier_name':'Regular'}]}
    elif path.endswith('/tiers'):data=[{'id':T,'name':'Regular','price_naira':100,'is_active':True}]
    elif path.endswith('/checkin'):
     assert r.post_data_json['ticket_id']==T;data={'completed':True,'is_guest':True,'hp_added_to_active':0}
    elif path.endswith('/tickets/verify'):data={'ticket_id':T,'payment_status':state['payment']}
    elif path.endswith('/qr'):
     qr_calls.append((r.post_data_json,r.headers))
     if state['fail_qr']:state['fail_qr']=False;route.fulfill(status=503,json={'error':'Controlled QR read unavailable'});return
     data={'qr_image':png,'qr_payload':f'hg-event:{E}:{T}'}
    route.fulfill(json=data)
   def open_context(logged=True,reference=False):
    ctx=browser.new_context(viewport={'width':width,'height':1000});ctx.route('**/api/**',api)
    script="localStorage.setItem('hg_campus_id','"+C+"');localStorage.setItem('hg_cookie_consent',JSON.stringify({essential:true,analytics:false,date:new Date().toISOString()}));"
    if logged:script+="sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_role','student');localStorage.setItem('hg_user_campus_id','"+C+"');"
    else:script+="sessionStorage.setItem('hg_event_guest_email','guest@example.invalid');"
    ctx.add_init_script(script);page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto('http://127.0.0.1:5276/events/'+E+('?reference=controlled-reference' if reference else ''));return ctx,page
   ctx,page=open_context();expect(page.get_by_text('Controlled QR read unavailable',exact=True)).to_be_visible();page.get_by_role('button',name='Retry ticket QR',exact=True).click();qr=page.get_by_alt_text('Your event ticket QR code',exact=True);expect(qr).to_be_visible();assert qr.evaluate('(img)=>img.complete&&img.naturalWidth>200');assert qr_calls[-1][0]=={} and qr_calls[-1][1].get('authorization')=='Bearer controlled';assert qr.get_attribute('src').startswith('data:image/png;base64,')
   expect(page.get_by_text('Free to attend. Register so we know you\'re coming, then scan the Holy Grill QR at the entrance to claim your HP.',exact=True)).to_have_count(0)
   page.screenshot(path=str(out/f'owned-ticket-{width}.png'),full_page=True)
   state['payment']='pending';before=len(qr_calls);page.reload();expect(page.get_by_role('button',name='Get Your Ticket',exact=True)).to_be_visible();expect(page.get_by_text('Ticket Confirmed',exact=True)).to_have_count(0);expect(page.get_by_alt_text('Your event ticket QR code',exact=True)).to_have_count(0);assert len(qr_calls)==before;ctx.close()
   state['payment']='paid';ctx,page=open_context(False,True);expect(page.get_by_alt_text('Your event ticket QR code',exact=True)).to_be_visible();assert qr_calls[-1][0]=={'guest_email':'guest@example.invalid'} and 'authorization' not in qr_calls[-1][1]
   page.get_by_role('button',name='Scan QR Code to Check In',exact=True).click();page.get_by_placeholder('token from the QR code',exact=True).fill('a'*32);page.get_by_role('button',name='Check In',exact=True).click();expect(page.get_by_text('Your attendance has been recorded.',exact=True).first).to_be_visible();ctx.close()
   state['payment']='refund_pending';state['cancelled']=True;before=len(qr_calls);ctx,page=open_context(False,True);expect(page.get_by_role('heading',name='Event cancelled',exact=True)).to_be_visible();expect(page.get_by_text('Ticket refund recorded',exact=True)).to_be_visible();expect(page.get_by_text('Your ticket is ready.',exact=True)).to_have_count(0);assert len(qr_calls)==before
   assert not errors,errors
   ctx.close();print(f'PASS {width}: real PNG decoded, owner/guest request identity, QR failure/Retry, no unpaid entry QR or false free/paid copy, refund return has no ready-ticket claim; screenshots={out}',flush=True)
  browser.close()
finally:os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
