"""Local fixture transport only: edit/delete/contact UI at staff roles and widths."""
import json,os
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('HG_BROWSER_BASE','http://127.0.0.1:4187')
C='70000001-cafe-cafe-cafe-000000000001';U='11111111-1111-4111-8111-111111111111';M='22222222-2222-4222-8222-222222222222';A='33333333-3333-4333-8333-333333333333'
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
 for role in ['community_manager','admin','super_admin']:
  for width in [393,1280]:
   state={'deleted':False,'caption':'Hello {{link}}','revision':1,'contact':None,'assignments':0,'writes':[]};errors=[]
   ctx=browser.new_context(service_workers='block',viewport={'width':width,'height':950})
   ctx.add_init_script(f"localStorage.setItem('hg_access_token','synthetic');localStorage.setItem('hg_campus_id','{C}');localStorage.setItem('hg_user_campus_id','{C}');localStorage.setItem('hg_admin_campus_id','{C}');localStorage.setItem('hg_user_role','{role}');")
   def api(route):
    req=route.request;path=urlparse(req.url).path;method=req.method;data={}
    if path.endswith('/auth/me'):data={'id':U,'full_name':'Local staff','role':role,'campus_id':C,'is_active':True}
    elif path.endswith('/campuses'):data={'campuses':[{'id':C,'name':'FUTA','slug':'futa','is_active':True}]}
    elif path.endswith('/ambassadors/staff/promo-messages'):data={'messages':[] if state['deleted'] else [{'id':M,'caption':state['caption'],'revision':state['revision'],'month':'2026-11','target_all':True}]}
    elif path.endswith('/promo-messages/'+M):
     body=req.post_data_json;state['writes'].append((method,body))
     assert body['revision']==state['revision']
     if method=='PATCH':state['caption']=body['caption'];state['revision']+=1
     elif method=='DELETE':state['deleted']=True
     else:raise AssertionError('Unexpected message method')
     data={'message':{'id':M,'caption':state['caption'],'revision':state['revision']}}
    elif path.endswith('/assignments'):
     state['assignments']+=1;data={'assignments':[{'id':A,'ambassador_id':A,'status':'pending','profile':{'id':A,'full_name':'Known Ambassador','referral_code':'HGKNOWN','phone':'08012345678','ambassador_whatsapp':state['contact']}}]}
    elif path.endswith('/whatsapp'):
     body=req.post_data_json;state['writes'].append((method,body));assert path.endswith('/'+A+'/whatsapp');state['contact']=body['whatsapp_phone'];data={'whatsapp_phone':state['contact'],'ambassador_id':A}
    elif path.endswith('/notifications'):data={'notifications':[],'unread_count':0}
    route.fulfill(status=200,json=data)
   ctx.route('**/api/**',api)
   # No real external messages, image uploads or navigation are allowed.
   ctx.route('https://*.onesignal.com/**',lambda route:route.abort())
   page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
   prefix='/community-manager' if role=='community_manager' else '/admin'
   page.goto(BASE+prefix+'?section=ambassadorpromo',wait_until='domcontentloaded')
   page.get_by_role('button',name='Edit message',exact=True).click();dialog=page.get_by_role('dialog')
   dialog.get_by_label('Caption',exact=False).fill('Changed {{link}}');dialog.get_by_role('button',name='Save changes',exact=True).click();expect(dialog).not_to_be_visible()
   expect(page.get_by_role('button',name='Changed {{link}}',exact=False)).to_be_visible()
   page.get_by_role('button',name='Changed {{link}}',exact=False).click();expect(page.get_by_text('Known Ambassador',exact=True)).to_be_visible()
   assert state['assignments']==1
   page.get_by_label('Ambassador WhatsApp contact',exact=True).fill('+2348099999999');page.get_by_role('button',name='Save WhatsApp contact',exact=True).click()
   link=page.get_by_role('link',name='Share on WhatsApp',exact=True);expect(link).to_have_attribute('href',__import__('re').compile('wa.me/2348099999999'))
   assert '/register?ref=HGKNOWN' in parse_qs(urlparse(link.get_attribute('href')).query)['text'][0]
   page.get_by_role('button',name='Delete message',exact=True).click();dialog=page.get_by_role('dialog');dialog.get_by_role('button',name='Delete message',exact=True).click();expect(dialog).not_to_be_visible()
   expect(page.get_by_role('button',name='Edit message',exact=True)).to_have_count(0)
   assert [w[0] for w in state['writes']]==['PATCH','PATCH','DELETE'];assert not errors,errors
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
   print(json.dumps({'role':role,'width':width,'passed':True,'external_messages_sent':0}),flush=True);ctx.close()
 browser.close()
