"""Bounded, local-only acceptance for the public Next pilot. Never writes to production."""
import json,os,socket,subprocess,threading,time,urllib.request
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
OUT=Path(os.environ.get('HG_TEST_OUTPUT','/tmp/hg-next-acceptance'));OUT.mkdir(parents=True,exist_ok=True)
def free_port():
 with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
api_port=free_port();web_port=free_port();base=f'http://127.0.0.1:{web_port}'
state={'price':2500,'menu_fail':False,'calls':[],'writes':[]}
class API(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_POST(self):state['writes'].append(self.path);self.send_error(405)
 def do_GET(self):
  url=urlparse(self.path);p=url.path;q=parse_qs(url.query);cid=self.headers.get('X-Campus-ID');state['calls'].append({'path':p,'campus':cid,'query':q})
  if p.endswith('/campuses'):data={'campuses':[{'id':'campus-a','slug':'alpha','name':'Campus Alpha','is_default':True},{'id':'campus-b','slug':'beta','name':'Campus Beta'}]}
  elif p.endswith('/menu/items'):
   if state['menu_fail']:self.send_error(503);return
   if not cid or q.get('campus_id')!=[cid]:self.send_error(400);return
   name='Plate Alpha' if cid=='campus-a' else 'Plate Beta'
   data={'items':[{'id':'plate','name':name,'description':'Grilled chicken with chips','price':state['price'],'is_available':True,'category_id':'plates','cushion_amount':800,'internal_secret':'SHOULD_NOT_LEAK'},{'id':'side','name':'Side Slaw','description':'Fresh slaw','price':600,'is_available':True,'category_id':'sides'},{'id':'out','name':'Sold-out plate','price':1000,'is_available':True,'is_sold_out':True,'category_id':'plates'},{'id':'secret','name':'Hidden item','price':900,'is_secret':True,'is_available':True}]}
  elif p.endswith('/menu/categories'):data=[{'id':'plates','name':'Plates'},{'id':'sides','name':'Sides'}]
  elif p.endswith('/storefront/banners'):data=[{'placement':'hero','metadata':{'slides':[{'display_mode':'text','title':'Together at the table','subtitle':'A CMS-backed hero','cta_text':'Browse meals','cta_url':'/menu'}]}}]
  elif p.endswith('/storefront/sections'):data=[]
  else:self.send_error(404);return
  self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(json.dumps(data).encode())
server=ThreadingHTTPServer(('127.0.0.1',api_port),API);threading.Thread(target=server.serve_forever,daemon=True).start()
env={**os.environ,'API_BASE_URL':f'http://127.0.0.1:{api_port}/api','LIVE_SITE_URL':'https://holygrills.online','NEXT_TELEMETRY_DISABLED':'1'}
log=(OUT/'server.log').open('w');proc=subprocess.Popen(['node','node_modules/next/dist/bin/next','start','--hostname','127.0.0.1','--port',str(web_port)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
checks=[]
def ok(label):checks.append(label);print('PASS',label,flush=True)
def fetch(path):
 with urllib.request.urlopen(base+path,timeout=18) as r:return r.status,dict(r.headers),r.read().decode()
try:
 for attempt in range(80):
  if proc.poll() is not None:raise RuntimeError((OUT/'server.log').read_text())
  try:
   with socket.create_connection(('127.0.0.1',web_port),timeout=.2):break
  except OSError:time.sleep(.1)
 else:raise RuntimeError('Next server did not start')
 status,headers,html=fetch('/menu');assert status==200 and 'Plate Alpha' in html and '2,500' in html
 assert 'SHOULD_NOT_LEAK' not in html and 'cushion_amount' not in html and 'Hidden item' not in html;ok('Initial HTML contains real DTO fields and excludes internal/secret fields')
 assert 'noindex' in headers.get('X-Robots-Tag','') and 'noindex' in html;assert 'Disallow: /' in fetch('/robots.txt')[2];ok('Preview is excluded from indexing by headers, metadata and robots')
 state['price']=2700;assert '2,700' in fetch('/menu')[2];ok('Price changes are visible on the next request without stale menu caching')
 assert 'Plate Beta' in fetch('/menu?campus=beta')[2];assert 'Plate Alpha' not in fetch('/menu?campus=beta')[2];ok('Campus-scoped menu never crosses into the other campus')
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
  nojs=browser.new_context(java_script_enabled=False,viewport={'width':1440,'height':1000});page=nojs.new_page();page.goto(base+'/menu');expect(page.get_by_role('heading',name='Plate Alpha',exact=True)).to_be_visible();ok('Menu renders with JavaScript disabled')
  page.get_by_label('Search the menu').fill('slaw');page.get_by_role('button',name='Find a meal').click();expect(page.get_by_role('heading',name='Side Slaw',exact=True)).to_be_visible();assert page.get_by_role('heading',name='Plate Alpha',exact=True).count()==0;ok('Native search form works without hydration')
  page.get_by_label('Search the menu').fill('');page.get_by_label('Category',exact=True).select_option('sides');page.get_by_role('button',name='Find a meal').click();expect(page.get_by_role('heading',name='Side Slaw',exact=True)).to_be_visible();ok('Category filtering composes with search')
  page.goto(base+'/');expect(page.get_by_role('heading',name='Together at the table')).to_be_visible();assert page.get_by_role('link',name='Browse meals').get_attribute('href')=='/menu?campus=alpha';ok('CMS content and campus-preserving CTA render without JavaScript')
  nojs.close();ctx=browser.new_context(viewport={'width':390,'height':844});errors=[];api_calls=[];page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:api_calls.append(r.url) if '/api/' in r.url else None)
  page.goto(base+'/menu');expect(page.get_by_role('heading',name='Plate Alpha',exact=True)).to_be_visible();page.wait_for_timeout(400)
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');assert not errors,errors;assert not api_calls,api_calls
  page.screenshot(path=str(OUT/'menu-mobile.png'),full_page=True);ok('Mobile layout has no horizontal overflow, page errors or browser API waterfall')
  links=page.get_by_role('link',name='Choose options');assert links.count()==2;assert all(x.get_attribute('href').startswith('https://holygrills.online/menu/') for x in links.all());ok('Only available items hand off to the intended live product page')
  r=page.goto(base+'/menu?campus=unknown');assert r.status==404;ok('Unknown campus returns 404 instead of silently showing another campus')
  state['menu_fail']=True;page.goto(base+'/menu');expect(page.get_by_role('heading',name='We couldn’t load the menu just now.')).to_be_visible();expect(page.get_by_role('link',name='Try again')).to_be_visible();ok('API failure gives a recoverable screen, not invented data or a crash')
  state['menu_fail']=False;page.get_by_role('link',name='Try again').click();expect(page.get_by_role('heading',name='Plate Alpha',exact=True)).to_be_visible();ok('Retry recovers after the API returns')
  for path in ['/admin','/wallet','/checkout']:
   assert page.goto(base+path).status==404
  ok('Private/payment routes are not exposed by the pilot')
  browser.close()
 assert not state['writes'];assert all(c['campus'] in ('campus-a','campus-b') for c in state['calls'] if c['path'].endswith('/menu/items'));ok('Every source operation is GET-only and every menu read is campus scoped')
 (OUT/'result.json').write_text(json.dumps({'checks':checks,'passed':len(checks),'production_writes':0,'browser_source_api_requests':0},indent=2))
finally:
 proc.terminate()
 try:proc.wait(timeout=6)
 except subprocess.TimeoutExpired:proc.kill()
 log.close();server.shutdown()
print('ALL',len(checks),'ACCEPTANCE CHECKS PASSED')
