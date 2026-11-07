import json,time,os
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
C='70000001-cafe-cafe-cafe-000000000001';ID='11111111-1111-4111-8111-111111111111';D='22222222-2222-4222-8222-222222222222';L='33333333-3333-4333-8333-333333333333'
BASE=os.environ.get('HG_BROWSER_BASE','http://127.0.0.1:4185')
reports=[]
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for role in ['guest','community_manager','admin','super_admin','student','kitchen','rider']:
  context=browser.new_context(viewport={'width':1365,'height':950})
  script=f"localStorage.setItem('hg_campus_id','{C}');localStorage.setItem('hg_install_dismissed',String(Date.now()));"
  if role!='guest':script+=f"localStorage.setItem('hg_access_token','synthetic');localStorage.setItem('hg_user_role','{role}');localStorage.setItem('hg_user_campus_id','{C}');"
  context.add_init_script(script)
  calls=[];writes=[];held=[];errors=[]
  def api(route):
   r=route.request;path=urlparse(r.url).path;calls.append(path);data={}
   if path.endswith('/auth/logout'):held.append(route);return
   if path.endswith('/auth/me'):data={'id':ID,'role':role,'full_name':'Local audit','campus_id':C,'is_active':True}
   elif path.endswith('/auth/registration-options'):data={'campus_id':C,'campuses':[{'id':C,'name':'FUTA'}],'departments':[{'id':D,'name':'Medicine and Surgery (MBBS)','faculty':'School of Clinical Sciences'}],'levels':[{'id':L,'name':'300 Level','value':'300'}]}
   elif path.endswith('/auth/register'):writes.append(r.post_data_json);route.fulfill(status=400,content_type='application/json',body='{"error":"Stopped safely before real signup"}');return
   elif path.endswith('/campuses'):data={'campuses':[{'id':C,'name':'FUTA','slug':'futa','is_active':True}]}
   elif '/assignments/' in path:
    writes.append(r.post_data_json);data={'assignment':{'id':D,'status':'seen'}}
   elif path.endswith('/assignments'):data={'assignments':[{'id':D,'status':'pending','profile':{'full_name':'Synthetic ambassador'}}]}
   elif '/promo-messages' in path:data={'messages':[{'id':ID,'caption':'Synthetic promo','month':'2026-11','target_all':True}]}
   elif '/notifications' in path:data={'notifications':[],'unread_count':0}
   elif 'cart' in path:data={'items':[]}
   elif any(x in path for x in ('tiers','saved','menu','feature-flags','orders','batches')):data=[]
   route.fulfill(status=200,content_type='application/json',body=json.dumps(data))
  context.route('**/api/**',api);context.route('https://*.onesignal.com/**',lambda r:r.abort())
  page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
  if role=='guest':
   page.goto(BASE+'/register')
   page.get_by_role('combobox',name='School / faculty').select_option(label='School of Clinical Sciences')
   expect(page.get_by_text('Medicine and Surgery (MBBS)',exact=True)).to_be_attached(timeout=15000)
   page.get_by_label('Full Name',exact=True).fill('Synthetic Student');page.get_by_label('Email',exact=True).fill('audit@example.invalid')
   page.get_by_label('Phone Number',exact=True).fill('08012345678')
   page.get_by_label("When's your birthday?").fill('2000-01-01')
   page.get_by_role('combobox',name='What are you studying?').select_option(D)
   page.get_by_role('combobox',name='Your level').select_option(L)
   page.get_by_label('Password (min',exact=False).fill('Synthetic2026!')
   page.get_by_label('Confirm Password',exact=True).fill('Synthetic2026!')
   page.get_by_role('checkbox',name='I agree',exact=False).check()
   if page.get_by_role('button',name='Essential only').count():page.get_by_role('button',name='Essential only').click()
   page.get_by_role('button',name='Create Account',exact=True).click()
   expect(page.get_by_text('Stopped safely before real signup')).to_be_visible()
   assert writes[0]['department_id']==D and writes[0]['academic_level_id']==L,writes
   assert calls.count('/api/auth/registration-options')==1,calls
   reports.append({'role':role,'one_reference_request':True,'MBBS_rendered':True,'console_errors':errors})
  elif role in ['community_manager','admin','super_admin']:
   page.goto(BASE+'/'+('community-manager' if role=='community_manager' else 'admin')+'?section=ambassadorpromo')
   expect(page.get_by_text('Synthetic promo',exact=True)).to_be_visible(timeout=15000)
   page.get_by_text('Synthetic promo',exact=True).click()
   expect(page.get_by_text('Synthetic ambassador',exact=True)).to_be_visible()
   page.get_by_role('button',name='Seen',exact=True).click()
   expect(page.get_by_text('Seen',exact=True).first).to_be_visible()
   assert len(writes)==1 and writes[0]['status']=='seen',writes
   assert calls.count('/api/ambassadors/staff/promo-messages')<=1,calls
   button=page.get_by_role('button',name='Sign out',exact=False)
   if button.count()==0:button=page.get_by_role('button',name='Sign Out',exact=False)
   if button.count()==0:button=page.get_by_role('button',name='Log out',exact=False)
   button.first.click()
   expect(page).to_have_url(BASE+'/login',timeout=1500)
   assert page.evaluate("localStorage.getItem('hg_access_token')") is None
   page.wait_for_timeout(300);assert page.url.endswith('/login')
   reports.append({'role':role,'seen_saved':True,'logout_does_not_wait_for_server':True,'console_errors':errors})
  else:
   # Shared role context restores without loading admin-only code.
   page.goto(BASE+'/menu')
   expect(page.get_by_role('button',name='Your account')).to_be_visible(timeout=10000)
   page.get_by_role('button',name='Your account').click()
   button=page.get_by_role('button',name='Log out',exact=False)
   if not button.count():button=page.get_by_role('button',name='Sign out',exact=False)
   button.first.click();expect(page).to_have_url(BASE+'/login',timeout=1500)
   reports.append({'role':role,'logout_does_not_wait_for_server':True,'console_errors':errors})
  assert not errors,errors
  print(json.dumps(reports[-1]),flush=True)
  for route in held:
   try:route.abort()
   except:pass
  context.close()
 browser.close()
print(json.dumps(reports))
