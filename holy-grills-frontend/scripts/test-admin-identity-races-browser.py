"""Native stale role/access and pending submission controls; controlled accounts."""
import json,os
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('HG_BROWSER_BASE','http://127.0.0.1:4185');C='70000001-cafe-cafe-cafe-000000000001';A='11111111-1111-4111-8111-111111111111';U='22222222-2222-4222-8222-222222222222';M='33333333-3333-4333-8333-333333333333';ERROR='This account changed. Refresh the directory before changing its role or access.'
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for width in (393,1280):
  state={'rows':[{'id':U,'full_name':'Fixture student','role':'student','campus_id':C,'is_active':True},{'id':M,'full_name':'Fixture manager','role':'community_manager','campus_id':C,'is_active':False}],'writes':[],'held':[]};errors=[]
  ctx=browser.new_context(viewport={'width':width,'height':1000});ctx.add_init_script(f"localStorage.setItem('hg_access_token','synthetic');localStorage.setItem('hg_user_role','admin');localStorage.setItem('hg_campus_id','{C}');localStorage.setItem('hg_user_campus_id','{C}');localStorage.setItem('hg_cookie_consent',JSON.stringify({{essential:true,analytics:false,date:new Date().toISOString()}}));")
  def api(route):
   req=route.request;path=urlparse(req.url).path;data={}
   if path.endswith('/auth/me'):data={'id':A,'full_name':'Audit admin','role':'admin','campus_id':C}
   elif path.endswith('/campuses'):data={'campuses':[{'id':C,'name':'FUTA','slug':'futa','is_active':True}]}
   elif path.endswith('/admin/users'):data=state['rows']
   elif '/admin/users/' in path:
    body=req.post_data_json;state['writes'].append((path,body));row=next(r for r in state['rows'] if r['id']==path.split('/')[-2])
    assert body['expected_campus_id']==C
    if path.endswith('/role') and len(state['writes'])==1:
     assert body['expected_role']=='student' and body['expected_is_active'] is True;row['role']='kitchen';state['held'].append(route);return
    assert body['expected_role']==row['role'] and body['expected_is_active']==row['is_active']
    if path.endswith('/role'):row['role']=body['role']
    elif path.endswith('/activate'):row['is_active']=True
    elif path.endswith('/deactivate'):
     state['held'].append(route);return
    data=row
   elif '/notifications' in path:data={'notifications':[]}
   else:data=[]
   route.fulfill(status=200,json=data)
  ctx.route('**/api/**',api);ctx.route('https://*.onesignal.com/**',lambda r:r.abort())
  page=ctx.new_page();page.set_default_timeout(15000);page.on('pageerror',lambda e:errors.append(str(e)));page.goto(BASE+'/admin?section=users',wait_until='domcontentloaded',timeout=30000);roles=page.get_by_title('Change role',exact=True);expect(roles.first).to_be_enabled();roles.first.select_option('rider');expect(roles.first).to_be_disabled();expect(page.get_by_role('button',name='Refresh directory',exact=True)).to_be_disabled();assert len(state['writes'])==1
  state['held'][0].fulfill(status=409,json={'error':ERROR});expect(page.get_by_text(ERROR,exact=True)).to_be_visible();page.get_by_role('button',name='Refresh directory',exact=True).click();expect(roles.first).to_have_value('kitchen');roles.first.select_option('rider');expect(roles.first).to_have_value('rider');assert state['writes'][-1][1]['expected_role']=='kitchen'
  page.get_by_title('Reactivate account',exact=True).click();expect(page.get_by_title('Reactivate account',exact=True)).to_have_count(0);assert state['rows'][1]['is_active'] is True;expect(roles.nth(1)).to_be_disabled()
  page.get_by_title('Deactivate account',exact=True).last.click();dialog=page.get_by_role('dialog',name='Deactivate account?',exact=True);dialog.get_by_role('button',name='Deactivate',exact=True).click();expect(dialog.get_by_role('button',name='Cancel',exact=True)).to_be_disabled();expect(dialog.get_by_role('button',name='Deactivate',exact=True)).to_be_disabled();assert len(state['writes'])==4
  state['rows'][1]['is_active']=False;state['held'][-1].fulfill(status=200,json={'message':'Fixture account deactivated'});expect(dialog).not_to_be_visible();expect(page.get_by_title('Reactivate account',exact=True)).to_be_visible();assert state['writes'][-1][1]['expected_role']=='community_manager' and state['writes'][-1][1]['expected_is_active'] is True
  assert not errors,errors
  print(json.dumps({'width':width,'passed':True,'production_writes':0}),flush=True);ctx.close()
 browser.close()
