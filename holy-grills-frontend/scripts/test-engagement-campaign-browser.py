"""Native editor workflow against local API fixtures. Never contacts a provider."""
import json,os
from copy import deepcopy
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('HG_BROWSER_BASE','http://127.0.0.1:4187');C='70000001-cafe-cafe-cafe-000000000001';U='11111111-1111-4111-8111-111111111111'
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
 for width in [393,1280]:
  saved={'id':U,'name':'Bring your people','revision':0,'start_date':'2026-11-25','morning_time':'09:00','afternoon_time':'15:00','is_active':False,'steps':[{'day':d,'slot':slot,'title':'Your people','body':'Morning {{nickname}}','action_url':'/menu','push_image':None} for d in range(1,15) for slot in ['morning','afternoon']]}
  counts={'reads':0,'saves':0,'previews':0,'external_sends':0};errors=[]
  ctx=browser.new_context(viewport={'width':width,'height':950},service_workers='block');ctx.add_init_script(f"localStorage.setItem('hg_access_token','synthetic');localStorage.setItem('hg_user_role','admin');localStorage.setItem('hg_campus_id','{C}');localStorage.setItem('hg_user_campus_id','{C}');localStorage.setItem('hg_cookie_consent',JSON.stringify({{essential:true,analytics:false}}));")
  def api(route):
   path=urlparse(route.request.url).path;data={}
   if path.endswith('/auth/me'):data={'id':U,'full_name':'Local admin','role':'admin','campus_id':C,'is_active':True}
   elif path.endswith('/campuses'):data={'campuses':[{'id':C,'name':'FUTA','slug':'futa','is_active':True}]}
   elif path.endswith('/engagement-campaign/preview'):
    body=route.request.post_data_json;step=next(s for s in body['campaign']['steps'] if s['day']==body['day'] and s['slot']==body['slot']);counts['previews']+=1;data={**step,'body':step['body'].replace('{{nickname}}',body['nickname'])}
   elif path.endswith('/engagement-campaign'):
    if route.request.method=='PATCH':
     counts['saves']+=1;incoming=route.request.post_data_json
     if incoming['revision']!=saved['revision']:route.fulfill(status=409,json={'error':'This campaign changed. Reload the latest version before saving.'});return
     saved.update(incoming);saved['revision']+=1
    else:counts['reads']+=1
    data={'campaign':deepcopy(saved)}
   elif path.endswith('/notifications'):data={'notifications':[]}
   elif path.endswith('/notifications/blasts'):data={'blasts':[]}
   elif path.endswith('/uploads/status'):data={'configured':False,'missing':['CLOUDINARY_API_SECRET']}
   if path.endswith('/notifications/blasts/test') or path.endswith('/notifications/blasts/send'):
    counts['external_sends']+=1
   route.fulfill(status=200,json=data)
  ctx.route('**/api/**',api);ctx.route('https://*.onesignal.com/**',lambda r:r.abort());page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(BASE+'/admin?section=notifications',wait_until='domcontentloaded');expect(page.get_by_role('heading',name='14-day community push campaign',exact=True)).to_be_visible();assert counts['reads']==0
  page.get_by_role('button',name='Edit repeating campaign',exact=True).click();expect(page.get_by_label('Campaign name',exact=True)).to_have_value('Bring your people')
  page.get_by_label('Cycle day',exact=True).select_option('14');page.get_by_label('Time slot',exact=True).select_option('afternoon');page.get_by_label('Push message',exact=True).fill('Bring your people, {{nickname}}.');page.get_by_label('Preview nickname',exact=True).fill('Kani');page.get_by_role('button',name='Preview only',exact=True).click();expect(page.get_by_text('Bring your people, Kani.',exact=True)).to_be_visible();assert counts['saves']==0
  page.get_by_label('Enable recurring sends to opted-in students',exact=True).check();page.get_by_role('button',name='Save campaign',exact=True).click();expect(page.get_by_text('Saved status: Active',exact=True)).to_be_visible();assert saved['steps'][-1]['body']=='Bring your people, {{nickname}}.';assert len(saved['steps'])==28
  page.get_by_label('Enable recurring sends to opted-in students',exact=True).uncheck();page.get_by_role('button',name='Save campaign',exact=True).click();expect(page.get_by_text('Saved status: Paused',exact=True)).to_be_visible()
  saved['revision']+=1
  page.get_by_role('button',name='Save campaign',exact=True).click();expect(page.get_by_role('alert').filter(has_text='This campaign changed.')).to_be_visible();page.get_by_role('button',name='Reload campaign',exact=True).click();expect(page.get_by_label('Push message',exact=True)).to_have_value('Bring your people, {{nickname}}.')
  assert not errors,errors;assert counts['external_sends']==0;assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'),width
  print(json.dumps({'width':width,**counts,'passed':True}),flush=True);ctx.close()
 browser.close()
