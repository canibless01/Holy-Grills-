"""Native campaign editor and customer claim card; controlled HTTP only."""
import json, os, signal, subprocess, tempfile, time
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect

repo=Path(__file__).resolve().parents[1]; out=Path(tempfile.mkdtemp(prefix='hg-gift-campaign-'))
c='11111111-1111-4111-8111-111111111111'; config=None; stamp=None; history=[]; saves=[]; claims=[]; conflict=False
def fixture(route):
    global config,stamp,conflict
    req=route.request; path=urlparse(req.url).path; data={}
    if path.endswith('/auth/me'): data={'id':'controlled-admin','role':'admin','campus_id':c,'profile':{'id':'controlled-admin','role':'admin','campus_id':c}}
    elif path.endswith('/campuses'): data=[{'id':c,'name':'Controlled campus','is_active':True}]
    elif path.endswith('/admin/welcome-credit'): data={'config':{'enabled':True,'credits':1,'validity_days':60}}
    elif path.endswith('/admin/first-order-gifts'): data=[]
    elif path.endswith('/admin/gift-campaign'):
        if req.method=='PATCH':
            saves.append(req.post_data_json)
            if conflict:
                route.fulfill(status=409,json={'error':'This campaign changed. Reload it before saving.'});return
            config=req.post_data_json['config'];stamp='stamp-'+str(len(saves))
            for item in config['benefits']: item['label']=item['kind']+' gift'
        data={'config':config or {'id':None,'name':'','enabled':False,'eligibility':'first_order','starts_at':None,'ends_at':None,'validity_days':60,'benefits':[]},'updated_at':stamp,'inherited':False}
    elif path.endswith('/storefront/gift-campaign'):data={'campaign':config}
    elif path.endswith('/rewards/gift-campaign'):
        if req.method=='POST':
            claims.append(req.post_data_json)
            history.append({'id':'controlled-receipt','prize_name':config['name'],'result_snapshot':{'campaign_id':config['id'],'benefits':config['benefits'],'expires_at':'2099-01-01T00:00:00Z'}})
            data={'granted':True,'receipt_id':'controlled-receipt'}
        else: data={'campaign':config,'history':history}
    elif path.endswith('/cart'): data={'items':[]}
    route.fulfill(status=200,json=data)
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5225','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
try:
    time.sleep(2)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        ctx=browser.new_context(viewport={'width':1280,'height':1000},timezone_id='America/New_York');ctx.route('**/api/**',fixture)
        ctx.add_init_script("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_campus_id','"+c+"');localStorage.setItem('hg_user_campus_id','"+c+"');localStorage.setItem('hg_admin_campus_id','"+c+"')")
        page=ctx.new_page();page.on('pageerror',lambda error:print(str(error)));page.goto('http://127.0.0.1:5225/admin?section=onboarding')
        page.get_by_role('button',name='Essential only',exact=True).click()
        panel=page.get_by_role('button',name='New campaign',exact=True).locator('..').locator('..')
        panel.get_by_label('Campaign name',exact=True).fill('Controlled launch gifts')
        panel.get_by_role('switch',name='Enable campaign',exact=True).click()
        panel.get_by_label('Who receives these gifts?',exact=True).select_option('everyone')
        panel.get_by_label('Campaign starts',exact=True).fill('2026-10-01T09:15')
        panel.get_by_label('Campaign ends',exact=True).fill('2026-11-01T22:00')
        for label in ('HP','Delivery discount','Food HP multiplier'):panel.get_by_label(label,exact=True).check()
        panel.get_by_label('Delivery discount (%)',exact=True).fill('50')
        panel.get_by_label('Maximum delivery discount (₦)',exact=True).fill('300')
        panel.get_by_role('button',name='Save campaign',exact=True).click()
        expect(page.get_by_text('Gift campaign saved',exact=True).first).to_be_visible()
        assert len(saves)==1 and len(saves[0]['config']['benefits'])==4
        assert saves[0]['config']['starts_at']=='2026-10-01T08:15:00.000Z'
        assert saves[0]['expected_updated_at'] is None
        first_id=saves[0]['config']['id']
        panel.get_by_label('Campaign name',exact=True).fill('Controlled edited gifts')
        panel.get_by_role('button',name='Save campaign',exact=True).click()
        page.wait_for_timeout(200)
        assert saves[-1]['config']['id']==first_id and saves[-1]['expected_updated_at']=='stamp-1'
        conflict=True
        panel.get_by_label('Campaign name',exact=True).fill('Stale draft')
        panel.get_by_role('button',name='Save campaign',exact=True).click()
        expect(panel.get_by_role('button',name='Reload campaign',exact=True)).to_be_visible()
        panel.get_by_role('button',name='Reload campaign',exact=True).click()
        expect(panel.get_by_label('Campaign name',exact=True)).to_have_value('Controlled edited gifts')
        page.goto('http://127.0.0.1:5225/faq')
        page.evaluate("""async()=>{const R=await import('/node_modules/.vite/deps/react.js');const React=R.default||R;const D=await import('/node_modules/.vite/deps/react-dom_client.js');const {default:Card}=await import('/src/components/GiftCampaignCard.tsx');document.getElementById('root').hidden=true;const host=document.createElement('div');document.body.append(host);(D.createRoot||D.default.createRoot)(host).render(React.createElement(Card,{onClaimed:()=>{window.giftRefresh=(window.giftRefresh||0)+1;throw Error('Controlled balance read outage')}}));}""")
        page.get_by_role('button',name='Claim gifts',exact=True).click()
        expect(page.get_by_role('button',name='Claimed',exact=True)).to_be_disabled()
        assert claims==[{'campaign_id':first_id}] and page.evaluate('window.giftRefresh')==1
        page.get_by_text('Claimed gift campaigns',exact=True).click()
        expect(page.get_by_text('Order benefits valid until',exact=False)).to_be_visible()
        config={**config,'name':'Changed after claim','benefits':[{'kind':'hp','amount':999,'label':'999 HP'}]}
        page.goto('http://127.0.0.1:5225/faq')
        page.evaluate("""async()=>{const R=await import('/node_modules/.vite/deps/react.js');const React=R.default||R;const D=await import('/node_modules/.vite/deps/react-dom_client.js');const {default:Card}=await import('/src/components/GiftCampaignCard.tsx');document.getElementById('root').hidden=true;const host=document.createElement('div');document.body.append(host);(D.createRoot||D.default.createRoot)(host).render(React.createElement(Card));}""")
        expect(page.get_by_role('heading',name='Controlled edited gifts',exact=True)).to_be_visible()
        expect(page.get_by_text('999 HP',exact=True)).to_have_count(0)
        page.goto('http://127.0.0.1:5225/faq')
        page.evaluate("""async()=>{const R=await import('/node_modules/.vite/deps/react.js');const React=R.default||R;const D=await import('/node_modules/.vite/deps/react-dom_client.js');const source=await(await fetch('/src/components/GiftCampaignTeaser.tsx')).text();const routerPath=source.match(/from \"([^\"]*react-router-dom[^\"]*)\"/)[1];const {MemoryRouter}=await import(routerPath);const {default:Teaser}=await import('/src/components/GiftCampaignTeaser.tsx');document.getElementById('root').hidden=true;const host=document.createElement('div');document.body.append(host);(D.createRoot||D.default.createRoot)(host).render(React.createElement(MemoryRouter,null,React.createElement(Teaser,{campusId:'11111111-1111-4111-8111-111111111111',authenticated:false})));}""")
        expect(page.get_by_role('heading',name='Changed after claim',exact=True)).to_be_visible()
        expect(page.get_by_role('link',name='See gifts',exact=True)).to_have_attribute('href','/signup')
        browser.close()
    print(json.dumps({'four_benefits_saved_with_lagos_dates':True,'edits_keep_campaign_identity':True,'stale_save_reload':True,'customer_claim_history_and_no_second_click':True,'balance_outage_preserves_success':True,'earned_display_survives_campaign_edits':True,'homepage_teaser_reads_saved_campaign':True}))
finally:os.killpg(proc.pid,signal.SIGTERM)
