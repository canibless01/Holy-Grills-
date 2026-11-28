"""Actual menu/addon editor recovery and reversed responses; synthetic HTTP only."""
import json, os, signal, subprocess, tempfile, time
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect
ROOT=Path(__file__).resolve().parents[1]
C='11111111-1111-4111-8111-111111111111'
A='22222222-2222-4222-8222-222222222222'; B='33333333-3333-4333-8333-333333333333'
out=Path(tempfile.mkdtemp(prefix='hg-editor-recovery-'))
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5218','--strictPort'],cwd=ROOT,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
try:
 time.sleep(2)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  for width in (393,1280):
   state={'menu_fail':True,'global_fail':True,'hold_a':False,'held':[],'writes':[],'global_hold':True,'pending_global':[]}
   ctx=browser.new_context(viewport={'width':width,'height':1000})
   ctx.add_init_script(f"sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_campus_id','{C}');localStorage.setItem('hg_user_campus_id','{C}');localStorage.setItem('hg_admin_campus_id','{C}');localStorage.setItem('hg_cookie_consent',JSON.stringify({{essential:true,analytics:false,date:new Date().toISOString()}}));")
   def api(route):
    req=route.request;path=urlparse(req.url).path;data=[]
    if path.endswith('/auth/me'): data={'id':'controlled-admin','role':'admin','campus_id':C,'full_name':'Controlled admin'}
    elif path.endswith('/campuses'): data=[{'id':C,'name':'Controlled campus','is_active':True}]
    elif path.endswith('/menu/items'):
     if state['menu_fail']: route.fulfill(status=503,json={'error':'Controlled catalogue failure'});return
     data={'items':[{'id':A,'name':'Meal A','price':1000,'is_available':True},{'id':B,'name':'Meal B','price':2000,'is_available':True}]}
    elif path.endswith('/menu/addons'):
     if req.method=='POST':
      state['writes'].append(req.post_data_json)
      if state['global_hold']: state['pending_global'].append(route);return
      data={'id':'saved-addon',**req.post_data_json}
     elif state['global_fail']: route.fulfill(status=503,json={'error':'Controlled addon failure'});return
     else: data={'addons':[]}
    elif f'/menu/items/{A}' in path or f'/menu/items/{B}' in path:
     if state['hold_a'] and f'/menu/items/{A}' in path: state['held'].append(route);return
     suffix='A' if A in path else 'B'
     data={'addon_groups':[]} if path.endswith('/addons') else {'variation_groups':[{'id':'group-'+suffix,'name':'Protein '+suffix,'is_required':True,'options':[{'name':'Chicken','price_delta':0}]}]}
    route.fulfill(status=200,json=data)
   ctx.route('**/api/**',api);ctx.route('https://*.onesignal.com/**',lambda r:r.abort())
   page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   page.goto('http://127.0.0.1:5218/admin?section=menu')
   expect(page.get_by_role('alert').filter(has_text='Menu items could not be loaded')).to_be_visible()
   assert not page.get_by_text('No menu items yet.',exact=True).count()
   state['menu_fail']=False;page.get_by_role('alert').get_by_role('button',name='Retry',exact=True).click()
   expect(page.get_by_text('Meal A',exact=True)).to_be_visible()
   page.goto('http://127.0.0.1:5218/admin?section=addons')
   expect(page.get_by_role('alert').filter(has_text='Add-ons could not be loaded')).to_be_visible()
   state['global_fail']=False;page.get_by_role('alert').get_by_role('button',name='Retry',exact=True).click()
   group=page.get_by_label('Group name (e.g. Protein, Spice level)',exact=True)
   expect(group).to_have_value('Protein A')
   selector=page.get_by_label('Menu item for modifiers',exact=True)
   selector.select_option(B);expect(group).to_have_value('Protein B')
   state['hold_a']=True;selector.select_option(A);expect(page.get_by_role('button',name='Save Modifiers',exact=True)).to_be_disabled()
   page.wait_for_timeout(100);assert state['held']
   selector.select_option(B);expect(group).to_have_value('Protein B');expect(page.get_by_role('button',name='Save Modifiers',exact=True)).to_be_enabled()
   for route in state['held']:
    route.fulfill(status=200,json={'addon_groups':[]} if route.request.url.endswith('/addons') else {'variation_groups':[{'id':'old','name':'STALE A','options':[]}]})
   page.wait_for_timeout(100);expect(group).to_have_value('Protein B')
   page.get_by_role('button',name='Add Global',exact=True).click()
   page.get_by_label('Name',exact=True).fill('Extra sauce');page.get_by_label('Price (₦)',exact=True).fill('200')
   page.get_by_role('button',name='Save',exact=True).evaluate('(b)=>{b.click();b.click();}')
   expect(page.get_by_role('button',name='Cancel',exact=True)).to_be_disabled();expect(page.get_by_role('button',name='Add Global',exact=True)).to_be_disabled()
   page.wait_for_timeout(100);assert len(state['writes'])==1
   state['pending_global'].pop().fulfill(status=503,json={'error':'Controlled write failure'})
   expect(page.get_by_role('button',name='Save',exact=True)).to_be_enabled();expect(page.get_by_label('Name',exact=True)).to_have_value('Extra sauce')
   state['global_hold']=False;state['global_fail']=True
   page.get_by_role('button',name='Save',exact=True).click()
   expect(page.get_by_role('alert').filter(has_text='saved add-on list could not be refreshed')).to_be_visible();assert len(state['writes'])==2
   state['global_fail']=False;page.get_by_role('alert').filter(has_text='saved add-on list').get_by_role('button',name='Retry',exact=True).click()
   expect(page.get_by_role('alert').filter(has_text='saved add-on list')).to_have_count(0)
   assert not errors,errors
   print(json.dumps({'width':width,'catalogue_retry':True,'addon_bootstrap_retry':True,'stale_item_response_ignored':True,'unsaved_item_blocked':True,'duplicate_write_blocked':True,'failed_draft_retained':True,'post_save_refresh_retry':True}),flush=True)
   ctx.close()
  browser.close()
finally:
 os.killpg(proc.pid,signal.SIGTERM)
