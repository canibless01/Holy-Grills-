"""Native consent boundary and redacted route tracking; all API calls are local fixtures."""
import os,json
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('HG_BROWSER_BASE','http://127.0.0.1:4187');C='70000001-cafe-cafe-cafe-000000000001';U='11111111-1111-4111-8111-111111111111'
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
 for role,consent in [(None,False),(None,True),('student',True),('super_admin',True)]:
  views=[];errors=[];ctx=browser.new_context(viewport={'width':393,'height':950},service_workers='block')
  setup=f"localStorage.setItem('hg_campus_id','{C}');localStorage.setItem('hg_cookie_consent',JSON.stringify({{essential:true,analytics:{str(consent).lower()}}}));"
  if role:setup+=f"localStorage.setItem('hg_access_token','synthetic');localStorage.setItem('hg_user_role','{role}');localStorage.setItem('hg_user_campus_id','{C}');"
  ctx.add_init_script(setup)
  def api(route):
   req=route.request;path=urlparse(req.url).path;data={}
   if path.endswith('/auth/me'):
    if not role:route.fulfill(status=401,json={'error':'guest'});return
    data={'id':U,'full_name':'Local user','role':role,'campus_id':C,'created_at':'2026-11-25T00:00:00Z'}
   elif path.endswith('/campuses'):data={'campuses':[{'id':C,'name':'FUTA','slug':'futa','is_active':True,'is_default':True}]}
   elif path.endswith('/menu/items'):data={'items':[],'kitchen':{}}
   elif path.endswith('/menu/categories'):data=[]
   elif path.endswith('/engagement/page-view'):views.append({'body':req.post_data_json,'authorization':req.headers.get('authorization')});data={'accepted':True}
   elif path.endswith('/notifications'):data={'notifications':[]}
   route.fulfill(status=200,json=data)
  ctx.route('**/api/**',api);ctx.route('https://*.onesignal.com/**',lambda r:r.abort());page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto(BASE+'/menu?claim_token=DO_NOT_STORE',wait_until='domcontentloaded');page.wait_for_timeout(1600)
  if consent and role!='super_admin':
   assert len(views)==1,views;body=views[0]['body'];assert body['path']=='/menu' and 'DO_NOT_STORE' not in str(body);assert body['visitor_id'] and body['id'];assert ('user_id' not in body)
   assert views[0]['authorization']==('Bearer synthetic' if role else None)
  else:assert not views,views
  assert not errors,errors
  print(json.dumps({'role':role or 'guest','analytics_consent':consent,'recorded':len(views),'passed':True}),flush=True);ctx.close()
 browser.close()
