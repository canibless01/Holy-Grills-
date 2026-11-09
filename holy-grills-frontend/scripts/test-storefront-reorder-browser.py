"""Native sorting controls against controlled API; no production mutations."""
import os,signal,subprocess,tempfile,time,uuid
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
repo=Path(__file__).resolve().parents[1];out=Path(tempfile.mkdtemp(prefix='hg-cms-sort-'));campus=str(uuid.uuid4())
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5272','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
try:
 time.sleep(2)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  for width in (393,1280):
   def rows(kind):return [{'id':str(uuid.uuid4()),'title':kind+' '+str(i),'key':kind+str(i),'campus_id':None,'section_type':'whats_inside','placement':'hero','sort_order':0,'updated_at':'2026-11-09T10:00:00+00:00','is_active':True,'content':{'placement':'home','display_mode':'text'},'metadata':{'slides':[{'title':kind+' '+str(i),'image_url':'','display_mode':'text'}]}} for i in range(1,6)]
   state={'sections':rows('Card'),'banners':rows('Carousel'),'fail':False,'moves':[]};state['sections'][0]['content'].pop('placement');errors=[]
   def api(route):
    r=route.request;path=urlparse(r.url).path;data={}
    if path.endswith('/auth/me'):data={'id':'controlled','role':'super_admin','campus_id':campus,'is_active':True,'profile':{'id':'controlled','role':'super_admin','campus_id':campus}}
    elif path.endswith('/campuses'):data=[{'id':campus,'name':'FUTA','is_active':True}]
    elif path.endswith('/move'):
     group='sections' if '/sections/' in path else 'banners';body=r.post_data_json;state['moves'].append(body)
     if state['fail']:state['fail']=False;route.fulfill(status=409,json={'error':'Content changed while reordering. Try again.'});return
     ids=[row['id'] for row in state[group]];assert {x['id'] for x in body['expected']}==set(ids)
     i=ids.index(path.split('/')[-2]);j=i+body['direction'];state[group][i],state[group][j]=state[group][j],state[group][i]
     for rank,row in enumerate(state[group]):row['sort_order']=rank
     data={'moved':True}
    elif path.endswith('/storefront/sections'):data=state['sections']
    elif path.endswith('/storefront/banners'):data=state['banners']
    elif path.endswith('/upload/status'):data={'configured':False,'missing':[]}
    elif any(x in path for x in ('early-supporters','newsletter','campaigns')):data=[]
    route.fulfill(json=data)
   ctx=browser.new_context(viewport={'width':width,'height':1000});ctx.route('**/api/**',api)
   ctx.add_init_script("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_role','super_admin');localStorage.setItem('hg_admin_scope_all','1');localStorage.setItem('hg_cookie_consent',JSON.stringify({essential:true,analytics:false,date:new Date().toISOString()}));")
   page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto('http://127.0.0.1:5272/admin?section=storefront')
   expect(page.get_by_display_value('Carousel 5') if hasattr(page,'get_by_display_value') else page.locator('input[value="Carousel 5"]')).to_be_visible()
   carousel=page.locator('fieldset').filter(has=page.locator('input[value="Carousel 5"]')).first
   carousel.get_by_title('Move carousel up',exact=True).click();expect(page.locator('input[value^="Carousel "]').nth(3)).to_have_value('Carousel 5')
   page.reload();expect(page.locator('input[value^="Carousel "]').nth(3)).to_have_value('Carousel 5')
   page.get_by_role('button',name="What's Inside 5",exact=True).click();expect(page.locator('input[value="Card 5"]')).to_be_visible()
   card=page.locator('fieldset').filter(has=page.locator('input[value="Card 5"]')).first
   card.get_by_title('Move up',exact=True).click();expect(page.locator('input[value^="Card "]').nth(3)).to_have_value('Card 5')
   state['fail']=True;card=page.locator('fieldset').filter(has=page.locator('input[value="Card 5"]')).first;card.get_by_title('Move up',exact=True).click();expect(page.get_by_text('Content changed while reordering. Try again.',exact=True)).to_be_visible();expect(page.locator('input[value^="Card "]').nth(3)).to_have_value('Card 5')
   assert len(state['moves'])==3 and not errors,(state['moves'],errors)
   ctx.close();print(f'PASS {width}: equal-rank carousel/section moves, persistence after reload, expected snapshot and stale-error recovery',flush=True)
  browser.close()
finally:os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
