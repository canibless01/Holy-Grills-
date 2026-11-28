"""Native catering paging/search/status and independent event failure. No writes."""
import json,os,re,uuid
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('HG_BROWSER_BASE','http://127.0.0.1:4185');C='70000001-cafe-cafe-cafe-000000000001';U='11111111-1111-4111-8111-111111111111'
ROWS=[{'id':str(uuid.UUID(int=i+1)),'campus_id':C,'organizer_name':'Outside first fifty' if i==55 else f'Organizer {i:02d}','email':f'fixture{i}@example.invalid','event_name':f'Event {i:02d}','event_date':'2026-12-01','expected_guests':10,'status':'quoted' if i%2 else 'new','quoted_amount':0 if i%2 else None,'updated_at':'2026-11-15T10:00:00Z'} for i in range(60)]
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for width in (393,1280):
  state={'reads':[],'fail':False,'event_reads':0};errors=[]
  ctx=browser.new_context(viewport={'width':width,'height':1000});ctx.add_init_script(f"localStorage.setItem('hg_access_token','synthetic');localStorage.setItem('hg_user_role','admin');localStorage.setItem('hg_campus_id','{C}');localStorage.setItem('hg_user_campus_id','{C}');localStorage.setItem('hg_cookie_consent',JSON.stringify({{essential:true,analytics:false,date:new Date().toISOString()}}));")
  def api(route):
   req=route.request;url=urlparse(req.url);path=url.path;q=parse_qs(url.query);data={}
   if path.endswith('/auth/me'):data={'id':U,'full_name':'Audit admin','role':'admin','campus_id':C}
   elif path.endswith('/campuses'):data={'campuses':[{'id':C,'name':'FUTA','slug':'futa','is_active':True}]}
   elif path.endswith('/events/catering-requests'):
    assert req.method=='GET';state['reads'].append(q)
    if state['fail']:route.fulfill(status=503,json={'error':'Controlled page failure'});return
    rows=ROWS;status=q.get('status',[''])[0];term=q.get('q',[''])[0].lower()
    if status:rows=[r for r in rows if r['status']==status]
    if term:rows=[r for r in rows if any(term in r[k].lower() for k in ('organizer_name','event_name','email'))]
    offset=int(q.get('offset',['0'])[0]);limit=int(q.get('limit',['25'])[0]);data={'requests':rows[offset:offset+limit]}
   elif path.endswith('/events/admin'):state['event_reads']+=1;route.fulfill(status=503,json={'error':'Controlled event outage'});return
   elif '/notifications' in path:data={'notifications':[]}
   else:data=[]
   route.fulfill(status=200,json=data)
  ctx.route('**/api/**',api);ctx.route('https://*.onesignal.com/**',lambda r:r.abort())
  page=ctx.new_page();page.set_default_timeout(15000);page.on('pageerror',lambda e:errors.append(str(e)));page.goto(BASE+'/admin?section=catering',wait_until='domcontentloaded',timeout=30000)
  expect(page.get_by_role('button').filter(has_text='Organizer 00')).to_be_visible();previous=page.get_by_role('button',name='Previous page',exact=True);next_button=page.get_by_role('button',name='Next page',exact=True);expect(previous).to_be_disabled();assert state['event_reads']==0
  next_button.click();expect(page.get_by_role('button').filter(has_text='Organizer 25')).to_be_visible();next_button.click();expect(page.get_by_role('button').filter(has_text='Outside first fifty')).to_be_visible();expect(next_button).to_be_disabled()
  search=page.get_by_label('Search catering requests',exact=True);search.fill('Outside first fifty');expect(page.get_by_text('Page 1',exact=True)).to_be_visible();expect(page.get_by_role('button').filter(has_text='Outside first fifty')).to_be_visible();assert state['reads'][-1]['offset']==['0'] and state['reads'][-1]['q']==['Outside first fifty'];expect(next_button).to_be_disabled()
  search.fill('');expect(page.get_by_role('button').filter(has_text='Organizer 00')).to_be_visible();page.get_by_role('button',name=re.compile('^quoted')).click();expect(page.get_by_role('button').filter(has_text='Organizer 01')).to_be_visible();assert state['reads'][-1]['status']==['quoted'];assert '₦0' in page.locator('body').inner_text()
  state['fail']=True;next_button.click();expect(page.get_by_role('alert')).to_be_visible();expect(search).to_be_visible();assert not page.get_by_text('No catering requests found.',exact=True).count();state['fail']=False;page.get_by_role('button',name='Retry',exact=True).click();expect(page.get_by_role('button').filter(has_text='Organizer 51')).to_be_visible();expect(next_button).to_be_disabled();assert state['reads'][-1]['offset']==['25']
  page.get_by_role('button',name=re.compile('^Event Catering')).click();expect(page.get_by_role('alert')).to_contain_text('Event catering could not be loaded. Catering requests are still available.');page.get_by_role('button',name=re.compile('^Partnership Requests')).click();expect(page.get_by_role('button').filter(has_text='Organizer 51')).to_be_visible();assert state['event_reads']==1 and not errors,errors
  print(json.dumps({'width':width,'passed':True,'synthetic_requests':60,'production_writes':0}),flush=True);ctx.close()
 browser.close()
