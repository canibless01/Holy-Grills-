"""User directory/drawer/grants against controlled endpoints; no real accounts."""
import os,signal,subprocess,tempfile,time,uuid
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import sync_playwright,expect
repo=Path(__file__).resolve().parents[1];out=Path(tempfile.mkdtemp(prefix='hg-users-'))
a='11111111-1111-4111-8111-111111111111';b='22222222-2222-4222-8222-222222222222';actor='44444444-4444-4444-8444-444444444444'
role='super_admin';reads=[];hold=False;held=[];read_fail=False;wallet_fail=False;single_loss=True;bulk_loss=True;single_writes=[];bulk_writes=[];receipts={};errors=[];expiry_loss=True;expiry_writes=[];expiry_receipts={}
expect.set_options(timeout=15000)
users={c:[{'id':str(uuid.UUID(int=i+100+(0 if c==a else 1000))),'full_name':f'{label} member {i}','email':f'user-{i}@example.invalid','role':'student','campus_id':c,'is_active':True,'hp_balance':100,'wallet_balance':0,'created_at':'2026-11-05T12:00:00Z'} for i in range(25)] for c,label in ((a,'A'),(b,'B'))}
def member(uid):return next(u for group in users.values() for u in group if u['id']==uid)
def fixture(route):
 global single_loss,bulk_loss,expiry_loss
 req=route.request;url=urlparse(req.url);path=url.path;q=parse_qs(url.query);data={}
 if path.endswith('/auth/me'):data={'id':actor,'role':role,'campus_id':a,'profile':{'id':actor,'role':role,'campus_id':a}}
 elif path.endswith('/campuses'):data=[{'id':a,'name':'Campus A','is_active':True},{'id':b,'name':'Campus B','is_active':True}]
 elif path.endswith('/analytics/hp'):data={'hp_earned_active':100,'hp_spent':0,'tier_distribution':{}}
 elif path.endswith('/admin/users'):
  campus=q.get('campus_id',[None])[0];reads.append((campus,q));assert campus in (a,b)
  if read_fail:route.fulfill(status=503,json={'error':'Controlled directory failure'});return
  if hold and campus==a:held.append(route);return
  rows=users[campus]
  if q.get('q'):rows=[u for u in rows if q['q'][0].lower() in u['full_name'].lower() or q['q'][0].lower() in u['email'].lower()]
  if q.get('role'):rows=[u for u in rows if u['role']==q['role'][0]]
  offset=int(q.get('offset',['0'])[0]);limit=int(q.get('limit',['24'])[0]);data=rows[offset:offset+limit]
 elif path.endswith('/hp/admin/expire'):
  body=req.post_data_json;expiry_writes.append(body);u=member(body['user_id']);rid=body['request_id'];assert set(body)=={'user_id','amount','expected_balance','notes','request_id'}
  if rid in expiry_receipts:
   saved=expiry_receipts[rid];assert saved['body']==body;data={'success':True,'replayed':True,'expired':saved['expired'],'new_balance':u['hp_balance']}
  else:
   if u['hp_balance']!=body['expected_balance']:route.fulfill(status=409,json={'error':'Controlled expiry balance changed'});return
   remove=body['amount'] if body['amount'] is not None else u['hp_balance'];assert 0<remove<=u['hp_balance'];u['hp_balance']-=remove;expiry_receipts[rid]={'body':body,'expired':remove}
   if expiry_loss:expiry_loss=False;u['hp_balance']+=10;route.fulfill(status=503,json={'error':'Controlled committed expiry response loss'});return
   data={'success':True,'replayed':False,'expired':remove,'new_balance':u['hp_balance']}
 elif path.endswith('/hp/admin/grant'):
  body=req.post_data_json;single_writes.append(body);key=('single',body['grant_id'],body['user_id']);u=member(body['user_id'])
  replay=key in receipts
  if not replay:u['hp_balance']+=body['amount'];receipts[key]=dict(body)
  else:assert receipts[key]==body
  if single_loss:single_loss=False;route.fulfill(status=503,json={'error':'Controlled committed single grant response loss'});return
  data={'amount':body['amount'],'awarded':0 if replay else body['amount'],'replayed':replay,'new_balance':u['hp_balance']}
 elif path.endswith('/admin/hp/bulk-grant'):
  body=req.post_data_json;bulk_writes.append(body);assert body['campus_id']==a
  if body['dry_run']:data={'grant_id':body['grant_id'],'matched_count':len(body['user_ids'])}
  else:
   awarded=0;replayed=0
   for uid in body['user_ids']:
    key=('bulk',body['grant_id'],uid)
    if key in receipts:replayed+=1
    else:member(uid)['hp_balance']+=body['amount'];receipts[key]=body;awarded+=1
    if bulk_loss:bulk_loss=False;route.fulfill(status=503,json={'error':'Controlled partial bulk response loss'});return
   data={'awarded_count':awarded,'already_granted_count':replayed,'failed_count':0,'skipped_user_ids':[]}
 elif '/admin/users/' in path:
  parts=path.split('/');uid=parts[parts.index('users')+1];u=member(uid)
  if path.endswith('/role'):u['role']=req.post_data_json['role'];data=u
  elif path.endswith('/deactivate'):u['is_active']=False;data=u
  elif path.endswith('/activate'):u['is_active']=True;data=u
  elif path.endswith('/hp'):data={'active':u['hp_balance'],'total_visible':u['hp_balance'],'pending':0,'transactions':[]}
  elif path.endswith('/wallet'):
   if wallet_fail:route.fulfill(status=503,json={'error':'Controlled wallet history failure'});return
   data={'balance':1000,'transactions':[]}
  elif path.endswith('/orders'):data={'orders':[]}
  else:data={'profile':u}
 route.fulfill(status=200,json=data)
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5264','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
try:
 time.sleep(2)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);ctx=browser.new_context(viewport={'width':1280,'height':1000});ctx.route('**/api/**',fixture)
  ctx.add_init_script("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_role','super_admin');localStorage.setItem('hg_user_campus_id','"+a+"');if(!localStorage.getItem('hg_admin_campus_id'))localStorage.setItem('hg_admin_campus_id','"+a+"');")
  page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto('http://127.0.0.1:5264/admin?section=users');expect(page.get_by_text('A member 0',exact=True)).to_be_visible();assert reads[-1][0]==a
  page.get_by_text('A member 0',exact=True).click();drawer=page.get_by_role('dialog',name='A member 0',exact=True);expect(drawer).to_be_visible()
  wallet_fail=True;drawer.get_by_role('button',name='Wallet',exact=True).click();expect(drawer.get_by_role('alert')).to_contain_text('This history could not be loaded.')
  wallet_fail=False;drawer.get_by_role('button',name='Retry',exact=True).click();expect(drawer.get_by_role('alert')).to_have_count(0)
  drawer.get_by_role('button',name='Grant HP',exact=True).click();dialog=page.get_by_role('dialog',name='Grant HP — A member 0',exact=True)
  dialog.get_by_label('HP amount',exact=True).fill('-1');dialog.get_by_role('button',name='Grant HP',exact=True).click();expect(dialog.get_by_role('alert')).to_contain_text('Enter a whole HP amount')
  dialog.get_by_label('HP amount',exact=True).fill('75');dialog.get_by_label('Grant reason',exact=True).fill('Browser controlled grant');dialog.get_by_role('button',name='Grant HP',exact=True).evaluate('(b)=>{b.click();b.click()}');expect(dialog.get_by_role('alert')).to_have_text('Controlled committed single grant response loss')
  dialog.get_by_role('button',name='Grant HP',exact=True).click();expect(dialog).to_have_count(0);assert len(single_writes)==2 and single_writes[0]==single_writes[1] and users[a][0]['hp_balance']==175
  drawer.get_by_role('button',name='Close profile',exact=True).click();expect(drawer).to_have_count(0)
  page.locator('select[title="Change role"]').first.select_option('kitchen');expect(page.locator('select[title="Change role"]').first).to_have_value('kitchen');assert users[a][0]['role']=='kitchen'
  page.get_by_title('Deactivate account',exact=True).first.click();page.get_by_role('button',name='Deactivate',exact=True).click();expect(page.get_by_title('Reactivate account',exact=True).first).to_be_visible();assert users[a][0]['is_active'] is False
  page.get_by_title('Reactivate account',exact=True).first.click();expect(page.get_by_title('Reactivate account',exact=True)).to_have_count(0);assert users[a][0]['is_active'] is True
  page.get_by_role('button',name='Bulk',exact=True).click();page.get_by_role('button',name='Select A member 0',exact=True).click();page.get_by_role('button',name='Next',exact=True).click();expect(page.get_by_text('A member 24',exact=True)).to_be_visible();page.get_by_role('button',name='Select A member 24',exact=True).click();page.get_by_role('button',name='Grant HP (2)',exact=True).click()
  dialog=page.get_by_role('dialog',name='Bulk HP Grant',exact=True);expect(dialog.get_by_text('A member 0',exact=True)).to_be_visible();expect(dialog.get_by_text('A member 24',exact=True)).to_be_visible();expect(dialog.get_by_role('button',name='Grant 50 HP',exact=True)).to_be_disabled()
  dialog.get_by_role('button',name='Preview (no HP awarded)',exact=True).click();expect(dialog.get_by_role('button',name='Grant 50 HP',exact=True)).to_be_enabled();assert users[a][0]['hp_balance']==175 and users[a][24]['hp_balance']==100
  dialog.get_by_role('button',name='Grant 50 HP',exact=True).evaluate('(b)=>{b.click();b.click()}');expect(dialog.get_by_role('alert')).to_have_text('Controlled partial bulk response loss');dialog.get_by_role('button',name='Grant 50 HP',exact=True).click();expect(dialog).to_have_count(0)
  assert len(bulk_writes)==3 and len({b['grant_id'] for b in bulk_writes})==1 and bulk_writes[1]==bulk_writes[2] and users[a][0]['hp_balance']==225 and users[a][24]['hp_balance']==150
  page.get_by_role('button',name='Exit bulk',exact=True).click();hold=True;page.get_by_label('Search by name, phone or email…',exact=True).fill('A member');page.wait_for_timeout(400);assert held
  page.get_by_role('button',name='Campus A',exact=True).click();page.get_by_role('button',name='Campus B',exact=True).click();expect(page.get_by_text('B member 0',exact=True)).to_be_visible();assert reads[-1][0]==b
  for route in held:route.fulfill(status=200,json=users[a][:1])
  expect(page.get_by_text('A member 0',exact=True)).to_have_count(0)
  read_fail=True;page.reload();expect(page.get_by_text("We couldn't load this page. Please try again.",exact=True)).to_be_visible();read_fail=False;page.get_by_role('button',name='Retry',exact=True).click();expect(page.get_by_text('B member 0',exact=True)).to_be_visible()
  hold=False;page.get_by_role('button',name='Campus B',exact=True).click();page.get_by_role('button',name='Campus A',exact=True).click()
  page.goto('http://127.0.0.1:5264/admin?section=hp');expect(page.get_by_label('Grant recipient',exact=True)).to_be_visible();assert reads[-1][0]==a
  page.get_by_label('Grant recipient',exact=True).select_option(users[a][1]['id']);page.get_by_label('HP amount',exact=True).fill('20');page.get_by_label('Grant reason',exact=True).fill('Programme browser grant');single_loss=True
  page.get_by_role('button',name='Grant to user',exact=True).evaluate('(b)=>{b.click();b.click()}');expect(page.get_by_text('✕ Controlled committed single grant response loss',exact=True)).to_be_visible()
  page.get_by_role('button',name='Grant to user',exact=True).click();expect(page.get_by_text('This grant was already applied.',exact=True)).to_be_visible();assert len(single_writes)==4 and single_writes[2]==single_writes[3] and users[a][1]['hp_balance']==120
  page.get_by_label('Deduction recipient',exact=True).select_option(users[a][1]['id']);page.get_by_label('HP to remove (blank for all active HP)',exact=True).fill('25');page.get_by_label('Deduction reason',exact=True).fill('Controlled expiry')
  expect(page.get_by_role('button',name='Confirm removal of 25 HP',exact=True)).to_have_count(0);page.get_by_role('button',name='Preview deduction',exact=True).click();expect(page.get_by_role('button',name='Confirm removal of 25 HP',exact=True)).to_be_visible()
  page.get_by_role('button',name='Confirm removal of 25 HP',exact=True).evaluate('(b)=>{b.click();b.click()}');expect(page.get_by_text('✕ Controlled committed expiry response loss',exact=True)).to_be_visible();assert users[a][1]['hp_balance']==105
  page.get_by_role('button',name='Confirm removal of 25 HP',exact=True).click();expect(page.get_by_text('This deduction was already applied. Current balance: 105 HP.',exact=True)).to_be_visible();assert len(expiry_writes)==2 and expiry_writes[0]==expiry_writes[1] and users[a][1]['hp_balance']==105
  page.get_by_label('HP to remove (blank for all active HP)',exact=True).fill('');page.get_by_role('button',name='Preview deduction',exact=True).click();expect(page.get_by_role('button',name='Confirm removal of 105 HP',exact=True)).to_be_visible();users[a][1]['hp_balance']+=5
  page.get_by_role('button',name='Confirm removal of 105 HP',exact=True).click();expect(page.get_by_text('✕ Controlled expiry balance changed',exact=True)).to_be_visible();assert users[a][1]['hp_balance']==110
  page.get_by_role('button',name='Preview deduction',exact=True).click();page.get_by_role('button',name='Confirm removal of 110 HP',exact=True).click();expect(page.get_by_text('110 HP removed. Current balance: 0 HP.',exact=True)).to_be_visible();assert users[a][1]['hp_balance']==0 and len(expiry_receipts)==2
  ctx.close()
  role='admin';hold=False;ctx=browser.new_context(viewport={'width':1280,'height':1000});ctx.route('**/api/**',fixture);ctx.add_init_script("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_role','admin');localStorage.setItem('hg_user_campus_id','"+a+"');localStorage.setItem('hg_admin_campus_id','"+b+"');")
  page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto('http://127.0.0.1:5264/admin?section=users');expect(page.get_by_text('A member 0',exact=True)).to_be_visible();assert reads[-1][0]==a;expect(page.locator('select[title="Change role"]').first.get_by_role('option',name='Super Admin',exact=True)).to_have_count(0)
  ctx.close();browser.close();assert not errors,errors
 print('PASS: directory campus/stale reply isolation; drawer failed history Retry; single grant validation/latch/response-loss identity; role/active reflection; cross-page bulk names, preview, partial-loss safe retry; regular-admin role restrictions; HP programme grant identity/replay; expiry preview/latch/replay, late earning preservation, stale balance refusal and all-mode confirmation')
finally:
 os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
