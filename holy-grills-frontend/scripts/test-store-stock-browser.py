"""Real mobile/desktop controls; controlled transport, no production writes."""
import json, os
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('HG_BROWSER_BASE','http://127.0.0.1:4185')
C='11111111-1111-4111-8111-111111111111';U='22222222-2222-4222-8222-222222222222';S='33333333-3333-4333-8333-333333333333';I='44444444-4444-4444-8444-444444444444'
with sync_playwright() as p:
 b=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);expect.set_options(timeout=12000)
 for role,width in [('admin',393),('admin',1280),('kitchen',393)]:
  ctx=b.new_context(viewport={'width':width,'height':950});state={'classified':role=='kitchen','total':100,'store':60 if role=='kitchen' else 0,'lost':True};calls=[];errors=[]
  values={'hg_access_token':'controlled','hg_user_role':role,'hg_campus_id':C,'hg_user_campus_id':C,'hg_admin_campus_id':C,'hg_cookie_consent':json.dumps({'essential':True,'analytics':False,'date':'2026-11-25'})}
  ctx.add_init_script('for(const[k,v]of Object.entries('+json.dumps(values)+'))localStorage.setItem(k,v);')
  stores=[{'id':S,'campus_id':C,'name':'North counter','is_active':True,'address':'North road','pickup_enabled':True,'delivery_enabled':True}]
  def item():return {'id':I,'name':'Takeaway containers','campus_id':C,'current_balance':state['total'],'central_balance':state['total']-state['store'],'allocated_balance':state['store'],'store_balance':state['store'],'store_distributable':state['classified'],'usage_unit':'pieces','conversion_factor':1,'purchase_unit_id':I,'usage_unit_id':I,'low_stock_threshold':2}
  def api(route):
   req=route.request;path=urlparse(req.url).path;data=[]
   if path.endswith('/auth/me'):data={'id':U,'role':role,'campus_id':C,'is_active':True,'full_name':'Controlled operator','phone':'08012345678'}
   elif path.endswith('/campuses'):data=[{'id':C,'name':'FUTA','is_active':True}]
   elif path.endswith('/feature-flags'):data=[{'feature_name':'multi_store_ordering','is_active':True}]
   elif path.endswith('/admin/stores') or path.endswith('/admin/work-stores'):data={'stores':stores,'ordering_enabled':True}
   elif path.endswith('/admin/store-stock'):
    if req.method=='POST':
     body=req.post_data_json;calls.append(body)
     if body['action']=='classify':state['classified']=body['distributable']
     elif body['action']=='transfer':
      if state['lost']:
       state['store']+=body['quantity'];state['lost']=False;route.fulfill(status=503,json={'error':'Controlled lost response; retry same movement'});return
      assert body==calls[-2],calls
     elif body['action']=='usage':state['store']-=body['quantity'];state['total']-=body['quantity']
     data={'saved':True}
    else:
     row=item()
     if role=='kitchen':row={k:v for k,v in row.items() if k not in ('current_balance','central_balance','allocated_balance')}
     data={'entries':[]} if 'history' in req.url else {'items':[row]}
   elif path.endswith('/admin/stock-items'):data=[item()]
   elif path.endswith('/measurement-units'):data=[{'id':I,'name':'pieces'}]
   elif path.endswith('/kitchen/scheduled'):data={'count':0,'scheduled_orders':[]}
   elif path.endswith('/kitchen/handoff'):data={'batches':[],'riders':[]}
   elif path.endswith('/kitchen/settings'):data={}
   elif path.endswith('/notifications'):data={'notifications':[],'unread_count':0}
   elif 'window-status' in path or 'capacity' in path:data={'is_open':True,'remaining':50}
   elif req.method!='GET':data={}
   route.fulfill(status=200,json=data)
  ctx.route('**/api/**',api);page=ctx.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
  page.goto(BASE+('/kitchen' if role=='kitchen' else '/admin?section=store'),wait_until='domcontentloaded')
  page.get_by_role('button',name='Central kitchen & store supplies',exact=True).click()
  expect(page.get_by_role('heading',name='Supply desk',exact=True)).to_be_visible()
  location=page.get_by_label('Stock location',exact=True)
  if role=='admin':
   page.get_by_text('Tracking settings',exact=True).click()
   page.get_by_label('Allocate this item to stores',exact=True).click();page.get_by_role('button',name='Transfer stock',exact=True).click()
   dialog=page.get_by_role('dialog');dialog.get_by_label('Quantity in usage units',exact=True).fill('60');dialog.get_by_label('Reason / dispatch note',exact=True).fill('Dispatch to counter')
   dialog.get_by_role('button',name='Record movement',exact=True).click();expect(dialog.get_by_role('alert')).to_contain_text('Controlled lost response')
   dialog.get_by_role('button',name='Record movement',exact=True).click();expect(dialog).to_have_count(0);assert state['total']==100 and state['store']==60
   location.select_option(S)
   expect(page.get_by_role('button',name='Usage',exact=True)).to_be_visible()
  else:
   expect(location).to_have_value(S);expect(page.get_by_role('button',name='Transfer stock',exact=True)).to_have_count(0)
   expect(page.get_by_text('Campus total',exact=True)).to_have_count(0)
  page.get_by_role('button',name='Usage',exact=True).click();dialog=page.get_by_role('dialog');dialog.get_by_label('Quantity in usage units',exact=True).fill('5');dialog.get_by_label('Reason / dispatch note',exact=True).fill('Five orders served')
  dialog.get_by_role('button',name='Record movement',exact=True).click();expect(dialog).to_have_count(0)
  assert calls[-1]['store_id']==S and calls[-1]['action']=='usage' and state['store']==55 and state['total']==95
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(role,width)
  assert not errors,errors
  page.wait_for_timeout(5200)
  page.screenshot(path=f'/workspace/work/multi-store/stock-{role}-{width}.png',full_page=True);print(json.dumps({'role':role,'width':width,'passed':True}),flush=True);ctx.close()
 b.close()
