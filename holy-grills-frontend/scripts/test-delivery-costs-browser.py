"""Native cost controls with controlled API responses; no live customer writes."""
import os,json
from datetime import datetime,timezone,timedelta
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('HG_BROWSER_BASE','http://127.0.0.1:4195')
C='11111111-1111-4111-8111-111111111111';U='22222222-2222-4222-8222-222222222222'
IDS=['33333333-3333-4333-8333-333333333333','44444444-4444-4444-8444-444444444444','55555555-5555-4555-8555-555555555555']
DAY=(datetime.now(timezone.utc)+timedelta(hours=1)).date().isoformat()
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for case in ('trip_mobile','edit_desktop','retry','csv','menu','addons','modifier'):
  context=browser.new_context(viewport={'width':393 if case=='trip_mobile' else 1280,'height':960},accept_downloads=True)
  context.add_init_script(f"localStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_role','admin');localStorage.setItem('hg_campus_id','{C}');localStorage.setItem('hg_user_campus_id','{C}');localStorage.setItem('hg_admin_campus_id','{C}');localStorage.setItem('hg_cookie_consent',JSON.stringify({{essential:true,analytics:false,date:new Date().toISOString()}}));")
  writes=[];saved=False
  def handler(route):
   global saved
   path=urlparse(route.request.url).path;method=route.request.method;result={}
   if method!='GET':
    if path.endswith('/auth/session-activity'):
     route.fulfill(json={});return
    body=route.request.post_data_json;writes.append({'path':path,'body':body})
    if path.endswith('/admin/delivery-costs'):
     if case=='retry' and len(writes)==1:route.fulfill(status=503,json={'error':'Temporary uncertainty'});return
     saved=True;route.fulfill(json={'entry_id':body['entry_id'],'version':1});return
    if '/menu/' in path:route.fulfill(json={'id':IDS[0],**body});return
    assert path.endswith('/budget'), 'Unexpected mutation '+path
    route.fulfill(json=[]);return
   if path.endswith('/auth/me'):result={'id':U,'role':'admin','full_name':'Controlled admin','campus_id':C}
   elif path.endswith('/campuses'):result=[{'id':C,'name':'FUTA','is_active':True}]
   elif path.endswith('/admin/delivery-costs/report'):
    result={'balance':-600,'changes':{'today':-600,'week':-600,'month':-600},'unrecorded_orders':3,'unreconciled_collections':3000,'gates':[{'campus_id':C,'campus':'FUTA','gate_id':C,'gate':'West Gate','cushion':1500,'delivery_fees':1500,'rider_costs':3600,'balance':-600,'unrecorded':0}],'trend':[{'day':DAY,'balance':-600,'change':-600}],'rows':[{'order_id':IDS[0],'campus':'=HYPERLINK("bad")','gate':'West Gate','delivery_date':DAY,'order_total':4000,'net_effect':-600}]}
   elif path.endswith('/admin/delivery-costs/budget'):result=[{'campus_id':C,'campus':'FUTA','floor':0,'version':0,'balance':-600}]
   elif '/admin/delivery-costs/history/' in path:result=[{'id':1,'actor_id':U,'occurred_at':DAY+'T12:00:00Z','after_values':{'entry':{'version':1,'total_cost':1000,'cost_date':DAY,'note':'Receipt retained'},'allocations':[{'order_id':i,'amount':333.33} for i in IDS]}}]
   elif path.endswith('/admin/delivery-costs'):
    result={'orders':[{'order_id':i,'campus_id':C,'campus_name':'FUTA','gate_id':C,'gate_name':'West Gate','delivery_date':DAY,'status':'delivered','payment_status':'paid','order_total':4000,'customer_delivery_fee':500,'cushion_original':500,'cushion_total':500,'delivery_fee_collected':500,'rider_cost':333.33 if case=='edit_desktop' or saved else None,'net_effect':666.67 if saved else None,'cost_eligible':True,'entry_id':U if case=='edit_desktop' or saved else None,'entry_version':1,'entry_kind':'trip','entry_orders':IDS,'entry_total':1000,'entry_date':DAY,'entry_note':'Receipt retained','address':'Near West Gate'} for i in IDS]}
   elif path.endswith('/menu/categories'):result=[{'id':C,'name':'Meals'}]
   elif path.endswith('/menu/items'):result={'items':[{'id':IDS[0],'name':'Grilled plate','price':3500,'cushion_amount':500,'category_id':C,'campus_id':C,'is_available':True,'hp_multiplier':1,'description':'','image_url':''}],'kitchen':{}}
   elif path.endswith('/menu/addons'):result=[{'id':IDS[1],'name':'Extra sauce','price':500,'cushion_amount':50}]
   elif path.endswith('/addons'):result={'addon_groups':[]}
   elif path.endswith('/menu/items/'+IDS[0]):result={'id':IDS[0],'variation_groups':[{'id':C,'name':'Protein','is_required':True,'options':[{'id':IDS[2],'name':'Chicken','price_delta':200,'cushion_amount':50}]}]}
   elif path.endswith('/feature-flags') or path.endswith('/system-settings'):result=[]
   elif path.endswith('/notifications'):result={'notifications':[],'unread_count':0}
   elif path.endswith('/cart'):result={'items':[]}
   elif 'storefront' in path:result=[] if 'banner' in path or 'hours' in path else {}
   route.fulfill(json=result)
  context.route('**/api/**',handler);page=context.new_page();page.set_default_timeout(15000)
  page.on('pageerror',lambda e: print('PAGEERROR',str(e),flush=True))
  section='menu' if case in ('menu','modifier') else 'addons' if case=='addons' else 'deliverycosts'
  page.goto(BASE+'/admin?section='+section,wait_until='domcontentloaded')
  if case in ('trip_mobile','retry'):
   for order in IDS:page.get_by_label('Select order '+order[:8]).check()
   page.get_by_role('button',name='Record trip cost (3)',exact=True).click()
   expect(page.get_by_role('dialog')).to_be_visible()
   page.get_by_label('Actual rider cost',exact=True).fill('1000')
   page.get_by_label('Cost note',exact=True).fill('One West Gate trip')
   page.get_by_role('button',name='Save actual cost',exact=True).click()
   if case=='retry':
    expect(page.get_by_role('alert').filter(has_text='uncertain')).to_be_visible()
    expect(page.get_by_label('Actual rider cost',exact=True)).to_be_disabled()
    page.get_by_role('button',name='Retry same save',exact=True).click()
   expect(page.get_by_role('dialog')).to_have_count(0)
   assert writes[0]['body']['total_cost']=='1000' and set(writes[0]['body']['order_ids'])==set(IDS)
   if case=='retry':assert writes[0]['body']==writes[1]['body'],'Retry changed intent'
   if case=='trip_mobile':page.screenshot(path='/workspace/Holy-Grills-/work/delivery-costs-mobile.png',full_page=True)
  elif case=='edit_desktop':
   page.get_by_role('button',name='Edit trip cost',exact=True).first.click();expect(page.get_by_label('Actual rider cost',exact=True)).to_have_value('1000')
   page.get_by_label('Actual rider cost',exact=True).fill('3600');page.get_by_role('button',name='Save actual cost',exact=True).click();expect(page.get_by_role('dialog')).to_have_count(0)
   assert writes[0]['body']['entry_id']==U and writes[0]['body']['version']==1 and len(writes[0]['body']['order_ids'])==3
   page.get_by_role('button',name='Cost history '+IDS[0][:8],exact=True).click();expect(page.get_by_text('Receipt retained',exact=True)).to_be_visible()
  elif case=='csv':
   with page.expect_download() as event:page.get_by_role('button',name='Export orders CSV',exact=True).click()
   content=open(event.value.path(),encoding='utf-8-sig').read()
   assert "'=HYPERLINK" in content and '"-600"' in content
   page.get_by_label('Pool warning floor',exact=True).fill('30000');page.get_by_role('button',name='Save floor',exact=True).click()
   page.wait_for_timeout(100);assert writes[-1]['body']=={'floor':'30000','version':0}
  elif case=='menu':
   # Menu edit icon is unlabeled in the existing grid: choose its Pencil button through its SVG class.
   page.get_by_text('Grilled plate',exact=True).wait_for()
   page.locator('button').filter(has=page.locator('svg.lucide-pencil')).first.click()
   expect(page.get_by_label('Delivery cushion included (₦)',exact=True)).to_have_value('500')
   page.get_by_label('Delivery cushion included (₦)',exact=True).fill('600')
   page.get_by_role('button',name='Save Changes',exact=True).click()
   page.wait_for_timeout(100);assert writes[0]['body']['cushion_amount']==600 and writes[0]['body']['price']==3500
  elif case=='modifier':
   page.get_by_text('Grilled plate',exact=True).wait_for();page.locator('button').filter(has=page.locator('svg.lucide-pencil')).first.click()
   expect(page.get_by_label('Cushion for Chicken',exact=True)).to_have_value('50')
   page.get_by_label('Cushion for Chicken',exact=True).fill('80');page.get_by_role('button',name='Save Modifiers',exact=True).click()
   page.wait_for_timeout(200)
   assert any(write['body'].get('cushion_amount')==80 for write in writes)
  else:
   page.get_by_text('Extra sauce',exact=True).wait_for();page.locator('button').filter(has=page.locator('svg.lucide-pencil')).first.click()
   expect(page.get_by_label('Delivery cushion included (₦)',exact=True)).to_have_value('50')
   page.get_by_label('Delivery cushion included (₦)',exact=True).fill('100');page.get_by_role('button',name='Save',exact=True).click()
   page.wait_for_timeout(100);assert writes[0]['body']['cushion_amount']==100 and writes[0]['body']['price']==500
  assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),'Horizontal overflow'
  print('PASS',case,flush=True);context.close()
 browser.close()
