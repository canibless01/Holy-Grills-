"""Wallet ledger and cart history browsing, error/retry and obsolete-response checks."""
import json,os
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('HG_BROWSER_BASE','http://127.0.0.1:4185');A='11111111-1111-4111-8111-111111111111';U='22222222-2222-4222-8222-222222222222'
expect.set_options(timeout=20000)
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for section in ('wallet','abandoned'):
  for width in (393,1280):
   state={'fail':True,'reads':[],'hold':False,'held':[],'empty':False};errors=[]
   ctx=browser.new_context(viewport={'width':width,'height':1000});ctx.add_init_script(f"localStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_role','admin');localStorage.setItem('hg_user_campus_id','{A}');localStorage.setItem('hg_cookie_consent',JSON.stringify({{essential:true,analytics:false,date:new Date().toISOString()}}));")
   def api(route):
    req=route.request;path=urlparse(req.url).path;query=parse_qs(urlparse(req.url).query);data={}
    if path.endswith('/auth/me'):data={'id':U,'full_name':'Fixture admin','role':'admin','campus_id':A}
    elif path.endswith('/campuses'):data=[{'id':A,'name':'Campus A','is_active':True}]
    elif path.endswith('/wallet/admin/transactions') or path.endswith('/admin/abandoned-carts'):
     assert req.method=='GET' and req.headers.get('x-campus-id')==A;state['reads'].append(query)
     if state['fail']:route.fulfill(status=503,json={'error':'Controlled read outage'});return
     offset=int(query.get('offset',['0'])[0]);limit=int(query.get('limit',['25'])[0]);assert limit==25
     data=[] if state['empty'] else [{'id':f'fixture-{i}','description':f'Transaction {i}','full_name':f'Person {i}','amount':i+1,'type':query.get('type',['credit'])[0],'reference':f'REF-{i}','created_at':'2026-11-15T10:00:00Z','user_id':U,'profiles':{'full_name':f'Person {i}','email':f'person{i}@example.invalid'},'is_recovered':query.get('status',['all'])[0]=='recovered','subtotal':i+1} for i in range(offset,min(offset+limit,126))]
     if state['hold']:state['held'].append((route,data));return
    elif '/notifications' in path:data={'notifications':[]}
    elif 'cart' in path:data={'items':[]}
    elif any(x in path for x in ('orders','feature-flags','tiers','ambassadors','sections','banners')):data=[]
    route.fulfill(status=200,json=data)
   ctx.route('**/api/**',api);ctx.route('https://*.onesignal.com/**',lambda r:r.abort());page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto(BASE+'/admin?section='+section,wait_until='domcontentloaded')
   expect(page.get_by_role('alert').filter(has_text='Wallet transactions could not be loaded.' if section=='wallet' else 'Controlled read outage')).to_be_visible();assert not page.get_by_text('No wallet transactions found' if section=='wallet' else 'No abandoned carts found.',exact=True).count();state['fail']=False
   page.get_by_role('button',name='Retry transactions' if section=='wallet' else 'Refresh carts',exact=True).click();expect(page.get_by_text('Person 0',exact=True)).to_be_visible()
   if section=='wallet':
    page.get_by_text('Transaction 0',exact=True).click();expect(page.get_by_text('REF-0',exact=True)).to_be_visible();page.get_by_text('Transaction 0',exact=True).click()
   # Reach records beyond the old fixed first-100 request.
   for index in range(1,6):
    page.get_by_role('button',name='Next',exact=True).click();expect(page.get_by_text(f'Person {index*25}',exact=True)).to_be_visible()
   expect(page.get_by_role('button',name='Next',exact=True)).to_be_disabled();assert state['reads'][-1]['offset']==['125']
   state['fail']=True;page.get_by_role('button',name='Prev',exact=True).click();expect(page.get_by_role('alert')).to_be_visible();assert state['reads'][-1]['offset']==['100'];state['fail']=False;page.get_by_role('button',name='Retry transactions' if section=='wallet' else 'Refresh carts',exact=True).click();expect(page.get_by_text('Person 100',exact=True)).to_be_visible();assert state['reads'][-1]['offset']==['100']
   # Concurrent deletion / changed history can empty a later page: Previous remains usable.
   state['empty']=True;page.get_by_role('button',name='Refresh' if section=='wallet' else 'Refresh carts',exact=True).click();expect(page.get_by_text('No wallet transactions found' if section=='wallet' else 'No abandoned carts found.',exact=True)).to_be_visible();expect(page.get_by_role('button',name='Prev',exact=True)).to_be_enabled();state['empty']=False;page.get_by_role('button',name='Prev',exact=True).click();expect(page.get_by_text('Person 75',exact=True)).to_be_visible()
   if section=='wallet':
    state['hold']=True;page.get_by_role('button',name='Credit',exact=True).click();page.get_by_role('button',name='Debit',exact=True).click()
    for _ in range(100):
     if len(state['held'])>=2:break
     page.wait_for_timeout(100)
    assert len(state['held'])>=2
    state['held'][-1][0].fulfill(status=200,json=state['held'][-1][1]);expect(page.get_by_text('Person 0',exact=True)).to_be_visible()
    for route,data in state['held'][:-1]:route.fulfill(status=200,json=data)
    expect(page.get_by_text('−₦1',exact=True)).to_be_visible();assert state['reads'][-1]['type']==['debit'] and state['reads'][-1]['offset']==['0']
   else:
    search=page.get_by_label('Search this page by name or email',exact=True);search.fill('Person 75');expect(page.get_by_text('Person 76',exact=True)).to_have_count(0);page.get_by_role('button',name='Prev',exact=True).click();expect(search).to_have_value('');expect(page.get_by_text('Person 50',exact=True)).to_be_visible();page.get_by_label('Cart recovery status',exact=True).select_option('recovered');expect(page.get_by_text('Person 0',exact=True)).to_be_visible();assert state['reads'][-1]['offset']==['0']
   assert not errors,errors;assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');ctx.close();print(json.dumps({'section':section,'width':width,'passed':True,'writes':0}),flush=True)
 browser.close()
