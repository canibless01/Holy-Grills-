"""Native kitchen/rider/map components; controlled HTTP and GPS, no remote writes."""
import json, os, signal, subprocess, tempfile, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright, expect

repo=Path(__file__).resolve().parents[1]; out=Path(tempfile.mkdtemp(prefix='hg-handoff-'))
c='11111111-1111-4111-8111-111111111111'; b='22222222-2222-4222-8222-222222222222'; r='33333333-3333-4333-8333-333333333333'
today=datetime.now(timezone(timedelta(hours=1))).date().isoformat(); writes=[]
order={'id':'44444444-4444-4444-8444-444444444444','status':'ready','payment_status':'paid','customer_name':'Controlled customer','order_items':[{'name_snapshot':'Controlled meal','quantity':1}]}
batch={'id':b,'status':'open','rider_id':None,'zone':'Controlled gate','delivery_date':today,'orders':[order]}
def fixture(route):
    req=route.request; path=urlparse(req.url).path; data={}
    if path.endswith('/auth/me'): data={'id':'controlled-kitchen','role':'kitchen','campus_id':c,'profile':{'id':'controlled-kitchen','role':'kitchen','campus_id':c}}
    elif path.endswith('/campuses'): data=[{'id':c,'name':'Controlled campus','is_active':True}]
    elif path.endswith('/kitchen/handoff'): data={'batches':[batch],'riders':[{'id':r,'full_name':'Controlled rider'}]}
    elif path.endswith('/kitchen/handoff/'+b+'/assign'):
        writes.append(req.post_data_json);batch.update(status='assigned',rider_id=r);data={'id':b,'status':'assigned','rider_id':r}
    elif path.endswith('/kitchen/queue'): data=[]
    elif path.endswith('/kitchen/scheduled'):
        date=parse_qs(urlparse(req.url).query).get('date',[today])[0]
        data={'date':date,'count':1,'scheduled_orders':[{**order,'status':'received','scheduled_for':date+'T19:30:00+01:00'}]}
    elif path.endswith('/kitchen/windows'): data=[]
    elif path.endswith('/riders/my-batch'):
        data={'batch':{'id':b,'status':'assigned'},'orders':[{'id':order['id'],'status':'assigned','delivery_address':{'line1':'Controlled junction'},'delivery_location_lat':6.51,'delivery_location_lon':3.38,'items':[{'name_snapshot':'Controlled meal','quantity':1}]}]}
    elif path.endswith('/cart'): data={'items':[]}
    route.fulfill(status=200,json=data)
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5223','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
try:
    time.sleep(2)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        ctx=browser.new_context(viewport={'width':390,'height':844});ctx.route('**/api/**',fixture)
        ctx.route('https://www.google.com/maps/**',lambda route:route.fulfill(status=200,body='Controlled directions destination'))
        ctx.route('https://*.tile.openstreetmap.org/**',lambda route:route.abort())
        ctx.add_init_script("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_campus_id','"+c+"');localStorage.setItem('hg_user_campus_id','"+c+"');Object.defineProperty(navigator,'geolocation',{value:{watchPosition:()=>1,clearWatch:()=>{},getCurrentPosition:success=>success({coords:{latitude:7.3,longitude:5.2,accuracy:5}})}})")
        page=ctx.new_page();page.goto('http://127.0.0.1:5223/kitchen')
        page.get_by_role('button',name='Essential only',exact=True).click()
        page.get_by_role('button',name='Scheduled',exact=True).click()
        expect(page.get_by_label('Preparation date',exact=True)).to_have_value(today)
        page.get_by_label('Preparation date',exact=True).fill('2099-01-01')
        expect(page.get_by_role('button',name='Promote to Preparing',exact=True)).to_be_disabled()
        expect(page.get_by_text('Future orders are shown for planning only. Preparation opens on their scheduled day.',exact=True)).to_be_visible()
        page.get_by_role('button',name='Handoff',exact=True).click()
        expect(page.get_by_text('Controlled meal',exact=False)).to_be_visible()
        page.get_by_label('Rider',exact=True).select_option(r)
        page.get_by_role('button',name='Save rider',exact=True).click()
        expect(page.get_by_text('Assigned. Waiting for the rider to confirm pickup.',exact=True)).to_be_visible()
        assert writes==[{'rider_id':r}]
        page.goto('http://127.0.0.1:5223/rider')
        expect(page.get_by_text('Controlled junction',exact=True)).to_be_visible()
        with page.expect_popup() as popup:
            page.get_by_role('button',name='Navigate',exact=True).click()
        destination=popup.value;destination.wait_for_load_state()
        assert parse_qs(urlparse(destination.url).query)['destination']==['6.51,3.38']
        destination.close()
        page.goto('http://127.0.0.1:5223/faq')
        page.evaluate("""async()=>{const R=await import('/node_modules/.vite/deps/react.js');const React=R.default||R;const D=await import('/node_modules/.vite/deps/react-dom_client.js');const {default:Map}=await import('/src/components/OffCampusMap.tsx');document.getElementById('root').hidden=true;const host=document.createElement('div');document.body.append(host);function Test(){const [pin,setPin]=React.useState(null);return React.createElement(Map,{center:[7.3,5.2],pin,onPinChange:p=>{window.controlledPin=p;setPin(p)}})};(D.createRoot||D.default.createRoot)(host).render(React.createElement(Test));}""")
        expect(page.get_by_role('button',name='Reload map',exact=True)).to_be_visible(timeout=16000)
        page.get_by_role('button',name='Reload map',exact=True).click()
        page.get_by_role('button',name='Use my location',exact=True).click()
        assert page.evaluate('window.controlledPin')=={'lat':7.3,'lng':5.2}
        browser.close()
    print(json.dumps({'future_schedule_preview_cannot_prepare':True,'native_kitchen_assigns_rider':True,'rider_opens_saved_pin_directions':True,'blocked_tiles_offer_retry_and_gps_still_selects_pin':True}))
finally: os.killpg(proc.pid,signal.SIGTERM)
