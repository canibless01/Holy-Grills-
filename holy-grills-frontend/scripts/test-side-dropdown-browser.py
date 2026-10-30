"""Four independent side dropdowns retain availability, price and cart contract."""
import json,os,signal,subprocess,tempfile,time
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
repo=Path(__file__).resolve().parents[1];out=Path(tempfile.mkdtemp(prefix='hg-sides-'));c='11111111-1111-4111-8111-111111111111';mid='22222222-2222-4222-8222-222222222222'
groups=[{'id':f'group-{i}','name':f'Select side {i+1}','is_required':True,'min_selections':1,'max_selections':1,
 'options':[{'id':f'option-{i}-{j}','name':['Rice','Chips','Coleslaw','Unavailable side'][j],'price_delta':j*10,'is_available':j!=3} for j in range(4)]} for i in range(4)]
item={'id':mid,'name':'Controlled four-side meal','price':1000,'hp_earn_value':100,'hp_multiplier':1,'is_available':True,'variation_groups':groups,'description':'Controlled meal'}
def fixture(route):
 path=urlparse(route.request.url).path;data={}
 if path.endswith('/campuses'):data=[{'id':c,'name':'Controlled campus','is_active':True}]
 elif path.endswith('/menu/items/'+mid):data=item
 elif path.endswith('/addons'):data={'addon_groups':[]}
 elif path.endswith('/menu/items'):data={'items':[item]}
 elif path.endswith('/cart'):data={'items':[]}
 route.fulfill(status=200,json=data)
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5229','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
try:
 time.sleep(2)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);ctx=browser.new_context(viewport={'width':390,'height':844});ctx.route('**/api/**',fixture);ctx.add_init_script("localStorage.setItem('hg_campus_id','"+c+"')")
  page=ctx.new_page();page.set_default_timeout(8000);page.goto('http://127.0.0.1:5229/menu/'+mid);page.get_by_role('button',name='Essential only',exact=True).click()
  expect(page.get_by_role('combobox')).to_have_count(4);expect(page.get_by_role('button',name='Add to Cart',exact=True)).to_be_disabled()
  for i in range(4):
   dropdown=page.get_by_role('combobox',name=f'Select side {i+1}',exact=True);expect(dropdown.locator('option',has_text='Unavailable side')).to_be_disabled();dropdown.select_option(f'option-{i}-{i%3}')
  expect(page.get_by_role('button',name='Add to Cart',exact=True)).to_be_enabled();page.get_by_role('button',name='Add to Cart',exact=True).click()
  page.wait_for_function("JSON.parse(localStorage.getItem('hg_guest_cart')||'[]').length===1")
  cart=page.evaluate("JSON.parse(localStorage.getItem('hg_guest_cart'))");selected=cart[0]['selected_variations'];assert len(selected)==4
  assert {row['option_id'] for row in selected}=={f'option-{i}-{i%3}' for i in range(4)}
  assert cart[0]['menu_items']['price']==1030
  browser.close()
 print(json.dumps({'four_compact_independent_dropdowns':True,'required_choices_enforced':True,'unavailable_sides_disabled':True,'all_four_cart_selections_and_price_retained':True}))
finally:os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
