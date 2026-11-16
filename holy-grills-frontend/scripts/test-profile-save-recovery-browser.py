"""Native profile/reference/photo/delete feedback; controlled HTTP only."""
import json,os
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('HG_BROWSER_BASE','http://127.0.0.1:4185');C='70000001-cafe-cafe-cafe-000000000001';U='11111111-1111-4111-8111-111111111111';D='22222222-2222-4222-8222-222222222222';L='33333333-3333-4333-8333-333333333333'
OLD=f'https://res.cloudinary.com/demo/image/upload/profile_photos/{U}/old.jpg';NEW=f'https://res.cloudinary.com/demo/image/upload/profile_photos/{U}/new.jpg'
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for width in (393,1280):
  state={'profile':{'id':U,'full_name':'Original name','email':'fixture@example.invalid','role':'student','campus_id':C,'photo_url':OLD,'profile':{'phone':'08011111111','photo_url':OLD,'nickname':'Original nick','department_id':D,'department':'Computing','academic_level_id':L,'academic_level':'100','leaderboard_show_full_name':False}},'patches':[],'photos':[],'held':[],'deleteheld':[],'refs':0,'mefail':False,'fail_refresh_once':True};errors=[]
  ctx=browser.new_context(viewport={'width':width,'height':1000});ctx.add_init_script(f"localStorage.setItem('hg_access_token','synthetic');localStorage.setItem('hg_user_role','student');localStorage.setItem('hg_campus_id','{C}');localStorage.setItem('hg_user_campus_id','{C}');localStorage.setItem('hg_cookie_consent',JSON.stringify({{essential:true,analytics:false,date:new Date().toISOString()}}));")
  def api(route):
   req=route.request;path=urlparse(req.url).path;data={}
   if path.endswith('/auth/me'):
    if state['mefail']:route.fulfill(status=503,json={'error':'Controlled profile refresh failure'});return
    data=state['profile']
   elif path.endswith('/auth/registration-options'):
    state['refs']+=1
    if width==1280 and state['refs']<=2:route.fulfill(status=503,json={'error':'Controlled reference failure'});return
    data={'campus_id':C,'campuses':[{'id':C,'name':'FUTA'}],'departments':[{'id':D,'name':'Computing'}],'levels':[{'id':L,'name':'100 Level','value':'100'}]}
   elif path.endswith('/campuses'):data={'campuses':[{'id':C,'name':'FUTA','slug':'futa','is_active':True}]}
   elif path.endswith('/auth/profile/photo'):
    body=req.post_data_json;state['photos'].append(body);state['profile']['photo_url']=body['photo_url'];state['profile']['avatar_url']=body['photo_url'];state['profile']['profile']['photo_url']=body['photo_url'];data=body
   elif path.endswith('/auth/profile'):
    body=req.post_data_json;state['patches'].append(body)
    if len(state['patches'])==1:state['held'].append(route);return
    state['profile']['full_name']=body['full_name'];state['profile']['profile'].update(body)
    if state['fail_refresh_once']:state['fail_refresh_once']=False;state['mefail']=True
    data=state['profile']
   elif path.endswith('/auth/account'):
    state['deleteheld'].append(route);return
   elif path.endswith('/upload/status'):data={'configured':True,'cloud_name':'demo'}
   elif '/notifications' in path:data={'notifications':[]}
   elif path.endswith('/cart'):data={'items':[]}
   elif 'feature-flags' in path:data=[]
   else:data={}
   route.fulfill(status=200,json=data)
  ctx.route('**/api/**',api);ctx.route('https://*.onesignal.com/**',lambda r:r.abort());ctx.route('https://res.cloudinary.com/**',lambda r:r.abort())
  page=ctx.new_page();page.set_default_timeout(15000);page.on('pageerror',lambda e:errors.append(str(e)));page.goto(BASE+'/profile',wait_until='domcontentloaded',timeout=30000)
  edit=page.get_by_role('button',name='Edit Profile',exact=True)
  if width==1280:
   expect(page.get_by_role('button',name='Retry',exact=True)).to_be_visible();expect(edit).to_be_disabled();page.get_by_role('button',name='Retry',exact=True).click()
  expect(edit).to_be_enabled();edit.click();page.get_by_label('Full name',exact=True).fill('Saved name');page.get_by_label('Nickname',exact=True).fill('Saved nick');page.get_by_label('Phone',exact=True).fill('08012345678');page.get_by_role('button',name='Remove',exact=True).click();page.get_by_role('button',name='Save',exact=True).click();expect(page.get_by_role('button',name='Cancel',exact=True)).to_be_disabled();expect(page.get_by_label('Nickname',exact=True)).to_be_disabled();assert len(state['patches'])==1
  state['held'][0].fulfill(status=503,json={'error':'Controlled profile save failure'});expect(page.get_by_role('alert').filter(has_text='Controlled profile save failure')).to_be_visible();expect(page.get_by_label('Nickname',exact=True)).to_have_value('Saved nick');assert state['photos'][0]=={'photo_url':None}
  page.get_by_role('button',name='Save',exact=True).click();expect(page.get_by_role('alert').filter(has_text='Your changes were saved, but the updated profile could not be loaded.')).to_be_visible();expect(page.get_by_label('Full name',exact=True)).to_have_value('Saved name');state['mefail']=False;page.get_by_role('button',name='Save',exact=True).click();expect(edit).to_be_visible();expect(page.get_by_role('heading',name='Saved name',exact=True)).to_be_visible()
  page.reload(wait_until='domcontentloaded');expect(edit).to_be_enabled();edit.click();expect(page.get_by_label('Nickname',exact=True)).to_have_value('Saved nick');page.get_by_role('button',name='Use an image URL instead',exact=True).click();page.get_by_placeholder('https://…/image.jpg',exact=True).fill(NEW);page.get_by_role('button',name='Use',exact=True).click();page.get_by_role('button',name='Save',exact=True).click();expect(edit).to_be_visible();assert state['photos'][-1]['photo_url']==NEW
  edit.click();page.get_by_label('Nickname',exact=True).fill('Discard this');page.get_by_role('button',name='Cancel',exact=True).click();edit.click();expect(page.get_by_label('Nickname',exact=True)).to_have_value('Saved nick');page.get_by_role('button',name='Cancel',exact=True).click()
  page.get_by_role('button',name='Delete Account',exact=True).click();dialog=page.get_by_role('dialog',name='Delete account',exact=True);dialog.get_by_role('button',name='Delete my account',exact=True).click();expect(dialog.get_by_role('alert')).to_contain_text('Enter your password to confirm.');assert not state['deleteheld']
  password=dialog.get_by_placeholder('Your password',exact=True);password.fill('Fixture-only confirmation');dialog.get_by_role('button',name='Delete my account',exact=True).click();expect(password).to_be_disabled();expect(dialog.get_by_role('button',name='Close account deletion',exact=True)).to_be_disabled();state['deleteheld'][0].fulfill(status=409,json={'error':'Your account still has an active order.'});expect(dialog.get_by_role('alert')).to_contain_text('Your account still has an active order.');expect(password).to_be_enabled();assert page.evaluate("localStorage.getItem('hg_access_token')")=='synthetic';dialog.get_by_role('button',name='Close account deletion',exact=True).click();expect(dialog).not_to_be_visible()
  assert not errors,errors
  print(json.dumps({'width':width,'passed':True,'production_writes':0}),flush=True);ctx.close()
 browser.close()
