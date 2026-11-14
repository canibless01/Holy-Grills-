"""Native prize read/refresh failure handling; controlled transport, no real handover."""
import json,os
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('HG_BROWSER_BASE','http://127.0.0.1:4185')
C='70000001-cafe-cafe-cafe-000000000001';U='11111111-1111-4111-8111-111111111111';P='22222222-2222-4222-8222-222222222222'
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for width,failed_feed in ((393,'pending'),(1280,'fulfilled'),(393,'hof')):
  state={'fail':True,'fulfilled':False,'writes':[]};errors=[]
  ctx=browser.new_context(viewport={'width':width,'height':950});ctx.add_init_script(f"localStorage.setItem('hg_access_token','synthetic');localStorage.setItem('hg_user_role','admin');localStorage.setItem('hg_campus_id','{C}');localStorage.setItem('hg_user_campus_id','{C}');localStorage.setItem('hg_cookie_consent',JSON.stringify({{essential:true,analytics:false,date:new Date().toISOString()}}));")
  def api(route):
   req=route.request;url=urlparse(req.url);path=url.path;status=parse_qs(url.query).get('status',[''])[0];data={}
   if path.endswith('/auth/me'):data={'id':U,'full_name':'Audit admin','role':'admin','campus_id':C}
   elif path.endswith('/campuses'):data={'campuses':[{'id':C,'name':'FUTA','slug':'futa','is_active':True}]}
   elif path.endswith('/admin/leaderboard-prizes'):
    if state['fail'] and status==failed_feed:route.fulfill(status=503,json={'error':'Controlled prize failure'});return
    row={'id':P,'full_name':'Fixture winner','rank':1,'reward_description':'Fixture meal','status':status}
    data=[row] if (status=='fulfilled')==state['fulfilled'] else []
   elif '/admin/leaderboard-prizes/' in path:
    state['writes'].append(req.post_data_json);state['fulfilled']=True;state['fail']=True;data={'message':'Recorded fixture handover'}
   elif path.endswith('/admin/hall-of-fame-rewards'):
    if state['fail'] and failed_feed=='hof':route.fulfill(status=503,json={'error':'Controlled Hall of Fame failure'});return
    data=[]
   elif '/notifications' in path:data={'notifications':[]}
   else:data=[]
   route.fulfill(status=200,json=data)
  ctx.route('**/api/**',api);ctx.route('https://*.onesignal.com/**',lambda r:r.abort())
  page=ctx.new_page();page.set_default_timeout(12000);page.on('pageerror',lambda e:errors.append(str(e)));page.goto(BASE+'/admin?section=leaderboard',wait_until='domcontentloaded',timeout=30000)
  alert=page.get_by_role('alert').filter(has_text='Prize records could not be loaded.');expect(alert).to_be_visible();assert not page.get_by_text('No pending rewards. All caught up! 🎉',exact=True).count();assert not page.get_by_role('button',name='Fulfill',exact=True).count()
  state['fail']=False;alert.get_by_role('button',name='Retry',exact=True).click();expect(page.get_by_text('Fixture winner',exact=True)).to_be_visible();page.get_by_placeholder('Fulfilment notes (optional)…').fill('Handed over at reception');page.get_by_role('button',name='Fulfill',exact=True).click();expect(alert).to_be_visible();assert len(state['writes'])==1 and state['writes'][0]['notes']=='Handed over at reception'
  state['fail']=False;alert.get_by_role('button',name='Retry',exact=True).click();expect(page.get_by_text('Fulfillment History',exact=True)).to_be_visible();expect(page.get_by_text('Fixture winner',exact=True)).to_be_visible();assert not page.get_by_role('button',name='Fulfill',exact=True).count();assert len(state['writes'])==1
  assert not errors,errors
  print(json.dumps({'width':width,'failed_feed':failed_feed,'passed':True,'production_writes':0}),flush=True);ctx.close()
 browser.close()
