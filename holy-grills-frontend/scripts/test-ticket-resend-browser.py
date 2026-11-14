"""Native ticket resend proof: guests, owners and staff; response-loss retry."""
import os,signal,subprocess,tempfile,time
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
repo=Path(__file__).resolve().parents[1];out=Path(tempfile.mkdtemp(prefix='hg-ticket-resend-'));E='11111111-1111-4111-8111-111111111111';T='22222222-2222-4222-8222-222222222222';C='33333333-3333-4333-8333-333333333333'
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5283','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
try:
 time.sleep(2)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  for width in (393,1280):
   for role in ('super_admin','student','guest'):
    writes=[];errors=[]
    event={'id':E,'slug':E,'title':'Resend event','is_published':True,'starts_at':'2027-12-01T10:00:00Z','ends_at':'2027-12-01T12:00:00Z','campus_id':C,'hp_reward':50,'is_free':True,'location':'Hall'}
    def api(route):
     path=urlparse(route.request.url).path;data={}
     if path.endswith('/auth/me'):data={'id':C,'role':role,'campus_id':C,'is_active':True,'profile':{'role':role,'campus_id':C}}
     elif path.endswith('/campuses'):data=[{'id':C,'name':'FUTA','is_active':True}]
     elif path.endswith('/feature-flags'):data=[{'feature_name':'events','is_active':True}]
     elif path.endswith('/events/admin'):data={'events':[event]}
     elif path.endswith('/events/'+E):data=event
     elif path.endswith('/events/my-tickets'):data={'upcoming':[{'ticket_id':T,'event_id':E,'payment_status':'not_required','status':'confirmed','checked_in':False}]}
     elif path.endswith('/registrants'):data={'registrants':[{'ticket_id':T,'full_name':'Verified guest','email':'guest@example.invalid','status':'confirmed','payment_status':'not_required','checked_in':False}]}
     elif path.endswith('/tiers'):data=[]
     elif path.endswith('/qr'):data={'ticket_id':T,'status':'confirmed','payment_status':'not_required','qr_image':'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jD1sAAAAASUVORK5CYII='}
     elif path.endswith('/resend'):
      writes.append(route.request.post_data_json)
      if len(writes)==1:route.fulfill(status=503,json={'error':'Controlled committed response loss'});return
      assert writes[0]==writes[1]
      if role=='guest':assert writes[-1].get('access_token')=='controlled-proof'
      data={'delivery_id':writes[-1]['request_id'],'state':'accepted','replayed':True}
     route.fulfill(json=data)
    ctx=browser.new_context(viewport={'width':width,'height':1000});ctx.route('**/api/**',api)
    init="localStorage.setItem('hg_cookie_consent',JSON.stringify({essential:true,analytics:false,date:new Date().toISOString()}));localStorage.setItem('hg_user_campus_id','"+C+"');localStorage.setItem('hg_admin_campus_id','"+C+"');"
    if role!='guest':init+="sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_role','"+role+"');"
    ctx.add_init_script(init);page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
    if role=='super_admin':page.goto('http://127.0.0.1:5283/admin?section=events');page.get_by_role('button',name='Registrants',exact=True).click()
    else:page.goto('http://127.0.0.1:5283/events/'+E+('#ticket='+T+'&access=controlled-proof' if role=='guest' else ''))
    if role=='guest':page.get_by_role('button',name='FUTA',exact=True).click()
    button=page.get_by_role('button',name='Resend ticket email',exact=True);expect(button).to_be_visible();button.evaluate('(b)=>{b.click();b.click()}');expect(page.get_by_text('Controlled committed response loss',exact=True)).to_be_visible();assert len(writes)==1
    button.click();expect(page.get_by_text('Ticket email requested. Check your inbox and spam folder.',exact=True)).to_be_visible();expect(button).to_be_disabled();assert len(writes)==2;assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');assert not errors,errors;ctx.close();print(f'PASS {width} {role}: resend duplicate suppression, stable retry, truthful requested status',flush=True)
  browser.close()
finally:os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
