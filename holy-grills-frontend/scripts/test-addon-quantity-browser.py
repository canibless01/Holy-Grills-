"""Native menu configuration with controlled transport; no remote cart writes."""
import json, os, signal, subprocess, tempfile, time
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect

repo=Path(__file__).resolve().parents[1]; out=Path(tempfile.mkdtemp(prefix='hg-addon-'))
c='11111111-1111-4111-8111-111111111111'; writes=[]
def fixture(route):
    req=route.request; p=urlparse(req.url).path; data={}
    if p.endswith('/auth/me'): data={'id':'controlled-user','role':'student','campus_id':c,'profile':{'id':'controlled-user','role':'student','campus_id':c}}
    elif p.endswith('/campuses'): data=[{'id':c,'name':'Controlled campus','is_active':True}]
    elif p.endswith('/menu/items/controlled/addons'): data={'addon_groups':[{'id':'sides','name':'Sides','max_select':3,'min_select':0,'addons':[{'id':'coleslaw','name':'Coleslaw','price':100,'is_available':True},{'id':'fries','name':'Fries','price':200,'is_available':True}]}]}
    elif p.endswith('/menu/items/controlled'): data={'id':'controlled','name':'Controlled meal','price':1000,'description':'Meal','hp_earn_value':10,'variation_groups':[],'is_available':True}
    elif p.endswith('/cart'):
        if req.method=='POST': writes.append(req.post_data_json)
        data={'items':[]}
    elif p.endswith('/saved'): data=[]
    route.fulfill(status=200,json=data)
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5221','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
try:
    time.sleep(2)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        ctx=browser.new_context(viewport={'width':390,'height':844});ctx.route('**/api/**',fixture)
        ctx.add_init_script("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_campus_id','"+c+"');localStorage.setItem('hg_user_campus_id','"+c+"')")
        page=ctx.new_page();page.goto('http://127.0.0.1:5221/menu/controlled')
        page.get_by_role('button',name='Essential only',exact=True).click()
        add=page.get_by_role('button',name='Add one Coleslaw',exact=True)
        add.click();add.click();expect(page.get_by_label('Coleslaw',exact=True)).to_have_text('2')
        page.get_by_role('button',name='Add one Fries',exact=True).click()
        expect(add).to_be_disabled();expect(page.get_by_role('button',name='Add one Fries',exact=True)).to_be_disabled()
        page.get_by_role('button',name='Remove one Fries',exact=True).click()
        expect(add).to_be_enabled()
        page.get_by_role('button',name='Add to Cart',exact=True).click()
        page.wait_for_timeout(400)
        assert writes and writes[-1]['selected_addons']==[{'addon_id':'coleslaw','quantity':2}],writes
        browser.close()
    print(json.dumps({'mobile_quantity_counter':True,'combined_group_limit':True,'decrement_releases_capacity':True,'deduplicated_quantity_payload':True}))
finally: os.killpg(proc.pid,signal.SIGTERM)
