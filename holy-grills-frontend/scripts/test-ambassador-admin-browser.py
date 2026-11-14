"""Native roster/milestone controls with controlled API failures; no production writes."""
import json,os,re
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('HG_BROWSER_BASE','http://127.0.0.1:4185')
C='70000001-cafe-cafe-cafe-000000000001';U='11111111-1111-4111-8111-111111111111';M='22222222-2222-4222-8222-222222222222'
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for width,role in [(393,'admin'),(1280,'super_admin'),(393,'community_manager')]:
  ctx=browser.new_context(viewport={'width':width,'height':900});ctx.add_init_script(f"localStorage.setItem('hg_access_token','synthetic');localStorage.setItem('hg_campus_id','{C}');localStorage.setItem('hg_user_campus_id','{C}');localStorage.setItem('hg_user_role','{role}');")
  writes=[];rows=[];held=[];errors=[];failed_search=False
  def api(route):
   nonlocal_unused=None
   req=route.request;path=urlparse(req.url).path;data={}
   if path.endswith('/auth/me'):data={'id':U,'full_name':'Audit admin','role':role,'campus_id':C}
   elif path.endswith('/campuses'):data={'campuses':[{'id':C,'name':'FUTA','slug':'futa','is_active':True}]}
   elif path.endswith('/admin/users'):
    q=parse_qs(urlparse(req.url).query).get('q',[''])[0]
    if q=='old':held.append(route);return
    if q=='fail':route.fulfill(status=503,json={'error':'Controlled search failure'});return
    data={'users':[{'id':U,'full_name':'Latest person','email':'latest@example.invalid','is_active':True},{'id':M,'full_name':'Inactive person','is_active':False}]}
   elif path.endswith('/ambassadors/staff/ambassadors'):
    if req.method=='POST':writes.append(req.post_data_json);data={'ambassador':{'profile_id':U}}
    else:data={'ambassadors':[]}
   elif '/ambassadors/staff/milestones' in path:
    if req.method in ('POST','PATCH'):
     body=req.post_data_json;writes.append(body)
     if req.method=='POST' and len([w for w in writes if 'metric' in w])==1:route.fulfill(status=503,json={'error':'Controlled response loss'});return
     row={'id':M,'campus_id':None if body.get('global') else C,'updated_at':'2026-11-14T12:00:00Z',**body};rows[:]=[row];data={'milestone':row}
    else:data={'milestones':rows}
   elif '/notifications' in path:data={'notifications':[]}
   else:data=[]
   route.fulfill(status=200,json=data)
  ctx.route('**/api/**',api);ctx.route('https://*.onesignal.com/**',lambda r:r.abort())
  page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto(BASE+('/community-manager' if role=='community_manager' else '/admin')+'?section=ambassadors',wait_until='domcontentloaded')
  if page.get_by_role('button',name='Essential only').count():page.get_by_role('button',name='Essential only').click()
  expect(page.get_by_role('button',name='Performance milestones',exact=True)).to_be_visible(timeout=15000)
  if role!='community_manager':
   page.get_by_role('button',name='Add Ambassador tag',exact=True).click();d=page.get_by_role('dialog');search=d.get_by_role('textbox');search.fill('old')
   page.wait_for_timeout(400);search.fill('new');expect(d.get_by_text('Latest person',exact=True)).to_be_visible();assert not d.get_by_text('Inactive person',exact=True).count()
   for r in held:r.fulfill(status=200,json={'users':[{'id':M,'full_name':'Obsolete person'}]})
   page.wait_for_timeout(100);assert not d.get_by_text('Obsolete person').count()
   search.fill('fail');expect(d.get_by_role('alert')).to_be_visible();d.get_by_role('button',name='Retry',exact=True).click();expect(d.get_by_role('alert')).to_be_visible();search.fill('new');expect(d.get_by_text('Latest person',exact=True)).to_be_visible()
   d.get_by_role('button',name='Add Ambassador tag',exact=True).last.click();expect(d).not_to_be_visible();assert len(writes)==1
  page.get_by_role('button',name='Performance milestones',exact=True).click()
  if role=='community_manager':assert not page.get_by_role('button',name='New milestone',exact=True).count()
  else:
   page.get_by_role('button',name='New milestone',exact=True).click();d=page.get_by_role('dialog')
   if role=='admin':assert not d.get_by_label('Global (all campuses)',exact=True).count()
   else:expect(d.get_by_label('Global (all campuses)',exact=True)).to_be_checked()
   d.get_by_label('Amount / quantity',exact=True).fill('0');d.get_by_role('button',name='Save milestone',exact=True).click();assert len(writes)==1
   d.get_by_label('Amount / quantity',exact=True).fill('3500');d.get_by_role('button',name='Save milestone',exact=True).click();expect(page.get_by_text('Controlled response loss')).to_be_visible()
   d.get_by_role('button',name='Save milestone',exact=True).click();expect(d).not_to_be_visible();assert writes[-1]==writes[-2]
   expect(page.get_by_role('button',name='Edit milestone',exact=True)).to_be_visible();page.get_by_role('button',name='Edit milestone',exact=True).click();d=page.get_by_role('dialog');d.get_by_label('Milestone active',exact=True).uncheck();d.get_by_role('button',name='Save milestone',exact=True).click();expect(d).not_to_be_visible();expect(page.get_by_text('inactive',exact=True)).to_be_visible();assert writes[-1]['expected_updated_at']=='2026-11-14T12:00:00Z' and writes[-1]['is_active'] is False
  assert not errors,errors
  print(json.dumps({'width':width,'role':role,'passed':True}),flush=True);ctx.close()
 browser.close()
