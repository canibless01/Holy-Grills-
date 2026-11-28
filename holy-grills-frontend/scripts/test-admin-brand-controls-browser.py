"""Native brand JSON, intent recovery and stale status controls; no production writes."""
import json,os
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('HG_BROWSER_BASE','http://127.0.0.1:4185')
C='70000001-cafe-cafe-cafe-000000000001';U='11111111-1111-4111-8111-111111111111'
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for width in (393,1280):
  state={'rows':[],'creates':[],'held':[],'patches':[],'conflict':True};errors=[]
  ctx=browser.new_context(viewport={'width':width,'height':1000});ctx.add_init_script(f"localStorage.setItem('hg_access_token','synthetic');localStorage.setItem('hg_user_role','admin');localStorage.setItem('hg_campus_id','{C}');localStorage.setItem('hg_user_campus_id','{C}');localStorage.setItem('hg_cookie_consent',JSON.stringify({{essential:true,analytics:false,date:new Date().toISOString()}}));")
  def api(route):
   req=route.request;path=urlparse(req.url).path;data={}
   if path.endswith('/auth/me'):data={'id':U,'full_name':'Audit admin','role':'admin','campus_id':C}
   elif path.endswith('/campuses'):data={'campuses':[{'id':C,'name':'FUTA','slug':'futa','is_active':True}]}
   elif path.endswith('/analytics/brand-partnerships'):
    if req.method=='POST':
     body=req.post_data_json;state['creates'].append(body);row=next((r for r in state['rows'] if r['id']==body['request_id']),None)
     if row is None:row={**body,'id':body['request_id'],'status':'pending'};state['rows'].append(row)
     if len(state['creates'])==1:state['held'].append(route);return
     data=row
    else:data={'brand_partnerships':state['rows']}
   elif '/analytics/brand-partnerships/' in path:
    body=req.post_data_json;state['patches'].append(body);row=next(r for r in state['rows'] if r['id']==path.rsplit('/',1)[-1]);assert body['expected_status']=='pending'
    if state['conflict']:
     state['conflict']=False;row['status']='approved';route.fulfill(status=409,json={'error':'This brand request changed. Reload the requests before changing its status.'});return
    row['status']=body['status'];data=row
   elif path.endswith('/analytics/items'):data=[]
   elif '/notifications' in path:data={'notifications':[]}
   elif '/analytics/' in path:data={}
   else:data=[]
   route.fulfill(status=200,json=data)
  ctx.route('**/api/**',api);ctx.route('https://*.onesignal.com/**',lambda r:r.abort())
  page=ctx.new_page();page.set_default_timeout(15000);page.on('pageerror',lambda e:(errors.append(str(e)),print('PAGE ERROR',str(e),flush=True)));page.goto(BASE+'/admin?section=analytics',wait_until='domcontentloaded',timeout=30000);
  try:page.get_by_role('button',name='Customers & Engagement',exact=True).click(timeout=30000)
  except Exception:
   print(page.locator('body').inner_text(),flush=True);raise
  expect(page.get_by_text('No brand partnership requests yet',exact=True)).to_be_visible()
  page.get_by_role('button',name='Log request',exact=True).click();d=page.get_by_role('dialog',name='Log Brand Partnership Request');d.get_by_label('Brand name',exact=True).fill('Campus partner');d.get_by_label('Contact email',exact=True).fill('bad');d.get_by_role('button',name='Log request',exact=True).click();assert not state['creates']
  d.get_by_label('Contact email',exact=True).fill('info@example.com');j=d.get_by_label('Requested data (JSON)',exact=True);j.fill('{');d.get_by_role('button',name='Log request',exact=True).click();expect(d.get_by_role('alert')).to_contain_text('Enter a valid JSON object');expect(j).to_have_value('{');assert not state['creates']
  j.fill('[1,2]');d.get_by_role('button',name='Log request',exact=True).click();expect(d.get_by_role('alert')).to_be_visible();assert not state['creates']
  j.fill('{"sales_summary": true, "notes": "Two paragraphs\\nkept"}');d.get_by_role('button',name='Log request',exact=True).click();expect(d.get_by_role('button',name='Cancel',exact=True)).to_be_disabled();expect(j).to_be_disabled();d.evaluate('(form)=>form.requestSubmit()');assert len(state['creates'])==1
  state['held'][0].fulfill(status=503,json={'error':'Controlled response loss'});expect(page.get_by_text('Controlled response loss',exact=True)).to_be_visible();expect(j).to_be_enabled();d.get_by_role('button',name='Log request',exact=True).click();expect(d).not_to_be_visible();expect(page.get_by_text('Campus partner',exact=True)).to_be_visible();assert len(state['rows'])==1 and state['creates'][0]==state['creates'][1] and state['creates'][1]['requested_data']['sales_summary'] is True
  page.get_by_role('button',name='Reject',exact=True).click();expect(page.get_by_text('This brand request changed. Reload the requests before changing its status.',exact=True)).to_be_visible();page.get_by_role('button',name='Refresh requests',exact=True).click();expect(page.get_by_text('approved',exact=True)).to_be_visible();assert not page.get_by_role('button',name='Reject',exact=True).count()
  page.get_by_role('button',name='Log request',exact=True).click();d=page.get_by_role('dialog');d.get_by_label('Brand name',exact=True).fill('Second partner');d.get_by_label('Contact email',exact=True).fill('second@example.com');d.get_by_role('button',name='Log request',exact=True).click();expect(d).not_to_be_visible();assert state['creates'][-1]['request_id']!=state['creates'][0]['request_id'];page.get_by_role('button',name='Reject',exact=True).click();expect(page.get_by_text('rejected',exact=True)).to_be_visible();assert len(state['patches'])==2 and len(state['rows'])==2
  assert not errors,errors
  print(json.dumps({'width':width,'passed':True,'production_writes':0}),flush=True);ctx.close()
 browser.close()
