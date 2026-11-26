"""Native APK choice vs Safari guide; local fixtures only, no customer writes."""
import os,json
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('HG_BROWSER_BASE','http://127.0.0.1:4189');C='70000001-cafe-cafe-cafe-000000000001'
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
 for platform,ua in [('android','Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/130 Mobile Safari/537.36'),('ios','Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17 Mobile Safari/604.1')]:
  counts={'manifest':0,'writes':0};errors=[]
  ctx=browser.new_context(viewport={'width':393,'height':852},user_agent=ua,service_workers='block')
  ctx.add_init_script(f"localStorage.setItem('hg_campus_id','{C}');localStorage.setItem('hg_cookie_consent',JSON.stringify({{essential:true,analytics:false}}));")
  def intercept(route):
   req=route.request;path=urlparse(req.url).path
   if path.endswith('/android-release.json'):
    counts['manifest']+=1;route.fulfill(status=200,headers={'Access-Control-Allow-Origin':'*'},json={'available':True,'version':'1.0.0','versionCode':1,'url':'https://github.com/canibless01/Holy-Grills-/releases/download/android-v1/Holy-Grills.apk','sha256':'a'*64});return
   if req.method not in ('GET','OPTIONS'):counts['writes']+=1
   result={}
   if path.endswith('/campuses'):result={'campuses':[{'id':C,'name':'FUTA','slug':'futa','is_active':True}]}
   elif '/menu' in path:result={'items':[],'categories':[]}
   elif '/sections' in path:result={'sections':[]}
   elif path.endswith('/notifications'):result={'notifications':[]}
   route.fulfill(status=200,headers={'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'*','Access-Control-Allow-Methods':'GET,POST,OPTIONS'},json=result)
  ctx.route('**/api/**',intercept);ctx.route('**/android-release.json',intercept);ctx.route('https://*.onesignal.com/**',lambda r:r.abort())
  page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.on('console',lambda m: print(m.type,m.text[:160],flush=True) if m.type=='error' else None)
  page.goto(BASE+'/',wait_until='domcontentloaded')
  page.wait_for_timeout(1200)
  if platform=='android':
   expect(page.get_by_role('link',name='Download APK',exact=True)).to_be_visible();assert counts['manifest']==1
   page.get_by_role('link',name='Download APK',exact=True).click();expect(page.get_by_role('heading',name='Holy Grills for Android',exact=True)).to_be_visible();expect(page.get_by_role('link',name='Download APK',exact=True)).to_have_attribute('href','https://github.com/canibless01/Holy-Grills-/releases/download/android-v1/Holy-Grills.apk');assert counts['manifest']==1
  else:
   page.get_by_role('button',name='Add to Home Screen',exact=True).click();expect(page.get_by_role('dialog',name='Add to Home Screen',exact=True)).to_be_visible();expect(page.get_by_text('In Safari, tap Share.',exact=True)).to_be_visible();assert counts['manifest']==0
   assert page.get_by_role('link',name='Download APK',exact=True).count()==0
  assert not errors,errors;assert counts['writes']==0;assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
  print(json.dumps({'platform':platform,**counts,'passed':True}),flush=True);ctx.close()
 browser.close()
