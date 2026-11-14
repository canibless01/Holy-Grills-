"""Native legacy attendance HP review and earned snapshot presentation."""
import os,signal,subprocess,tempfile,time
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
repo=Path(__file__).resolve().parents[1];out=Path(tempfile.mkdtemp(prefix='hg-guest-hp-'));E='11111111-1111-4111-8111-111111111111';T='22222222-2222-4222-8222-222222222222';C='33333333-3333-4333-8333-333333333333'
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5282','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
try:
 time.sleep(2)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  for width in (393,1280):
   state={'done':False,'lost':True};writes=[];errors=[]
   event={'id':E,'title':'Guest HP event','is_published':True,'starts_at':'2027-12-01T10:00:00Z','ends_at':'2027-12-01T12:00:00Z','campus_id':C,'hp_reward':500}
   def api(route):
    path=urlparse(route.request.url).path;data={}
    if path.endswith('/auth/me'):data={'id':C,'role':'super_admin','campus_id':C,'is_active':True,'profile':{'role':'super_admin','campus_id':C}}
    elif path.endswith('/campuses'):data=[{'id':C,'name':'FUTA','is_active':True}]
    elif path.endswith('/feature-flags'):data=[{'feature_name':'events','is_active':True}]
    elif path.endswith('/events/admin'):data={'events':[event]}
    elif path.endswith('/events'):data=[event]
    elif path.endswith('/events/my-tickets'):data={'checked_in':[{'ticket_id':T,'event_id':E,'event_title':event['title'],'payment_status':'not_required','status':'confirmed','checked_in':True,'hp_claim_status':'completed' if state['done'] else 'review_required','hp_earned':50 if state['done'] else 0}]}
    elif path.endswith('/registrants'):data={'registrants':[{'ticket_id':T,'full_name':'Verified guest','email':'guest@example.invalid','status':'confirmed','payment_status':'not_required','checked_in':True,'hp_claim_status':'completed' if state['done'] else 'review_required'}]}
    elif path.endswith('/attendance-hp'):
     writes.append(route.request.post_data_json);assert writes[-1]['amount']==50 and writes[-1]['reason']=='Verified original event reward'
     state['done']=True
     if state['lost']:state['lost']=False;route.fulfill(status=503,json={'error':'Controlled committed response loss'});return
     data={'completed':True,'replayed':True,'hp_added_to_active':50}
    route.fulfill(json=data)
   ctx=browser.new_context(viewport={'width':width,'height':1000});ctx.route('**/api/**',api);ctx.add_init_script("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_role','super_admin');localStorage.setItem('hg_user_campus_id','"+C+"');localStorage.setItem('hg_admin_campus_id','"+C+"');localStorage.setItem('hg_cookie_consent',JSON.stringify({essential:true,analytics:false,date:new Date().toISOString()}));")
   page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto('http://127.0.0.1:5282/admin?section=events');page.get_by_role('button',name='Registrants',exact=True).click();page.get_by_role('button',name='Review attendance HP',exact=True).click();form=page.get_by_role('dialog',name='Review attendance HP',exact=True)
   expect(form.get_by_role('button',name='Confirm attendance HP',exact=True)).to_be_disabled();form.get_by_label('Verified HP amount',exact=True).fill('50');form.get_by_label('Review reason',exact=True).fill('Verified original event reward');form.get_by_role('button',name='Confirm attendance HP',exact=True).evaluate('(b)=>{b.click();b.click()}');expect(form.get_by_role('alert')).to_contain_text('Controlled committed response loss');assert len(writes)==1
   form.get_by_role('button',name='Confirm attendance HP',exact=True).click();expect(form).to_have_count(0);assert writes[0]==writes[1];expect(page.get_by_role('button',name='Review attendance HP',exact=True)).to_have_count(0)
   page.goto('http://127.0.0.1:5282/events');page.get_by_role('button',name='My Events',exact=True).click();expect(page.get_by_text('✓ Checked in · +50 HP',exact=True)).to_be_visible();expect(page.get_by_text('✓ Checked in · +500 HP',exact=True)).to_have_count(0)
   state['done']=False;page.reload();page.get_by_role('button',name='My Events',exact=True).click();expect(page.get_by_text('Your attendance HP is awaiting support review.',exact=True)).to_be_visible();assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');assert not errors,errors;ctx.close();print(f'PASS {width}: admin reason/amount, committed-response replay, and attendee earned HP snapshot/review status',flush=True)
  browser.close()
finally:os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
