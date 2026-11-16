"""Production CSP must allow offline recovery, including a failed first retry."""
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
repo=Path(__file__).resolve().parents[1]
with sync_playwright() as pw:
 browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 context=browser.new_context();state={'online':False,'probes':0};errors=[]
 def serve(route):
  path=route.request.url.split('https://offline.example',1)[-1]
  if path.startswith('/manifest.json'):
   state['probes']+=1
   if not state['online']:route.abort();return
   route.fulfill(json={'name':'Holy Grills'});return
  if path=='/offline-retry.js':route.fulfill(content_type='application/javascript',body=(repo/'public/offline-retry.js').read_text());return
  if path=='/offline.html':route.fulfill(content_type='text/html',body=(repo/'public/offline.html').read_text(),headers={'Content-Security-Policy':"default-src 'self';script-src 'self';style-src 'self' 'unsafe-inline';img-src 'self' data:;connect-src 'self'"});return
  route.fulfill(content_type='text/html',body='<h1>Connection restored</h1>')
 context.route('https://offline.example/**',serve)
 page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto('https://offline.example/offline.html');page.get_by_role('button',name='Try again',exact=True).click();expect(page.locator('#status')).to_contain_text('Still offline');expect(page.get_by_role('button',name='Try again',exact=True)).to_be_enabled();assert state['probes']==1
 state['online']=True;page.get_by_role('button',name='Try again',exact=True).click();expect(page.get_by_role('heading',name='Connection restored',exact=True)).to_be_visible();assert state['probes']==2 and not errors,errors
 print('PASS offline retry executes under production-style CSP, recovers after a failed probe, and navigates after reconnection')
 browser.close()
