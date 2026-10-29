"""Native global flag UI; isolated HTTP, no launch switches changed."""
import os,signal,subprocess,tempfile,time
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
repo=Path(__file__).resolve().parents[1];out=Path(tempfile.mkdtemp(prefix='hg-flags-'));campus='11111111-1111-4111-8111-111111111111';role='super_admin';fail_read=False;fail_write=False;writes=[]
flags=[{'feature_name':'hp_multiplier','is_active':False,'campus_id':None,'campus_overrides':[{'campus_id':campus,'is_active':True}]}]
def fixture(route):
    req=route.request;path=urlparse(req.url).path;data={}
    if path.endswith('/auth/me'):data={'id':'controlled','role':role,'campus_id':campus,'profile':{'id':'controlled','role':role,'campus_id':campus}}
    elif path.endswith('/campuses'):data=[{'id':campus,'name':'Campus A','is_active':True}]
    elif '/admin/feature-flags' in path:
        if req.method=='GET':
            if fail_read:route.fulfill(status=503,json={'error':'Controlled flags read failure'});return
            data=flags
        else:
            writes.append((path,req.post_data_json))
            if fail_write:route.fulfill(status=503,json={'error':'Controlled flags write failure'});return
            body=req.post_data_json
            if req.method=='PATCH':flags[0]['is_active']=body['is_active']
            else:flags.append({**body,'campus_id':None,'campus_overrides':[]})
            data={'message':'Controlled saved'}
    elif path.endswith('/storefront/feature-flags'):data=[{'feature_name':f['feature_name'],'is_active':f['is_active']} for f in flags]
    route.fulfill(status=200,json=data)
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5244','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api',npm_config_update_notifier='false'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
def context(browser):
    ctx=browser.new_context(viewport={'width':1280,'height':1000});ctx.route('**/api/**',fixture)
    ctx.add_init_script("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_admin_scope_all','1');localStorage.setItem('hg_user_role','"+role+"');localStorage.setItem('hg_user_campus_id','"+campus+"');")
    return ctx
try:
    time.sleep(2)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);ctx=context(browser);page=ctx.new_page();page.goto('http://127.0.0.1:5244/admin?section=flags')
        page.get_by_role('button',name='Essential only',exact=True).click()
        switch=page.get_by_role('switch',name='HP multiplier events feature flag',exact=True)
        expect(switch).to_have_attribute('aria-checked','false');expect(page.get_by_text('Campus A: Active',exact=True)).to_be_visible()
        fail_write=True;switch.click();expect(page.get_by_text('Controlled flags write failure',exact=True)).to_be_visible();expect(switch).to_have_attribute('aria-checked','false')
        fail_write=False;switch.click();expect(switch).to_have_attribute('aria-checked','true')
        page.wait_for_function("async () => (await import('/src/lib/featureConfig.ts')).isFeatureEnabled('hp_multiplier') === true")
        switch.click();expect(switch).to_have_attribute('aria-checked','false')
        page.wait_for_function("async () => (await import('/src/lib/featureConfig.ts')).isFeatureEnabled('hp_multiplier') === false")
        page.get_by_role('button',name='Create Flag',exact=True).click();dialog=page.get_by_role('dialog');expect(dialog.get_by_text('A new name has no effect until a feature is connected to it.',exact=False)).to_be_visible()
        fields=dialog.get_by_role('textbox');fields.nth(0).fill('audit_release');fields.nth(1).fill('Controlled new release');dialog.get_by_role('button',name='Create Flag',exact=True).click()
        expect(page.get_by_text('audit_release',exact=True).first).to_be_visible();assert len(writes)==4,writes
        ctx.close();role='admin';fail_read=True;ctx=context(browser);page=ctx.new_page();page.goto('http://127.0.0.1:5244/admin?section=flags')
        expect(page.get_by_role('alert')).to_have_text('Controlled flags read failure');fail_read=False;page.get_by_role('button',name='Retry',exact=True).click()
        expect(page.get_by_role('switch',name='HP multiplier events feature flag',exact=True)).to_be_disabled();expect(page.get_by_role('button',name='Create Flag',exact=True)).to_have_count(0)
        ctx.close();browser.close()
    print('PASS: native global flag toggle and frontend gate reload; failed write preserved; create; override visibility; campus-admin read-only; failed read retry')
finally:
    os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
