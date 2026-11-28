"""Staff distribution exceptions. Transport and external actions are intercepted."""
import json,os,re,base64
from urllib.parse import urlparse,unquote
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('HG_BROWSER_BASE','http://127.0.0.1:4185')
C='70000001-cafe-cafe-cafe-000000000001';U='11111111-1111-4111-8111-111111111111';M='22222222-2222-4222-8222-222222222222';A='33333333-3333-4333-8333-333333333333'
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for width in (393,1280):
  state={'reads':0,'status':'pending','writes':[],'fail_status':True,'roster_reads':0};errors=[]
  ctx=browser.new_context(viewport={'width':width,'height':950});ctx.add_init_script(f"localStorage.setItem('hg_access_token','synthetic');localStorage.setItem('hg_campus_id','{C}');localStorage.setItem('hg_user_campus_id','{C}');localStorage.setItem('hg_user_role','community_manager');window.auditOpened=[];window.open=(...args)=>{{window.auditOpened.push(args);return null;}};Object.defineProperty(navigator,'clipboard',{{value:{{writeText:async()=>{{throw Error('denied')}}}}}});")
  def api(route):
   req=route.request;path=urlparse(req.url).path;data={}
   if path.endswith('/auth/me'):data={'id':U,'full_name':'Audit manager','role':'community_manager','campus_id':C}
   elif path.endswith('/campuses'):data={'campuses':[{'id':C,'name':'FUTA','slug':'futa','is_active':True}]}
   elif path.endswith('/ambassadors/staff/promo-messages'):
    if req.method=='POST':state['writes'].append(req.post_data_json);data={'message':{'id':M},'recipient_count':1}
    else:data={'messages':[{'id':M,'caption':'Hello {{link}}','target_all':False,'month':'2026-11','image_url':'https://res.cloudinary.com/demo/image/upload/sample.jpg'}]}
   elif path.endswith('/assignments'):
    state['reads']+=1
    if state['reads']==1:route.fulfill(status=503,json={'error':'Controlled assignment read failure'});return
    data={'assignments':[{'id':A,'status':state['status'],'profile':{'full_name':'Known Ambassador','referral_code':'HGKNOWN','phone':'08012345678'}}]}
   elif '/assignments/' in path:
    state['writes'].append(req.post_data_json)
    if state['fail_status']:state['fail_status']=False;route.fulfill(status=503,json={'error':'Controlled status failure'});return
    state['status']=req.post_data_json['status'];data={'assignment':{'id':A,'status':state['status']}}
   elif path.endswith('/staff/ambassadors'):
    state['roster_reads']+=1
    if state['roster_reads']==1:route.fulfill(status=503,json={'error':'Controlled roster failure'});return
    data={'ambassadors':[{'ambassador':{'profile_id':U},'profile':{'full_name':'Known Ambassador'}}]}
   elif '/notifications' in path:data={'notifications':[]}
   elif path.endswith('/upload/status'):data={'configured':True,'missing':[],'cloud_name':'fixture-cloud'}
   elif path.endswith('/upload/signature'):
    assert req.post_data_json['folder']=='ambassador-promo';data={'api_key':'fixture-public-key','signature':'fixture-signature','timestamp':1,'cloud_name':'fixture-cloud','folder':'ambassador_promos/'+U}
   else:data=[]
   route.fulfill(status=200,json=data)
  def cloud_upload(route):
   assert 'ambassador_promos/'+U in route.request.post_data
   route.fulfill(status=200,json={'secure_url':'https://res.cloudinary.com/fixture-cloud/image/upload/ambassador_promos/'+U+'/flyer.png'})
  ctx.route('https://api.cloudinary.com/**',cloud_upload)
  ctx.route('https://res.cloudinary.com/**',lambda r:r.fulfill(status=200,body='<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>',content_type='image/svg+xml'))
  ctx.route('**/api/**',api);ctx.route('https://*.onesignal.com/**',lambda r:r.abort())
  page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto(BASE+'/community-manager?section=ambassadorpromo',wait_until='domcontentloaded')
  if page.get_by_role('button',name='Essential only').count():page.get_by_role('button',name='Essential only').click()
  page.get_by_role('button',name=re.compile('Hello')).click();retry=page.get_by_role('button',name='Could not load assignments. Retry',exact=True);expect(retry).to_be_visible();retry.click();expect(page.get_by_text('Known Ambassador',exact=True)).to_be_visible()
  expect(page.get_by_text('Hello '+BASE+'/?ref=HGKNOWN',exact=True)).to_be_visible()
  expect(page.get_by_role('link',name='Save graphic',exact=True)).to_have_attribute('href',re.compile('res.cloudinary.com'))
  page.get_by_role('button',name='Copy caption',exact=True).click();expect(page.get_by_text('Copy failed. Select and copy the link or caption instead.',exact=True)).to_be_visible()
  share=page.get_by_role('link',name='Share on WhatsApp',exact=True)
  expect(share).to_have_attribute('href',re.compile(r'https://wa.me/2348012345678\?text='))
  assert 'Hello '+BASE+'/?ref=HGKNOWN' in unquote(share.get_attribute('href'))
  ctx.route('https://wa.me/**',lambda r:r.fulfill(status=200,body='<html>Controlled WhatsApp destination</html>',content_type='text/html'))
  with page.expect_popup() as popup:share.click()
  expect(popup.value).to_have_url(re.compile(r'https://wa.me/2348012345678\?text='));popup.value.close()
  assert not state['writes'],'Sharing cannot fabricate manual Shared status'
  page.get_by_role('button',name='Shared',exact=True).click();expect(page.get_by_text('Controlled status failure',exact=True)).to_be_visible();assert state['status']=='pending'
  page.get_by_role('button',name='Shared',exact=True).click();expect(page.get_by_text('Shared',exact=True).first).to_be_visible();assert state['status']=='shared'
  page.get_by_role('button',name='Seen',exact=True).click();assert state['status']=='seen'
  page.get_by_role('button',name='Pending',exact=True).click();assert state['status']=='pending'
  page.get_by_role('button',name='New promotional message',exact=True).click();d=page.get_by_role('dialog');d.locator('input[type=file]').set_input_files({'name':'flyer.png','mimeType':'image/png','buffer':base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a7WQAAAAASUVORK5CYII=')});expect(d.locator('img')).to_have_attribute('src',re.compile('ambassador_promos/'+U+'/flyer.png'));d.get_by_label(re.compile('Caption')).fill('New {{link}}');expect(d.get_by_role('alert')).to_be_visible();expect(d.get_by_role('button',name='Generate personalized messages',exact=True)).to_be_disabled();d.get_by_role('button',name='Retry',exact=True).click();expect(d.get_by_role('alert')).not_to_be_visible();d.get_by_label('Send to all ambassadors',exact=True).uncheck();d.get_by_label('Known Ambassador',exact=True).check();d.get_by_role('button',name='Generate personalized messages',exact=True).click();expect(d).not_to_be_visible();assert state['writes'][-1]['image_url'].endswith('/ambassador_promos/'+U+'/flyer.png');assert state['writes'][-1]['target_all'] is False and state['writes'][-1]['ambassador_ids']==[U]
  assert not errors,errors
  print(json.dumps({'width':width,'passed':True,'external_messages_sent':0}),flush=True);ctx.close()
 browser.close()
