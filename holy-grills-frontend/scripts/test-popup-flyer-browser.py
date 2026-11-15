"""Actual flyer component/page/campus receipts and artwork geometry.
Uses controlled API and image bytes; no upload/provider-delivery assertion.
"""
import json,os,re,signal,subprocess,tempfile,time
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
repo=Path(__file__).resolve().parents[1];out=Path(tempfile.mkdtemp(prefix='hg-popup-'));A='11111111-1111-4111-8111-111111111111';B='22222222-2222-4222-8222-222222222222'
harness=repo/'src/components/__audit_popup.tsx';html=repo/'__audit_popup.html'
harness.write_text("""import React from 'react';import {BrowserRouter,Link} from 'react-router-dom';import {AppProviders} from '@/App';import {HolyGrillProvider} from '@/lib/HolyGrillContext';import {CampusProvider,useCampus} from '@/lib/campusContext';import Popup from '@/components/storefront/PromoFlyerPopup';import '@/index.css';function Scope(){const c=useCampus();return <><button onClick={()=>c.selectCampus('11111111-1111-4111-8111-111111111111')}>Campus A</button><button onClick={()=>c.selectCampus('22222222-2222-4222-8222-222222222222')}>Campus B</button></>}export default function Harness(){return <AppProviders><BrowserRouter><HolyGrillProvider><CampusProvider><nav>{['/','/menu','/dashboard','/orders','/rewards','/faq'].map(path=><Link key={path} to={path}>{path==='/'?'Home':path.slice(1)}</Link>)}</nav><Scope/><input aria-label='Preserved draft'/><Popup/></CampusProvider></HolyGrillProvider></BrowserRouter></AppProviders>}""")
html.write_text("""<html><head><meta name='viewport' content='width=device-width,initial-scale=1'></head><body><div id='root'></div><script type='module'>import React from 'react';import DOM from 'react-dom/client';import Harness from '/src/components/__audit_popup.tsx';history.replaceState(null,'','/');DOM.createRoot(document.getElementById('root')).render(React.createElement(Harness));</script></body></html>""")
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5291','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
try:
 time.sleep(2)
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  for width,height,account in ((393,852,'guest'),(1280,800,'guest'),(740,400,'guest'),(393,852,'unselected'),(393,852,'member')):
   state={'revision':1};errors=[]
   ctx=browser.new_context(viewport={'width':width,'height':height});ctx.add_init_script(f"localStorage.setItem('hg_campus_id','{A}');window.__offset=0;window.__realNow=Date.now.bind(Date);Date.now=()=>window.__realNow()+window.__offset;")
   if account=='unselected':ctx.add_init_script("localStorage.removeItem('hg_campus_id')")
   if account=='member':ctx.add_init_script(f"localStorage.setItem('hg_access_token','synthetic');localStorage.setItem('hg_user_campus_id','{A}');localStorage.setItem('hg_user_role','student');")
   def api(route):
    path=urlparse(route.request.url).path;scope=route.request.headers.get('x-campus-id') or A;data={}
    if path.endswith('/auth/me'):data={'id':'33333333-3333-4333-8333-333333333333','role':'student','campus_id':A,'full_name':'Fixture member'}
    elif path.endswith('/campuses'):data={'campuses':[{'id':A,'name':'Campus A','is_active':True},{'id':B,'name':'Campus B','is_active':True}]}
    elif path.endswith('/storefront/sections'):
     data=[{'id':f'flyer-{scope}-{page}','title':f'{page} promo {state["revision"]}','section_type':'popup','is_active':True,'updated_at':f'2026-11-15T10:00:0{state["revision"]}Z','content':{'placement':page,'image_url':'https://res.cloudinary.com/demo/image/upload/popup.svg','cta_text':'Open menu','cta_url':'/menu'}} for page in ('home','menu','dashboard','orders','rewards')]
    elif path.endswith('/cart'):data={'items':[]}
    else:data=[]
    route.fulfill(status=200,json=data)
   ctx.route('**/api/**',api);ctx.route('https://*.onesignal.com/**',lambda r:r.abort());ctx.route('https://res.cloudinary.com/**',lambda r:r.fulfill(status=200,content_type='image/svg+xml',body='<svg xmlns="http://www.w3.org/2000/svg" width="300" height="450"><path fill="orange" d="M150 0L180 70H290L250 140L300 450H0L50 140L10 70H120Z"/></svg>'))
   page=ctx.new_page();page.set_default_timeout(15000);page.on('pageerror',lambda e:errors.append(str(e)));page.goto('http://127.0.0.1:5291/__audit_popup.html',wait_until='domcontentloaded',timeout=30000);
   dialog=page.get_by_role('dialog',name='home promo 1',exact=True)
   if account=='unselected':
    page.wait_for_timeout(900);expect(page.get_by_role('dialog')).to_have_count(0);page.get_by_role('button',name='Campus A',exact=True).last.click()
   expect(dialog).to_be_visible();page.wait_for_timeout(300);image=dialog.locator('img');expect(image).to_have_js_property('naturalWidth',300);box=image.bounding_box();assert abs(box['width']/box['height']-2/3)<.01;close=dialog.get_by_role('button',name='Close promotion',exact=True);bounds=close.bounding_box();cta=dialog.get_by_role('button',name='Open menu',exact=True).bounding_box();assert cta['y']>=box['y']+box['height']-1 and bounds['y']>=cta['y']+cta['height']-1,(width,height,box,cta,bounds);assert bounds['y']>=0 and bounds['y']+bounds['height']<=height,(width,height,bounds);close.click();page.get_by_label('Preserved draft',exact=True).fill('keep this')
   page.get_by_role('link',name='menu',exact=True).click();expect(page.get_by_role('dialog',name='menu promo 1',exact=True)).to_be_visible();page.keyboard.press('Escape');expect(page.get_by_role('dialog')).to_have_count(0)
   for placement in ('dashboard','orders','rewards'):
    page.get_by_role('link',name=placement,exact=True).click();expect(page.get_by_role('dialog',name=f'{placement} promo 1',exact=True)).to_be_visible();page.get_by_role('button',name='Close promotion',exact=True).click()
   page.get_by_role('link',name='faq',exact=True).click();page.wait_for_timeout(750);expect(page.get_by_role('dialog')).to_have_count(0);page.get_by_role('link',name='Home',exact=True).click();page.wait_for_timeout(800);expect(page.get_by_role('dialog')).to_have_count(0)
   page.evaluate('window.__offset+=86400001;window.dispatchEvent(new Event("focus"))');expect(page.get_by_role('dialog',name='home promo 1',exact=True)).to_be_visible();page.get_by_role('button',name='Close promotion',exact=True).click()
   state['revision']=2;page.evaluate('window.__offset+=16000;window.dispatchEvent(new Event("focus"))');expect(page.get_by_role('dialog',name='home promo 2',exact=True)).to_be_visible();page.get_by_role('button',name='Close promotion',exact=True).click();page.get_by_role('button',name='Campus B',exact=True).click();
   if account=='member':
    page.wait_for_timeout(800);expect(page.get_by_role('dialog')).to_have_count(0);page.evaluate('window.__offset+=86400001;window.dispatchEvent(new Event("focus"))')
   expect(page.get_by_role('dialog',name='home promo 2',exact=True)).to_be_visible();page.get_by_role('button',name='Open menu',exact=True).click();expect(page).to_have_url(re.compile('/menu$'));expect(page.get_by_label('Preserved draft',exact=True)).to_have_value('keep this');assert not errors,errors
   print(json.dumps({'width':width,'height':height,'account':account,'passed':True}),flush=True);ctx.close()
  browser.close()
finally:
 harness.unlink(missing_ok=True);html.unlink(missing_ok=True);os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
