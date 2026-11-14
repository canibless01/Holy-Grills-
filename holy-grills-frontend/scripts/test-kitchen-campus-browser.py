"""Real kitchen components with controlled HTTP: scope, roles and outage recovery."""
import os,signal,subprocess,tempfile,time
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import sync_playwright,expect
repo=Path(__file__).resolve().parents[1];out=Path(tempfile.mkdtemp(prefix='hg-kitchen-campus-'))
a='11111111-1111-4111-8111-111111111111';b='22222222-2222-4222-8222-222222222222'
role='super_admin';reads=[];bad=[];fail=False

def fixture(route):
    req=route.request;u=urlparse(req.url);path=u.path;data={};cid=parse_qs(u.query).get('campus_id',[None])[0]
    if path.endswith('/auth/me'):data={'id':'controlled','role':role,'campus_id':a,'profile':{'id':'controlled','role':role,'campus_id':a}}
    elif path.endswith('/campuses'):data=[{'id':a,'name':'Campus A','is_active':True},{'id':b,'name':'Campus B','is_active':True}]
    elif '/kitchen/' in path:
        reads.append((path,cid))
        if role=='super_admin' and cid not in (a,b):bad.append(path);route.fulfill(status=400,json={'error':'Explicit campus required'});return
        if fail and path.endswith('/queue'):route.fulfill(status=503,json={'error':'Controlled unavailable'});return
        target=cid if role=='super_admin' else a
        if path.endswith('/queue'):data=[{'id':'44444444-4444-4444-8444-444444444444','status':'received','customer_name':'Kitchen '+('B' if target==b else 'A'),'order_items':[]}]
        elif path.endswith('/scheduled'):data={'count':0,'scheduled_orders':[]}
        elif path.endswith('/windows'):data=[]
        elif path.endswith('/settings'):data={'settings':{'daily_order_capacity':'20','is_accepting_orders':'false','auto_accept_orders':'true'}}
        elif path.endswith('/handoff'):data={'batches':[],'riders':[]}
    elif path.endswith('/kitchen-capacity'):data={'orders_today':2,'daily_order_capacity':20,'remaining':18}
    elif path.endswith('/delivery-windows/status'):data={'is_open':True,'windows':[]}
    route.fulfill(status=200,json=data)

proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5243','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api',npm_config_update_notifier='false'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
def context(browser,campus=None):
    ctx=browser.new_context(viewport={'width':1280,'height':950});ctx.route('**/api/**',fixture)
    ctx.add_init_script("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_campus_id','"+a+"');localStorage.setItem('hg_user_role','"+role+"');"+("localStorage.setItem('hg_admin_campus_id','"+campus+"');" if campus else "localStorage.setItem('hg_admin_scope_all','1');"))
    return ctx
try:
    time.sleep(2)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        ctx=context(browser);page=ctx.new_page();page.goto('http://127.0.0.1:5243/kitchen')
        expect(page.get_by_text('Select a campus to open its kitchen workspace.',exact=True)).to_be_visible()
        assert not reads,reads
        page.get_by_role('button',name='Essential only',exact=True).click()
        page.get_by_role('button',name='All Campuses',exact=True).click();page.get_by_role('button',name='Campus B',exact=True).click()
        expect(page.get_by_text('Kitchen B',exact=True)).to_be_visible()
        assert reads and not bad and all(c==b for _,c in reads),reads
        expect(page.get_by_role('switch')).to_have_count(0)
        page.get_by_role('button',name='Settings',exact=True).click()
        expect(page.get_by_text('Open',exact=True).last).to_be_visible()
        expect(page.get_by_text('Auto-Accept',exact=True)).to_have_count(0)
        expect(page.get_by_role('link',name='Manage ordering windows',exact=True).last).to_have_attribute('href','/admin?section=delivery')
        page.get_by_role('button',name='Campus B',exact=True).click();page.get_by_role('button',name='Campus A',exact=True).click()
        expect(page.get_by_text('Kitchen A',exact=True)).to_be_visible();expect(page.get_by_text('Kitchen B',exact=True)).to_have_count(0)
        page.get_by_role('button',name='Handoff',exact=True).click();expect(page.get_by_text('No ready batches awaiting handover.',exact=True)).to_be_visible()
        assert ('/api/kitchen/handoff',a) in reads
        fail=True
        expect(page.get_by_text('Kitchen updates are unavailable.',exact=False)).to_be_visible(timeout=18000)
        expect(page.get_by_role('button',name='Handoff',exact=True)).to_have_count(0)
        fail=False
        expect(page.get_by_role('button',name='Handoff',exact=True)).to_be_visible(timeout=18000)
        ctx.close()
        role='kitchen';ctx=context(browser,b);page=ctx.new_page();page.goto('http://127.0.0.1:5243/kitchen')
        expect(page.get_by_text('Kitchen A',exact=True)).to_be_visible()
        expect(page.get_by_role('switch')).to_have_count(0);expect(page.get_by_role('link',name='Manage ordering windows',exact=True)).to_have_count(0)
        page.get_by_role('button',name='Settings',exact=True).click();expect(page.get_by_text('Admin-managed · read-only',exact=True)).to_be_visible()
        ctx.close();browser.close()
    print('PASS: explicit super campus; all-campus gate; switch reset; handoff scope; actual schedule status; outage hides actions and recovers; kitchen read-only')
finally:
    os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
