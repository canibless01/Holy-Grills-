"""Actual admin form and price preview contracts, controlled API only."""
import json,os,signal,subprocess,tempfile,time
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
repo=Path(__file__).resolve().parents[1];out=Path(tempfile.mkdtemp(prefix='hg-reward-price-'));campus='11111111-1111-4111-8111-111111111111';tier='22222222-2222-4222-8222-222222222222';rows=[];previews=[];created=[];updates=[]
def fixture(route):
 req=route.request;p=urlparse(req.url).path;data=[]
 if p.endswith('/auth/me'):data={'id':'controlled-admin','role':'admin','campus_id':campus,'full_name':'Controlled admin','profile':{'id':'controlled-admin','role':'admin','campus_id':campus}}
 elif p.endswith('/campuses'):data=[{'id':campus,'name':'Controlled campus','is_active':True}]
 elif p.endswith('/hp/tiers'):data=[{'id':tier,'name':'Ember','slug':'ember'}]
 elif p.endswith('/rewards/admin/economics-preview'):
  body=req.post_data_json;previews.append(body)
  complete=all(body.get(key) is not None for key in ('food_cost','menu_price'))
  data={'complete':complete}
  if complete:data.update(hp_cost=1627 if body['food_cost']==600 else 1547,reward_value=1220 if body['food_cost']==600 else 1160,hp_liability=1220.25 if body['food_cost']==600 else 1160.25)
 elif p.endswith('/rewards/created-reward') and req.method=='PATCH':
  updates.append(req.post_data_json);route.fulfill(status=409,json={'error':'This reward changed while you were editing it. Reload it before saving again.'});return
 elif p.endswith('/rewards'):
  if req.method=='POST':
   body=req.post_data_json;created.append(body);row={**body,'id':'created-reward','hp_cost':1547,'reward_value':1160,'hp_liability':1160.25,'updated_at':'stamp-1'};rows.append(row);data=row
  else:data=rows
 elif p.endswith('/cart'):data={'items':[]}
 elif any(x in p for x in ('messages','config','feature-flags','balance','streak')):data={}
 route.fulfill(status=200,json=data)
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5217','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
try:
 time.sleep(2)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox']);ctx=browser.new_context(viewport={'width':1280,'height':1000});ctx.route('**/api/**',fixture);ctx.add_init_script("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_campus_id','"+campus+"');localStorage.setItem('hg_user_campus_id','"+campus+"');localStorage.setItem('hg_admin_campus_id','"+campus+"')")
  p=ctx.new_page();p.goto('http://127.0.0.1:5217/admin?section=rewards');p.get_by_role('button',name='Essential only',exact=True).click();p.get_by_role('button',name='Add Reward',exact=True).click();expect(p.get_by_text('Enter cost inputs to preview',exact=True)).to_be_visible()
  p.get_by_label('Name',exact=True).fill('Controlled meal');p.get_by_label('Food cost (₦)',exact=True).fill('500');p.get_by_label('Packaging cost (₦)',exact=True).fill('100');p.get_by_label('Menu price (₦)',exact=True).fill('2000');p.get_by_label('Margin share (%)',exact=True).fill('40');expect(p.get_by_text('1547 HP',exact=True).first).to_be_visible();assert previews[-1]['margin_share_pct']==.4
  p.get_by_role('button',name='Create Reward',exact=True).click();expect(p.get_by_role('button',name='Edit reward',exact=True)).to_be_visible();assert len(created)==1;assert created[0]['reward_type']=='food';assert created[0]['min_tier_id']==tier;assert 'hp_cost' not in created[0] and 'available_margin' not in created[0]
  before=len(previews);p.get_by_role('button',name='Edit reward',exact=True).click();expect(p.get_by_label('Margin share (%)',exact=True)).to_have_value('40');p.wait_for_timeout(450);assert len(previews)==before;expect(p.get_by_text('1547 HP',exact=True).first).to_be_visible();p.get_by_label('Food cost (₦)',exact=True).fill('600');expect(p.get_by_text('1627 HP',exact=True).first).to_be_visible()
  p.get_by_label('Packaging cost (₦)',exact=True).fill('');p.wait_for_timeout(500);assert previews[-1]['packaging_cost'] is None
  p.get_by_role('button',name='Save Changes',exact=True).click();expect(p.get_by_role('button',name='Reload rewards',exact=True)).to_be_visible();assert updates[-1]['expected_updated_at']=='stamp-1'
  p.get_by_role('button',name='Reload rewards',exact=True).click();expect(p.get_by_role('button',name='Edit reward',exact=True)).to_be_visible()
  browser.close()
 print(json.dumps({'empty_catalog_can_create':True,'backend_preview_and_percent_units':True,'canonical_type_real_tier_and_clean_payload':True,'unrelated_edit_retains_saved_price':True,'changed_cost_requests_new_preview':True}))
finally:os.killpg(proc.pid,signal.SIGTERM)
