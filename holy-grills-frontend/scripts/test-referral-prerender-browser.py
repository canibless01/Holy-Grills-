"""Production-built homepage referral hydration, with all API traffic controlled."""
import os, signal, subprocess, tempfile, time
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect
root=Path(__file__).resolve().parents[1]
campus='11111111-1111-4111-8111-111111111111'
log=Path(tempfile.mkdtemp())/'server.log'
proc=subprocess.Popen(['node','scripts/serve-static.mjs','5275'],cwd=root,start_new_session=True,stdout=log.open('w'),stderr=subprocess.STDOUT)
def api(route):
 path=urlparse(route.request.url).path;data=[]
 if path.endswith('/auth/registration-options'):data={'campus_id':campus,'campuses':[{'id':campus,'name':'Campus'}],'departments':[{'id':'department','name':'Medicine and Surgery','faculty':'Clinical Sciences'}],'levels':[{'id':'level','name':'300 Level','value':'300'}]}
 elif path.endswith('/campuses'):data=[{'id':campus,'name':'Campus'}]
 elif path.endswith('/messages'):data={'messages':{}}
 elif path.endswith('/ambassadors/track-click'):data={'anonymous_id':'controlled-anon'}
 route.fulfill(json=data)
try:
 time.sleep(1)
 with sync_playwright() as p:
  b=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  for width in (393,1280):
   c=b.new_context(viewport={'width':width,'height':900});c.route('**/api/**',api)
   c.add_init_script("localStorage.setItem('hg_cookie_consent',JSON.stringify({essential:true,analytics:false,date:new Date().toISOString()}));")
   page=c.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   page.goto('http://127.0.0.1:5275/?ref=HGFRIEND',wait_until='domcontentloaded')
   page.wait_for_url('**/register?ref=HGFRIEND')
   expect(page.get_by_placeholder('JANE123')).to_have_value('HGFRIEND')
   expect(page.get_by_label('School / faculty',exact=True)).to_be_enabled()
   assert not errors,errors
   c.close();print(f'PASS {width}: built prerender referral redirects and prefills without hydration/page errors',flush=True)
  b.close()
finally:
 os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
