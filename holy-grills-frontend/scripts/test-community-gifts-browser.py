"""Real gift components, controlled API, no provider sends or persisted accounts."""
import json,os,signal,subprocess,tempfile,time
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
html=ROOT/'.community-gift-audit.html';entry=ROOT/'.community-gift-audit.tsx'
entry.write_text('''import React,{useState} from 'react';import{createRoot}from'react-dom/client';import{MemoryRouter}from'react-router-dom';import{HolyGrillProvider}from'./src/lib/HolyGrillContext';import Birthday from'./src/components/wallet/BirthdayGiftPanel';import HP from'./src/components/HpTransferModal';import Cash from'./src/components/wallet/WalletTransferModal';import Receipt from'./src/components/wallet/HpGiftReceipt';import './src/index.css';function Demo(){const[p,S]=useState(null);const[k,K]=useState('');return <><Birthday code="FRIEND123" cashEnabled hpEnabled onCash={p=>{S(p);K('cash')}} onHp={p=>{S(p);K('hp')}}/>{k==='hp'&&<HP open initialRecipient={p} onClose={()=>K('')}/>} {k==='cash'&&<Cash initialRecipient={p} onClose={()=>K('')} onSuccess={()=>{}}/>}<button onClick={()=>K('receipt')}>Open received gift</button>{k==='receipt'&&<Receipt id="11111111-1111-4111-8111-111111111112" onClose={()=>K('')}/>}</>};createRoot(document.getElementById('root')).render(<MemoryRouter initialEntries={['/wallet']}><HolyGrillProvider><Demo/></HolyGrillProvider></MemoryRouter>);''')
html.write_text('<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module" src="/.community-gift-audit.tsx"></script></body></html>')
log=Path(tempfile.mkdtemp())/'vite.log';proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5281','--strictPort'],cwd=ROOT,env=dict(os.environ,VITE_API_BASE_URL='/api'),stdout=log.open('w'),stderr=subprocess.STDOUT,start_new_session=True)
OWNER='11111111-1111-4111-8111-111111111111';FRIEND='22222222-2222-4222-8222-222222222222'
try:
 time.sleep(2)
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);expect.set_options(timeout=15000)
  for width in (393,1280):
   state={'hp':[],'cash':[],'caps':True,'birthday_fail':True,'anon':False,'minimum':10};errors=[]
   def api(route):
    req=route.request;path=urlparse(req.url).path;data=[]
    if path.endswith('/auth/me'):data={'id':OWNER,'full_name':'Sender','role':'student','campus_id':OWNER,'is_active':True,'hp_balance':100,'wallet':{'balance':1000}}
    elif path.endswith('/hp/balance'):data={'active':100,'pending':0}
    elif path.endswith('/wallet'):data={'balance':1000}
    elif path.endswith('/hp/birthday-recipient'):
     if state['birthday_fail']:
      state['birthday_fail']=False;route.fulfill(status=503,json={'error':'Birthday list temporarily unavailable'});return
     data={'recipient':{'id':FRIEND,'name':'Birthday Friend','code':'FRIEND123','department':'Computing'}}
    elif path.endswith('/hp/transfer-eligibility'):data={'eligible':True,'delivered_orders':2,'minimum_orders':1,'minimum_amount':state['minimum'],'gift_options_supported':state['caps']}
    elif path.endswith('/hp/transfer'):
     state['hp'].append(req.post_data_json)
     if len(state['hp'])==1:route.fulfill(status=503,json={'error':'Response interrupted','code':'transfer_uncertain'});return
     data={'amount':10,'recipient_name':'Birthday Friend','new_balance':90,'replayed':True}
    elif '/hp/transfers/' in path:data={'transfer':{'id':'receipt','amount':10,'direction':'received','sender_name':'Anonymous' if state['anon'] else 'Your Friend','note':'Birthday love','shared_contact':None if state['anon'] else {'phone':'+2348000000000'}}}
    elif path.endswith('/wallet/transfers'):
     if req.method=='POST':
      body=req.post_data_json;state['cash'].append(body);data={'transfer':{'id':body['request_id'],'amount':100,'direction':'sent','recipient_name':'Birthday Friend','status':'completed'}}
     else:data={'enabled':True,'available_balance':1000,'minimum_amount':1,'maximum_amount':10000,'daily_remaining':10000,'gift_options_supported':state['caps']}
    elif path.endswith('/messages'):data={'messages':{}}
    elif path.endswith('/cart'):data={'items':[]}
    route.fulfill(json=data)
   context=browser.new_context(viewport={'width':width,'height':900});context.add_init_script(f"sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_role','student');localStorage.setItem('hg_user_campus_id','{OWNER}');");context.route('**/api/**',api)
   page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto('http://127.0.0.1:5281/.community-gift-audit.html')
   expect(page.get_by_role('alert')).to_contain_text('temporarily unavailable');page.get_by_role('button',name='Retry',exact=True).click()
   page.get_by_role('button',name='Send HP',exact=True).click();dialog=page.get_by_role('dialog');expect(dialog.get_by_text('Ready to send HP',exact=False)).to_be_visible()
   dialog.get_by_role('button',name='10',exact=True).click();anon=dialog.get_by_label('Send anonymously',exact=False);phone=dialog.get_by_label('Share my registered',exact=False)
   phone.check();anon.check();expect(phone).not_to_be_checked();expect(phone).to_be_disabled()
   dialog.get_by_role('button',name='Send 10 HP',exact=False).click();expect(dialog.get_by_text('Response interrupted')).to_be_visible();first=state['hp'][0]
   assert first['anonymous'] is True and first['share_contact'] is False and first['recipient_id']==FRIEND
   page.reload();page.get_by_role('button',name='Send HP',exact=True).click();dialog=page.get_by_role('dialog');expect(dialog.get_by_text('A response may have been lost.',exact=False)).to_be_visible()
   dialog.get_by_role('button',name='Send 10 HP',exact=False).click();expect(dialog.get_by_text('10 HP sent!',exact=False)).to_be_visible();assert state['hp'][1]==first
   dialog.get_by_role('button',name='Done',exact=True).click()
   page.get_by_role('button',name='Open received gift').click();dialog=page.get_by_role('dialog');expect(dialog.get_by_role('link',name='Call to say thank you',exact=False)).to_have_attribute('href','tel:+2348000000000');dialog.get_by_role('button',name='Close dialog',exact=True).click()
   state['anon']=True;page.get_by_role('button',name='Open received gift').click();dialog=page.get_by_role('dialog');expect(dialog.get_by_text('From Anonymous')).to_be_visible();expect(dialog.get_by_role('link')).to_have_count(0);dialog.get_by_role('button',name='Close dialog',exact=True).click()
   page.get_by_role('button',name='Send wallet money',exact=True).click();dialog=page.get_by_role('dialog');expect(dialog.get_by_text('Birthday Friend',exact=True)).to_be_visible();dialog.get_by_label('Amount (₦)').fill('100');dialog.get_by_label('Share my registered',exact=False).check();dialog.get_by_role('button',name='Review transfer').click();expect(dialog.get_by_text('Your name and registered phone number will be shared.')).to_be_visible();dialog.get_by_role('button',name='Send ₦100',exact=False).click();expect(dialog.get_by_text('Sent successfully')).to_be_visible();assert state['cash'][-1]['share_contact'] is True and state['cash'][-1]['anonymous'] is False and state['cash'][-1]['recipient_id']==FRIEND;dialog.get_by_role('button',name='Done',exact=True).click()
   state['caps']=False;state['minimum']=25;page.get_by_role('button',name='Send HP',exact=True).click();dialog=page.get_by_role('dialog');expect(dialog.get_by_text('Ready to send HP',exact=False)).to_be_visible();expect(dialog.get_by_label('Send anonymously',exact=False)).to_have_count(0);expect(dialog.get_by_text('Amount (min 25 HP)',exact=True)).to_be_visible();dialog.get_by_role('button',name='10',exact=True).click();expect(dialog.get_by_role('button',name='Send 10 HP',exact=False)).to_be_disabled();dialog.get_by_role('button',name='25',exact=True).click();expect(dialog.get_by_role('button',name='Send 25 HP',exact=False)).to_be_enabled()
   assert not errors,errors;context.close();print(f'PASS {width}: birthday retry/prefill, explicit anonymity/contact, uncertain gift retry after reload uses same intent, owned named/anonymous receipts, cash birthday gift review/send, old-backend capability gate',flush=True)
  browser.close()
finally:
 os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10);html.unlink(missing_ok=True);entry.unlink(missing_ok=True)
