"""Workspace layout, event selection and single student-site action at real viewports."""
import json,os
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('HG_BROWSER_BASE','http://127.0.0.1:4185');A='11111111-1111-4111-8111-111111111111';U='22222222-2222-4222-8222-222222222222';E='33333333-3333-4333-8333-333333333333'
expect.set_options(timeout=20000)
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for width in (393,1280):
  for role in ('event_organizer','admin'):
   errors=[];ctx=browser.new_context(viewport={'width':width,'height':1000});ctx.add_init_script(f"localStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_role','{role}');localStorage.setItem('hg_user_campus_id','{A}');localStorage.setItem('hg_cookie_consent',JSON.stringify({{essential:true,analytics:false,date:new Date().toISOString()}}));")
   event={'id':E,'title':'Ladies Hangout — an evening of connection, purpose and community','image_url':'https://res.cloudinary.com/fixture/image/upload/poster.svg','starts_at':'2026-11-28T10:00:00Z','ends_at':'2026-11-28T18:00:00Z','location':'Akure Tech Hub','review_status':'approved','is_published':True,'capacity':300,'metadata':{}}
   def api(route):
    path=urlparse(route.request.url).path;data={}
    if path.endswith('/auth/me'):data={'id':U,'role':role,'campus_id':A,'full_name':'Fixture staff'}
    elif path.endswith('/campuses'):data=[{'id':A,'name':'Campus A','is_active':True}]
    elif path.endswith('/event-organizer/events'):data={'events':[dict(event,id=E if i==0 else f'fixture-{i}',title=event['title'] if i==0 else 'Community gathering '+str(i)) for i in range(8)],'has_more':False}
    elif '/event-organizer/events/' in path and not path.endswith('/attendees'):data={'event':event,'counts':{'confirmed':120,'checked_in':35,'pending':5,'cancelled':2},'available':180000,'earned':180000,'reserved':0,'paid':0,'requests':[],'tiers':[]}
    elif path.endswith('/attendees'):data={'attendees':[]}
    elif '/notifications' in path:data={'notifications':[]}
    elif any(x in path for x in ('orders','sections','banners','feature-flags','tiers','ambassadors')):data=[]
    route.fulfill(status=200,json=data)
   ctx.route('**/api/**',api);ctx.route('https://res.cloudinary.com/**',lambda r:r.fulfill(status=200,content_type='image/svg+xml',body='<svg xmlns="http://www.w3.org/2000/svg" width="300" height="400"><rect width="300" height="400" fill="#401806"/><text x="25" y="140" fill="#f2b84b" font-size="32">ARISE</text></svg>'));ctx.route('https://*.onesignal.com/**',lambda r:r.abort());page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto(BASE+'/event-manager',wait_until='domcontentloaded')
   expect(page.get_by_role('heading',name=event['title'],exact=True)).to_be_visible();expect(page.get_by_role('button',name='Create event draft',exact=True)).to_have_count(1);expect(page.get_by_role('navigation',name='Event sections',exact=True)).to_be_visible()
   for name,anchor in [('Overview','event-overview'),('Guest list','event-attendees'),('Settlement','event-earnings')]:
    link=page.get_by_role('link',name=name,exact=True);expect(link).to_have_attribute('href','#'+anchor);assert page.locator('#'+anchor).count()==1
   page.get_by_role('link',name='Guest list',exact=True).click();expect(page.get_by_role('heading',name='Attendees and check-in',exact=True)).to_be_visible();assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(width,role)
   page.evaluate('scrollTo(0,0)');page.screenshot(path='/workspace/work/event-workspace-'+role+'-'+str(width)+'.png',full_page=True)
   if role=='admin':
    page.goto(BASE+'/admin?section=events',wait_until='domcontentloaded');site=page.get_by_role('link',name='View student page',exact=True);expect(site).to_have_count(1);expect(site).to_have_attribute('href','/');assert page.get_by_role('link',name='View Site',exact=True).count()==0;assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
   assert not errors,errors;ctx.close();print(json.dumps({'width':width,'role':role,'passed':True,'writes':0}),flush=True)
 browser.close()
