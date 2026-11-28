"""Remaining A5 native editor fields, pending writes and recovery. Controlled HTTP only."""
import json,os,signal,subprocess,tempfile,time
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1];C='11111111-1111-4111-8111-111111111111'
out=Path(tempfile.mkdtemp(prefix='hg-final-editors-'))
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5220','--strictPort'],cwd=ROOT,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
try:
 time.sleep(2)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  for width in (393,1280):
   state={'fail_read':False,'hold':False,'held':[],'writes':[],'sides':[],'milestones':[],'welcome':{'enabled':True,'credits':1,'validity_days':60}}
   ctx=browser.new_context(viewport={'width':width,'height':1000})
   ctx.add_init_script(f"sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_campus_id','{C}');localStorage.setItem('hg_user_campus_id','{C}');localStorage.setItem('hg_admin_campus_id','{C}');localStorage.setItem('hg_cookie_consent',JSON.stringify({{essential:true,analytics:false,date:new Date().toISOString()}}));")
   def api(route):
    req=route.request;path=urlparse(req.url).path;data=[]
    if path.endswith('/auth/me'):data={'id':'controlled-admin','role':'super_admin','campus_id':C,'full_name':'Controlled admin'}
    elif path.endswith('/campuses'):data=[{'id':C,'name':'Controlled campus','is_active':True}]
    elif '/free-sides/admin/items' in path:
     if req.method!='GET':
      body=req.post_data_json;state['writes'].append((path,body))
      if state['hold']:state['held'].append(route);return
      row={**body,'id':'controlled-side','updated_at':'stamp-1'};state['sides']=[row];data=row
     elif state['fail_read']:route.fulfill(status=503,json={'error':'Controlled free-side failure'});return
     else:data={'items':state['sides'],'validity_days':60}
    elif '/challenges/admin' in path:
     if req.method!='GET':
      body=req.post_data_json;state['writes'].append((path,body))
      if state['hold']:state['held'].append(route);return
      row={**body,'id':'controlled-challenge'};state['milestones']=[row];data=row
     elif state['fail_read']:route.fulfill(status=503,json={'error':'Controlled milestone failure'});return
     else:data={'milestones':state['milestones']}
    elif path.endswith('/admin/welcome-credit'):
     if req.method!='GET':
      body=req.post_data_json;state['writes'].append((path,body))
      if state['hold']:state['held'].append(route);return
      state['welcome']=body['config']
     elif state['fail_read']:route.fulfill(status=503,json={'error':'Controlled welcome failure'});return
     data={'config':state['welcome'],'inherited':True}
    elif path.endswith('/menu/items'):
     data={'items':[{'id':'controlled-menu','campus_id':C,'name':'Controlled meal','price':3500,'cushion_amount':500,'category_id':'controlled-category','hp_earn_value':10,'hp_multiplier':1,'daily_limit':50,'is_available':True}]}
    elif path.endswith('/menu/categories'):data={'categories':[{'id':'controlled-category','name':'Controlled category'}]}
    elif path.endswith('/menu/items/controlled-menu'):
     if req.method=='PATCH':state['writes'].append((path,req.post_data_json));data=req.post_data_json
     else:data={'variation_groups':[]}
    route.fulfill(status=200,json=data)
   ctx.route('**/api/**',api);ctx.route('https://*.onesignal.com/**',lambda r:r.abort())
   page=ctx.new_page();page.set_default_timeout(15000);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   # Milestone editor: all visible inputs + every trigger/window option are native selects.
   state['fail_read']=True;page.goto('http://127.0.0.1:5220/admin?section=challenges')
   expect(page.get_by_role('alert')).to_contain_text('Challenges could not be loaded');state['fail_read']=False;page.get_by_role('button',name='Retry',exact=True).click()
   page.get_by_role('button',name='New Milestone',exact=True).click();page.get_by_label('Title',exact=True).fill('Controlled milestone');page.get_by_label('Description',exact=True).fill('Controlled description')
   triggers=page.get_by_label('Trigger type',exact=True)
   for v in triggers.locator('option').evaluate_all('(o)=>o.map(x=>x.value)'):triggers.select_option(v);expect(page.get_by_label('Trigger value (target count)',exact=True)).to_have_value('1')
   triggers.select_option('order_count');page.get_by_label('Trigger value (target count)',exact=True).fill('5');page.get_by_label('HP awarded',exact=True).fill('75')
   windows=page.get_by_label('Time window',exact=True)
   for v in windows.locator('option').evaluate_all('(o)=>o.map(x=>x.value)'):windows.select_option(v)
   windows.select_option('weekly');page.get_by_role('switch',name='Active',exact=True).click()
   state['hold']=True;before=len(state['writes']);page.get_by_role('button',name='Save Milestone',exact=True).evaluate('(b)=>{b.click();b.click();}')
   expect(page.get_by_label('Title',exact=True)).to_be_disabled();page.get_by_role('button',name='Close dialog',exact=True).click();expect(page.get_by_role('dialog')).to_be_visible();page.wait_for_timeout(100);assert len(state['writes'])==before+1
   state['held'].pop().fulfill(status=503,json={'error':'Controlled milestone save failure'});expect(page.get_by_role('button',name='Save Milestone',exact=True)).to_be_enabled();expect(page.get_by_label('Title',exact=True)).to_have_value('Controlled milestone')
   state['hold']=False;page.get_by_role('button',name='Save Milestone',exact=True).click();expect(page.get_by_role('dialog')).to_have_count(0)
   body=state['writes'][-1][1];assert (body['trigger_value'],body['hp_awarded'],body['time_window'],body['is_active'])==(5,75,'weekly',True)
   page.get_by_role('button',name='Edit milestone',exact=True).click();expect(page.get_by_label('HP awarded',exact=True)).to_have_value('75');page.get_by_role('button',name='Close dialog',exact=True).click()
   # Free-side editor: stable create intent survives failure; update carries expected version.
   state['fail_read']=True;page.goto('http://127.0.0.1:5220/admin?section=freecredits');expect(page.get_by_role('alert')).to_contain_text('Controlled free-side failure');state['fail_read']=False;page.get_by_role('button',name='Retry',exact=True).click()
   page.get_by_role('button',name='Add side',exact=True).click();page.get_by_label('Name',exact=True).fill('Controlled slaw')
   state['hold']=True;before=len(state['writes']);page.get_by_role('button',name='Save side',exact=True).evaluate('(b)=>{b.click();b.click();}')
   expect(page.get_by_label('Name',exact=True)).to_be_disabled();page.get_by_role('button',name='Close dialog',exact=True).click();expect(page.get_by_role('dialog')).to_be_visible();page.wait_for_timeout(100);assert len(state['writes'])==before+1;intent=state['writes'][-1][1]['intent_key']
   state['held'].pop().fulfill(status=503,json={'error':'Controlled side save failure'});expect(page.get_by_role('button',name='Save side',exact=True)).to_be_enabled();expect(page.get_by_label('Name',exact=True)).to_have_value('Controlled slaw')
   state['hold']=False;page.get_by_role('button',name='Save side',exact=True).click();expect(page.get_by_role('dialog')).to_have_count(0);assert state['writes'][-1][1]['intent_key']==intent
   page.get_by_role('button',name='Edit Controlled slaw',exact=True).click();page.get_by_role('dialog').get_by_role('switch').click();page.get_by_role('button',name='Save side',exact=True).click();expect(page.get_by_role('dialog')).to_have_count(0)
   body=state['writes'][-1][1];assert body['is_active'] is False and body['expected_updated_at']=='stamp-1'
   # Onboarding: scope, inherited settings, invalid bounds and failure recovery.
   state['fail_read']=True;page.goto('http://127.0.0.1:5220/admin?section=onboarding');expect(page.get_by_text("We couldn't load this page. Please try again.",exact=True)).to_be_visible();state['fail_read']=False;page.get_by_role('button',name='Retry',exact=True).click()
   expect(page.get_by_text('Using global defaults',exact=True).first).to_be_visible();page.get_by_label('Credits per account',exact=True).first.fill('0');expect(page.get_by_role('button',name='Save welcome credits',exact=True)).to_be_disabled()
   page.get_by_label('Credits per account',exact=True).first.fill('2');page.get_by_label('Validity in days',exact=True).first.fill('366');expect(page.get_by_role('button',name='Save welcome credits',exact=True)).to_be_disabled();page.get_by_label('Validity in days',exact=True).first.fill('30');page.get_by_role('switch',name='Enable signup free-side credits',exact=True).click()
   state['hold']=True;before=len(state['writes']);page.get_by_role('button',name='Save welcome credits',exact=True).evaluate('(b)=>{b.click();b.click();}');expect(page.get_by_label('Credits per account',exact=True).first).to_be_disabled();page.wait_for_timeout(100);assert len(state['writes'])==before+1
   state['held'].pop().fulfill(status=503,json={'error':'Controlled welcome save failure'});expect(page.get_by_role('button',name='Save welcome credits',exact=True)).to_be_enabled();expect(page.get_by_label('Credits per account',exact=True).first).to_have_value('2')
   state['hold']=False;page.get_by_role('button',name='Save welcome credits',exact=True).click();expect(page.get_by_role('button',name='Save welcome credits',exact=True)).to_be_enabled();assert state['writes'][-1][1]=={'campus_id':C,'config':{'enabled':False,'credits':2,'validity_days':30}}
   # Menu scalar fields retain exact numbers (cushion is included, never added).
   page.goto('http://127.0.0.1:5220/admin?section=menu');page.get_by_role('button',name='Edit Controlled meal',exact=True).click()
   page.get_by_label('Name',exact=True).fill('Controlled edited meal');page.get_by_label('Price (₦)',exact=True).fill('4000');page.get_by_label('Delivery cushion included (₦)',exact=True).fill('600');page.get_by_label('Category',exact=True).select_option('controlled-category');page.get_by_label('Daily Limit',exact=True).fill('');page.get_by_label('HP Earn Value',exact=True).fill('0');page.get_by_label('HP Multiplier',exact=True).select_option('0.5');page.get_by_label('Description',exact=True).fill('Controlled edited description');page.get_by_role('switch',name='Featured',exact=True).click();page.get_by_role('switch',name='Hidden — only found by search',exact=True).click();page.get_by_role('button',name='Save Changes',exact=True).click();expect(page.get_by_role('dialog')).to_have_count(0)
   body=state['writes'][-1][1];assert (body['price'],body['cushion_amount'],body['daily_limit'],body['hp_earn_value'],body['hp_multiplier'],body['is_featured'],body['is_secret'])==(4000,600,None,0,.5,True,True)
   assert not errors,errors
   print(json.dumps({'width':width,'challenge_fields_and_options':True,'free_side_intent_version_and_fields':True,'welcome_bounds_scope_recovery':True,'menu_scalar_fields':True,'pending_duplicate_dismissal_guards':True,'real_writes':0}),flush=True);ctx.close()
  browser.close()
finally:os.killpg(proc.pid,signal.SIGTERM)
