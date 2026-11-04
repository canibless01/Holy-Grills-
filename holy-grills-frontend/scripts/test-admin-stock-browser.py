"""Native stock page: scoped forms, lost responses, signed corrections and ledger. No real writes."""
import os,signal,subprocess,tempfile,time,re
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import sync_playwright,expect
repo=Path(__file__).resolve().parents[1];out=Path(tempfile.mkdtemp(prefix='hg-stock-'))
a='11111111-1111-4111-8111-111111111111';b='22222222-2222-4222-8222-222222222222';u='33333333-3333-4333-8333-333333333333';v='44444444-4444-4444-8444-444444444444';alpha='55555555-5555-4555-8555-555555555555'
items={a:[{'id':alpha,'campus_id':a,'name':'Alpha ingredient','purchase_unit_id':u,'usage_unit_id':v,'conversion_factor':2,'low_stock_threshold':3,'current_balance':0}],b:[]};writes=[];receipts={};create_loss=True;purchase_loss=True;ledger_fail=True;read_fail=False;hold_a=False;held_a=None
edit_loss=True;edit_conflict=False
role='super_admin';scope_reads=[]
units=[{'id':u,'name':'Bags'},{'id':v,'name':'Spoons'}];ledger=[]
def fixture(route):
 global create_loss,purchase_loss,held_a,edit_loss
 req=route.request;url=urlparse(req.url);path=url.path;query=parse_qs(url.query);data={}
 if path.endswith('/auth/me'):data={'id':'controlled','role':role,'campus_id':a,'profile':{'id':'controlled','role':role,'campus_id':a}}
 elif path.endswith('/campuses'):data=[{'id':a,'name':'Campus A','is_active':True},{'id':b,'name':'Campus B','is_active':True}]
 elif path.endswith('/measurement-units'):data=units
 elif path.endswith('/admin/stock-items'):
  if req.method=='GET':
   cid=query.get('campus_id',[None])[0]
   assert cid in (a,b),'Unscoped ingredient read';scope_reads.append(cid)
   if read_fail:route.fulfill(status=503,json={'error':'Controlled stock read failure'});return
   if cid==a and hold_a:held_a=route;return
   data=items[cid]
  else:
   body=req.post_data_json;writes.append(('create',body));cid=body['campus_id'];assert cid==b
   row=next((x for x in items[cid] if x['id']==body['request_id']),None)
   if row is None:row={**body,'id':body['request_id'],'current_balance':0};items[cid].append(row)
   if create_loss:create_loss=False;route.fulfill(status=503,json={'error':'Controlled committed create response loss'});return
   data=row
 elif '/stock-items/' in path and path.endswith('/ledger'):
  if ledger_fail:route.fulfill(status=503,json={'error':'Controlled ledger failure'});return
  full=ledger+[{'id':f'filler-{i}','type':'usage','quantity_entered':1,'quantity_in_usage_units':-1,'unit_id':v,'measurement_units':{'name':'Spoons'},'profiles':{'full_name':'Inventory operator'},'created_at':'2026-11-04T12:00:00Z'} for i in range(47)]
  offset=int(query.get('offset',['0'])[0]);limit=int(query.get('limit',['50'])[0]);data={'ledger':full[offset:offset+limit],'has_more':offset+limit<len(full)}
 elif '/stock-items/' in path and req.method=='PATCH':
  body=req.post_data_json;writes.append(('edit',body));row=items[b][0]
  assert set(body)=={'name','low_stock_threshold','expected'}
  if edit_conflict:route.fulfill(status=409,json={'error':'Controlled edit conflict'});return
  if row['name']!=body['name'] or row['low_stock_threshold']!=body['low_stock_threshold']:
   assert body['expected']=={key:row[key] for key in ('name','low_stock_threshold')}
   row.update({key:body[key] for key in ('name','low_stock_threshold')})
  if edit_loss:edit_loss=False;route.fulfill(status=503,json={'error':'Controlled committed edit response loss'});return
  data=row
 elif '/stock-items/' in path and req.method=='POST':
  kind=path.split('/')[-1];body=req.post_data_json;writes.append((kind,body));row=items[b][0];rid=body['request_id']
  if rid not in receipts:
   delta=body['quantity']*row['conversion_factor'] if kind=='purchase' else -body['quantity'];row['current_balance']+=delta
   entry={'id':rid,'type':'purchase' if kind=='purchase' else body['type'],'quantity_entered':body['quantity'],'quantity_in_usage_units':delta,'unit_id':u if kind=='purchase' else v,'measurement_units':{'name':'Bags' if kind=='purchase' else 'Spoons'},'cost':body.get('cost'),'notes':body.get('notes'),'profiles':{'full_name':'Inventory operator'},'created_at':'2026-11-04T12:00:00Z'}
   ledger.append(entry);receipts[rid]={'current_balance':row['current_balance']}
  if kind=='purchase' and purchase_loss:purchase_loss=False;route.fulfill(status=503,json={'error':'Controlled committed purchase response loss'});return
  data=receipts[rid]
 route.fulfill(status=200,json=data)
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5261','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api',npm_config_update_notifier='false'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
try:
 time.sleep(2)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);ctx=browser.new_context(viewport={'width':1280,'height':1000});ctx.route('**/api/**',fixture)
  ctx.add_init_script("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_role','super_admin');localStorage.setItem('hg_user_campus_id','"+a+"');localStorage.setItem('hg_admin_scope_all','1');")
  page=ctx.new_page();page.goto('http://127.0.0.1:5261/admin?section=store');page.get_by_role('button',name='Essential only',exact=True).click()
  expect(page.get_by_text('Select a campus to manage its ingredient stock.',exact=True)).to_be_visible()
  page.get_by_role('button',name='All Campuses',exact=True).click();page.get_by_role('button',name='Campus B',exact=True).click();page.get_by_role('button',name='Add First Item',exact=True).click()
  dialog=page.get_by_role('dialog');dialog.get_by_role('button',name='Add Item',exact=True).click();expect(dialog.get_by_text('Enter a name between 1 and 128 characters.',exact=True)).to_be_visible()
  dialog.get_by_label('Name',exact=True).fill('Beta ingredient');dialog.get_by_label('Usage Unit',exact=True).select_option(v);dialog.get_by_label('Purchase Unit',exact=True).select_option(u)
  dialog.get_by_label('Conversion Factor',exact=True).fill('0');dialog.get_by_role('button',name='Add Item',exact=True).click();expect(dialog.get_by_text('Conversion must be positive and the threshold must be non-negative.',exact=True)).to_be_visible()
  dialog.get_by_label('Conversion Factor',exact=True).fill('2');dialog.get_by_label('Low Stock Threshold',exact=True).fill('3');dialog.get_by_role('button',name='Add Item',exact=True).evaluate('(button) => { button.click(); button.click(); }');expect(dialog.get_by_text('Controlled committed create response loss',exact=True)).to_be_visible()
  dialog.get_by_role('button',name='Add Item',exact=True).click();expect(page.get_by_role('button',name='Beta ingredient',exact=True)).to_be_visible()
  creates=[x[1] for x in writes if x[0]=='create'];assert len(creates)==2 and creates[0]==creates[1] and len(items[b])==1
  page.get_by_role('button',name='Purchase',exact=True).click();dialog=page.get_by_role('dialog');dialog.get_by_label('Quantity',exact=True).fill('5');dialog.get_by_label('Cost (₦)',exact=True).fill('-2');dialog.get_by_role('button',name='Log Purchase',exact=True).click();expect(dialog.get_by_text('Enter a finite, non-negative cost.',exact=True)).to_be_visible()
  dialog.get_by_label('Cost (₦)',exact=True).fill('20');dialog.get_by_label('Notes (optional)',exact=True).fill('Receipt 01');dialog.get_by_role('button',name='Log Purchase',exact=True).evaluate('(button) => { button.click(); button.click(); }');expect(dialog.get_by_text('Controlled committed purchase response loss',exact=True)).to_be_visible()
  dialog.get_by_role('button',name='Log Purchase',exact=True).click();expect(page.get_by_role('dialog')).to_have_count(0)
  purchases=[x[1] for x in writes if x[0]=='purchase'];assert len(purchases)==2 and purchases[0]==purchases[1] and items[b][0]['current_balance']==10 and len(ledger)==1
  for kind,quantity,balance in [('Correction','-3',13),('Waste','2',11),('Usage','1',10)]:
   page.get_by_role('button',name='Usage',exact=True).click();dialog=page.get_by_role('dialog');dialog.get_by_role('button',name=kind,exact=True).click();dialog.get_by_label('Quantity',exact=True).fill(quantity)
   if kind=='Correction':expect(dialog.get_by_text('Positive corrections remove usage units;',exact=False)).to_be_visible()
   dialog.get_by_role('button',name='Log Usage',exact=True).click();expect(page.get_by_role('dialog')).to_have_count(0);assert items[b][0]['current_balance']==balance
  page.get_by_role('button',name='Purchase',exact=True).click();dialog=page.get_by_role('dialog');dialog.get_by_label('Quantity',exact=True).fill('0.5');dialog.get_by_role('button',name='Log Purchase',exact=True).click();expect(page.get_by_role('dialog')).to_have_count(0)
  assert [body for kind,body in writes if kind=='purchase'][-1]['cost'] is None
  page.get_by_role('button',name='Beta ingredient',exact=True).click();dialog=page.get_by_role('dialog');expect(dialog.get_by_text('Stock history could not be loaded.',exact=True)).to_be_visible();expect(dialog.get_by_text('No entries yet',exact=True)).to_have_count(0)
  ledger_fail=False;dialog.get_by_role('button',name='Retry',exact=True).click();expect(dialog.get_by_text('5 Bags',exact=True)).to_be_visible();expect(dialog.get_by_text('Balance change: +10 Spoons',exact=True)).to_be_visible();expect(dialog.get_by_text('Purchase cost: ₦20',exact=True)).to_be_visible()
  dialog.get_by_role('button',name='Next',exact=True).click();expect(dialog.get_by_text('Page 2',exact=True)).to_be_visible();expect(dialog.get_by_role('button',name='Next',exact=True)).to_be_disabled();dialog.get_by_role('button',name='Previous',exact=True).click();expect(dialog.get_by_text('Page 1',exact=True)).to_be_visible()
  dialog.get_by_role('button',name='Close dialog',exact=True).click()
  page.get_by_role('button',name='Campus B',exact=True).click();page.get_by_role('button',name='Campus A',exact=True).click();expect(page.get_by_role('dialog')).to_have_count(0);expect(page.get_by_role('button',name='Alpha ingredient',exact=True)).to_be_visible()
  hold_a=True;page.get_by_role('button',name='Campus A',exact=True).click();page.get_by_role('button',name='Campus B',exact=True).click();page.get_by_role('button',name='Campus B',exact=True).click();page.get_by_role('button',name='Campus A',exact=True).click()
  page.get_by_role('button',name='Campus A',exact=True).click();page.get_by_role('button',name='Campus B',exact=True).click();expect(page.get_by_role('button',name='Beta ingredient',exact=True)).to_be_visible();assert held_a is not None;held_a.fulfill(status=200,json=items[a]);expect(page.get_by_role('button',name='Alpha ingredient',exact=True)).to_have_count(0)
  read_fail=True;page.reload();expect(page.get_by_text("We couldn't load this page. Please try again.",exact=True)).to_be_visible();read_fail=False;page.get_by_role('button',name='Retry',exact=True).click();expect(page.get_by_role('button',name='Beta ingredient',exact=True)).to_be_visible()
  before=dict(items[b][0]);ledger_before=list(ledger)
  page.get_by_role('button',name='Edit ingredient',exact=True).click();dialog=page.get_by_role('dialog')
  expect(dialog.get_by_text('Units and conversion stay fixed',exact=False)).to_be_visible();expect(dialog.locator('select')).to_have_count(0)
  dialog.get_by_label('Name',exact=True).fill(' ');dialog.get_by_role('button',name='Save ingredient',exact=True).click();expect(dialog.get_by_role('alert')).to_have_text('Enter a name between 1 and 128 characters.')
  dialog.get_by_label('Name',exact=True).fill('Beta renamed');dialog.get_by_label('Low Stock Threshold',exact=True).fill('7.5')
  dialog.get_by_role('button',name='Save ingredient',exact=True).evaluate('(button) => { button.click(); button.click(); }');expect(dialog.get_by_role('alert')).to_have_text('Controlled committed edit response loss')
  dialog.get_by_role('button',name='Save ingredient',exact=True).click();expect(page.get_by_role('dialog')).to_have_count(0);expect(page.get_by_role('button',name='Beta renamed',exact=True)).to_be_visible()
  edits=[body for kind,body in writes if kind=='edit'];assert len(edits)==2 and edits[0]==edits[1]
  for key in ('current_balance','purchase_unit_id','usage_unit_id','conversion_factor'):assert items[b][0][key]==before[key]
  assert ledger==ledger_before
  edit_conflict=True;page.get_by_role('button',name='Edit ingredient',exact=True).click();dialog=page.get_by_role('dialog');dialog.get_by_label('Name',exact=True).fill('Must not save');dialog.get_by_role('button',name='Save ingredient',exact=True).click();expect(dialog.get_by_role('alert')).to_have_text('Controlled edit conflict');assert items[b][0]['name']=='Beta renamed';dialog.get_by_role('button',name='Close dialog',exact=True).click()
  ctx.close();hold_a=False;role='admin';ctx=browser.new_context(viewport={'width':1280,'height':1000});ctx.route('**/api/**',fixture)
  ctx.add_init_script("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_role','admin');localStorage.setItem('hg_user_campus_id','"+a+"');localStorage.setItem('hg_admin_campus_id','"+b+"');")
  page=ctx.new_page();page.goto('http://127.0.0.1:5261/admin?section=store');hold_a=False
  # A normal admin uses profile campus A despite a stale stored admin selector B.
  if held_a is not None and scope_reads[-1]==a:
   try:held_a.fulfill(status=200,json=items[a])
   except Exception:pass
  expect(page.get_by_role('button',name='Alpha ingredient',exact=True)).to_be_visible();assert scope_reads[-1]==a
  expect(page.get_by_role('button',name='All Campuses',exact=True)).to_have_count(0)
  ctx.close();browser.close()
 print('PASS: explicit campus and stale response isolation; create/purchase response-loss replay; finite inputs; signed correction/waste/usage; exact ledger units/cost/actor; ledger Retry/paging and stock read Retry; metadata replay, conflict and accounting preservation')
finally:
 os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
