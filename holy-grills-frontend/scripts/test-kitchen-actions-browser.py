"""Native kitchen action races and stock persistence, isolated HTTP only."""
import os,signal,subprocess,tempfile,time,re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import sync_playwright,expect
repo=Path(__file__).resolve().parents[1];out=Path(tempfile.mkdtemp(prefix='hg-kitchen-actions-'));campus='11111111-1111-4111-8111-111111111111';wa='22222222-2222-4222-8222-222222222222';wb='33333333-3333-4333-8333-333333333333';item='44444444-4444-4444-8444-444444444444'
held_queue=None;held_queue_data=None;hold_queue=False;held_summary=None;held_batch=None;held_stock=None;hold_b=False;fail_summary=False;fail_stock=True;available=True;advanced=False;posts=[];stock=[]
def summary(w):return {'window_id':w,'total_orders':2,'summary':[{'item_name':('Fresh A' if advanced else 'Prep A') if w==wa else 'Prep B','total_quantity':2}]}
def fixture(route):
    global held_queue,held_queue_data,held_summary,held_batch,held_stock,available
    req=route.request;u=urlparse(req.url);path=u.path;data={}
    if path.endswith('/auth/me'):data={'id':'controlled','role':'super_admin','campus_id':campus,'profile':{'id':'controlled','role':'super_admin','campus_id':campus}}
    elif path.endswith('/campuses'):data=[{'id':campus,'name':'Campus A','is_active':True}]
    elif path.endswith('/kitchen/queue'):
        data=[{'id':str(i)*8+'-1111-4111-8111-111111111111','created_at':datetime.now(timezone.utc).isoformat(),'status':'preparing' if advanced else 'received','customer_name':'Ticket '+str(i),'order_items':[{'menu_item_id':item,'name_snapshot':'Ticket meal','quantity':1,'campus_is_available':available}]} for i in (5,6)]
        if hold_queue:held_queue=route;held_queue_data=data;return
    elif path.endswith('/kitchen/scheduled'):data={'count':0,'scheduled_orders':[]}
    elif path.endswith('/kitchen/settings'):data={'settings':{'daily_order_capacity':'20'}}
    elif path.endswith('/kitchen/windows'):data=[{'id':w,'label':label,'status':'open','order_count':2} for w,label in [(wa,'Window A'),(wb,'Window B')]]
    elif '/kitchen/batch-summary/' in path:
        w=path.split('/')[-1]
        if fail_summary:route.fulfill(status=503,json={'error':'Controlled summary failure'});return
        if w==wb and hold_b:held_summary=route;return
        data=summary(w)
    elif '/kitchen/batch/' in path:
        posts.append((path,parse_qs(u.query),req.post_data_json));held_batch=route;return
    elif path.endswith('/menu/items/'+item+'/availability'):
        stock.append(req.post_data_json)
        if fail_stock:route.fulfill(status=503,json={'error':'Controlled stock failure'});return
        held_stock=route;return
    elif '/menu/items/'+item in path:raise AssertionError('Kitchen called admin-only item editor')
    elif path.endswith('/kitchen-capacity'):data={'orders_today':2,'daily_order_capacity':20,'remaining':18}
    elif path.endswith('/delivery-windows/status'):data={'is_open':True,'windows':[]}
    route.fulfill(status=200,json=data)
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5245','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api',npm_config_update_notifier='false'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
try:
    time.sleep(2)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);ctx=browser.new_context(viewport={'width':1280,'height':1000});ctx.route('**/api/**',fixture)
        ctx.add_init_script("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_role','super_admin');localStorage.setItem('hg_user_campus_id','"+campus+"');localStorage.setItem('hg_admin_campus_id','"+campus+"');")
        page=ctx.new_page();page.goto('http://127.0.0.1:5245/kitchen');page.get_by_role('button',name='Essential only',exact=True).click()
        expect(page.get_by_title('Mark sold out (86)',exact=True)).to_have_count(2)
        page.get_by_title('Mark sold out (86)',exact=True).first.click();expect(page.get_by_text('Controlled stock failure',exact=True)).to_be_visible();expect(page.get_by_title('Restock item',exact=True)).to_have_count(0)
        hold_queue=True;page.wait_for_timeout(11000);assert held_queue is not None
        fail_stock=False;page.get_by_title('Mark sold out (86)',exact=True).first.click();expect(page.get_by_title('Mark sold out (86)',exact=True).last).to_be_disabled()
        assert stock[-1]=={'is_available':False,'campus_id':campus};available=False;held_stock.fulfill(status=200,json={'menu_item_id':item,'campus_id':campus,'is_available':False})
        expect(page.get_by_title('Restock item',exact=True)).to_have_count(2)
        hold_queue=False;held_queue.fulfill(status=200,json=held_queue_data);page.wait_for_timeout(200)
        expect(page.get_by_title('Restock item',exact=True)).to_have_count(2)
        page.reload();expect(page.get_by_title('Restock item',exact=True)).to_have_count(2)
        page.get_by_role('button',name='Prep List',exact=True).click();expect(page.get_by_text('Prep A',exact=True)).to_be_visible()
        hold_b=True;page.get_by_role('button',name=re.compile('^Window B')).click();expect(page.get_by_text('Updating preparation list…',exact=True)).to_be_visible();expect(page.get_by_role('button',name=re.compile('^Start Preparing'))).to_have_count(0)
        page.get_by_role('button',name=re.compile('^Window A')).click();expect(page.get_by_text('Prep A',exact=True)).to_be_visible();held_summary.fulfill(status=200,json=summary(wb));hold_b=False
        page.wait_for_timeout(200);expect(page.get_by_text('Prep B',exact=True)).to_have_count(0)
        fail_summary=True;page.get_by_role('button',name=re.compile('^Window B')).click();expect(page.get_by_text('Preparation list could not be loaded.',exact=False)).to_be_visible();expect(page.get_by_role('button',name=re.compile('^Start Preparing'))).to_have_count(0)
        fail_summary=False;page.get_by_role('button',name='Retry',exact=True).click();expect(page.get_by_text('Prep B',exact=True)).to_be_visible()
        page.get_by_role('button',name=re.compile('^Window A')).click();expect(page.get_by_text('Prep A',exact=True)).to_be_visible()
        start=page.get_by_role('button',name=re.compile('^Start Preparing'));start.click();expect(start).to_be_disabled();expect(page.get_by_role('button',name=re.compile('^Window B'))).to_be_disabled()
        start.evaluate('(button) => button.dispatchEvent(new MouseEvent("click", {bubbles:true}))');assert len(posts)==1,posts
        assert posts[0][0].endswith('/'+wa+'/advance') and posts[0][1]['campus_id']==[campus]
        advanced=True;held_batch.fulfill(status=200,json={'advanced_count':2,'skipped_count':0,'skipped':[]})
        expect(page.get_by_text('Fresh A',exact=True)).to_be_visible();expect(start).to_be_enabled()
        ctx.close();browser.close()
    print('PASS: stock failed-save retention, shared busy, stale-poll protection and persisted state; correct campus availability endpoint; prep stale-response rejection and failed-read retry; single scoped batch advance; summary refresh after advance')
finally:
    os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
