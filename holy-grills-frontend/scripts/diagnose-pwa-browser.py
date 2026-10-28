"""Production-host PWA diagnostics using real CDP, never synthetic install events.
Run after npm run build. Default: local production host. --origin supports live checks.
Headless Chromium has no omnibox; mobile emulation is not an Android-device test.
"""
import argparse,json,os,signal,struct,subprocess,tempfile,time
from pathlib import Path
from urllib.parse import urljoin,urlparse
from playwright.sync_api import sync_playwright
parser=argparse.ArgumentParser();parser.add_argument('--origin',default='http://127.0.0.1:5240');parser.add_argument('--output',default='/tmp/hg-pwa-diagnostics.json');args=parser.parse_args()
repo=Path(__file__).resolve().parents[1];origin=args.origin.rstrip('/');proc=None
if origin=='http://127.0.0.1:5240':
 proc=subprocess.Popen(['node','scripts/serve-static.mjs','5240'],cwd=repo,start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT);time.sleep(1)
results={'origin':origin,'mode':'real CDP; headless browser; clean persistent profiles; controlled application API; not visible Chrome omnibox or physical Android','profiles':[]}
try:
 with sync_playwright() as pw:
  contexts=[]
  for mobile in (False,True):
   context=pw.chromium.launch_persistent_context(tempfile.mkdtemp(prefix='hg-pwa-clean-'),executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'],viewport={'width':393 if mobile else 1365,'height':873 if mobile else 900},is_mobile=mobile,has_touch=mobile,service_workers='allow')
   context.add_init_script("window.__pwaEvents=[];addEventListener('beforeinstallprompt',e=>window.__pwaEvents.push({type:e.type,trusted:e.isTrusted}));addEventListener('securitypolicyviolation',e=>window.__pwaEvents.push({type:'csp',directive:e.effectiveDirective,blocked:e.blockedURI}))")
   context.route('**/api/**',lambda route:route.fulfill(status=200,json={} if any(x in route.request.url for x in ('messages','config','feature-flags')) else []))
   page=context.new_page();cdp=context.new_cdp_session(page);cdp.send('Page.enable');page.goto(origin,wait_until='domcontentloaded',timeout=30000)
   try:page.get_by_role('button',name='Essential only',exact=True).click(timeout=8000)
   except Exception:page.mouse.click(20,20)
   contexts.append((context,page,cdp,mobile,time.monotonic()))
  # Allow actual Chrome engagement evaluation, without fabricating the event.
  while any(time.monotonic()-started<32 for _,_,_,_,started in contexts):
   for _,page,_,_,_ in contexts:page.wait_for_timeout(250)
  for context,page,cdp,mobile,started in contexts:
   data=cdp.send('Page.getAppManifest');manifest=json.loads(data.get('data') or '{}');manifest_url=data.get('url') or origin+'/manifest.json';assets=[]
   for icon in manifest.get('icons',[]):
    url=urljoin(manifest_url,icon['src']);res=context.request.get(url);body=res.body();entry={'url':url,'status':res.status,'content_type':res.headers.get('content-type'),'declared':icon.get('sizes')}
    if body[:8]==b'\x89PNG\r\n\x1a\n':entry['pixels']=list(struct.unpack('>II',body[16:24]))
    assets.append(entry)
   sw=page.evaluate("async()=>({secureContext:isSecureContext,controller:navigator.serviceWorker.controller?.scriptURL||null,registrations:(await navigator.serviceWorker.getRegistrations()).map(r=>({scope:r.scope,script:r.active?.scriptURL,state:r.active?.state}))})")
   response=context.request.get(urljoin(manifest_url,manifest.get('start_url','/')))
   result={'profile':'mobile emulation' if mobile else 'desktop','browser':context.browser.version,'engagement_seconds':round(time.monotonic()-started),'manifest_url':manifest_url,'manifest_errors':data.get('errors',[]),'installability':cdp.send('Page.getInstallabilityErrors'),'manifest':manifest,'icons':assets,'start_url_status':response.status,'service_worker':sw,'events':page.evaluate('window.__pwaEvents'),'manifest_links':page.locator('link[rel="manifest"]').count()}
   result['asset_headers'] = {}
   for path in ('/manifest.json','/service-worker.js'):
    res=context.request.get(origin+path)
    result['asset_headers'][path]={'status':res.status,**{key:value for key,value in res.headers.items() if key in ('content-type','cache-control','service-worker-allowed')}}
   results['profiles'].append(result);context.close()
   assert not result['installability'].get('installabilityErrors'), result['installability']
   assert not any(error.get('critical') for error in result['manifest_errors']), result['manifest_errors']
   assert result['manifest_links']==1 and result['start_url_status']==200
   assert sw['secureContext'] and sw['controller'] and any(reg.get('state')=='activated' for reg in sw['registrations'])
   assert manifest.get('name') or manifest.get('short_name')
   assert manifest.get('display') in ('standalone','fullscreen','minimal-ui','window-controls-overlay')
   assert manifest.get('prefer_related_applications') is not True
   assert urlparse(urljoin(manifest_url,manifest['start_url'])).netloc==urlparse(origin).netloc
   for size in (192,512):
    assert any(icon['status']==200 and icon.get('pixels')==[size,size] and icon['content_type'].startswith('image/png') for icon in assets)
 Path(args.output).write_text(json.dumps(results,indent=2))
 for result in results['profiles']:
  print(json.dumps({'profile':result['profile'],'chrome_errors':result['installability'],'manifest_errors':result['manifest_errors'],'secure_context':result['service_worker']['secureContext'],'worker':result['service_worker']['controller'],'start_status':result['start_url_status'],'native_event':any(e['type']=='beforeinstallprompt' for e in result['events']),'icons':result['icons']}))
finally:
 if proc:os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
