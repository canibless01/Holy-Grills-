"""Native area UI: independent campus scope, delayed reads, save/clear/force and retries."""
import json,os,signal,subprocess,tempfile,time
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import sync_playwright,expect
repo=Path(__file__).resolve().parents[1];out=Path(tempfile.mkdtemp(prefix='hg-area-'))
a='11111111-1111-4111-8111-111111111111';b='22222222-2222-4222-8222-222222222222';role='super_admin';writes=[];reads=[];hold_a=True;held=None;fail_read=False;fail_save=False
locations={a:{'campus_id':a,'name':'Campus A','lat':7.3,'lon':5.14},b:{'campus_id':b,'name':'Campus B','lat':7.31,'lon':5.15}};radii={a:'15',b:'10'}
def fixture(route):
    global held,fail_save
    req=route.request;url=urlparse(req.url);path=url.path;params=parse_qs(url.query);method=req.method;data={}
    if path.endswith('/auth/me'):data={'id':'staff','role':role,'campus_id':a,'profile':{'id':'staff','role':role,'campus_id':a}}
    elif path.endswith('/campuses'):data=[{'id':a,'name':'Campus A'},{'id':b,'name':'Campus B'}]
    elif path.endswith('/location'):
        cid=path.split('/')[-2];reads.append((path,cid))
        if method=='GET':
            if cid==a and hold_a:held=route;return
            data={**locations[cid],'max_delivery_radius_km':float(radii[cid])}
        else:
            body=req.post_data_json;writes.append((path,cid,body))
            if fail_save:fail_save=False;route.fulfill(status=503,json={'error':'Controlled centre failure'});return
            if body.get('coordinates'):
                lat,lon=map(float,body['coordinates'].split(','))
                if lat>14 and not body.get('force'):route.fulfill(status=400,json={'error':'Outside Nigeria','code':'CAMPUS_LOCATION_OUTSIDE_NIGERIA'});return
                locations[cid].update(lat=lat,lon=lon)
            else:locations[cid].update(lat=None,lon=None)
            data={**locations[cid],'max_delivery_radius_km':float(radii[cid])}
    elif path.endswith('/kitchen/settings'):
        cid=params.get('campus_id',[None])[0];reads.append((path,cid))
        if role=='super_admin' and cid not in (a,b):route.fulfill(status=400,json={'error':'Explicit campus required'});return
        if role!='super_admin':cid=a
        if method=='GET':
            if fail_read:route.fulfill(status=503,json={'error':'Controlled radius failure'});return
            # Missing optional key uses the successful location response's server default.
            data={'settings':{} if cid==b else {'max_delivery_radius_km':radii[cid]}}
        else:
            body=req.post_data_json;writes.append((path,cid,body));radii[cid]=body['settings']['max_delivery_radius_km'];data={'message':'Saved'}
    elif path.endswith('/storefront/config/public'):
        cid=params.get('campus_id',[a])[0];data={'campus_lat':locations[cid]['lat'],'campus_lon':locations[cid]['lon'],'max_delivery_radius_km':float(radii[cid])}
    route.fulfill(status=200,json=data)
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5242','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api',npm_config_update_notifier='false'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
def context(browser):
    ctx=browser.new_context(viewport={'width':1280,'height':950});ctx.route('**/api/**',fixture)
    ctx.add_init_script("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_campus_id','"+a+"');localStorage.setItem('hg_user_role','"+role+"');localStorage.setItem('hg_admin_campus_id','"+a+"');")
    return ctx
try:
    time.sleep(2)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);ctx=context(browser);page=ctx.new_page();page.set_default_timeout(12000);page.goto('http://127.0.0.1:5242/admin?section=delivery');page.get_by_role('button',name='Delivery area',exact=True).click()
        page.get_by_label('Campus',exact=True).select_option(b)
        radius=page.get_by_label('Delivery radius (km)',exact=True);centre=page.get_by_label('Campus centre point',exact=True)
        expect(radius).to_have_value('10');expect(centre).to_have_value('7.31, 5.15');assert held is not None
        held.fulfill(status=200,json={**locations[a],'max_delivery_radius_km':15});hold_a=False;page.wait_for_timeout(100);expect(radius).to_have_value('10')
        radius.fill('-1');before=len(writes);page.get_by_role('button',name='Save radius',exact=True).click();assert len(writes)==before
        radius.fill('2.5');page.get_by_role('button',name='Save radius',exact=True).evaluate('(button)=>{button.click();button.click()}');expect(radius).to_have_value('2.5');page.wait_for_timeout(100);assert len(writes)==before+1 and radii[a]=='15' and radii[b]=='2.5'
        public=page.evaluate("async()=> (await (await fetch('/api/storefront/config/public?campus_id="+b+"')).json())");assert public['max_delivery_radius_km']==2.5
        centre.fill('7.32, 5.16');fail_save=True;page.get_by_role('button',name='Save centre point',exact=True).click();expect(page.get_by_text('Controlled centre failure',exact=True)).to_be_visible();expect(centre).to_have_value('7.32, 5.16');expect(page.get_by_role('button',name='These coordinates are outside Nigeria — save anyway',exact=True)).to_have_count(0)
        page.get_by_role('button',name='Save centre point',exact=True).click();expect(centre).to_have_value('7.32, 5.16');page.wait_for_timeout(100);assert locations[a]['lat']==7.3 and locations[b]['lat']==7.32
        expect(page.get_by_role('link',name='Open in Maps',exact=True)).to_have_attribute('href','https://www.google.com/maps/search/?api=1&query=7.32,5.16')
        centre.fill('40, -74');page.get_by_role('button',name='Save centre point',exact=True).click();page.get_by_role('button',name='These coordinates are outside Nigeria — save anyway',exact=True).click();page.wait_for_timeout(100);assert locations[b]['lat']==40 and writes[-1][2]['force'] is True
        centre.fill('');page.get_by_role('button',name='Save centre point',exact=True).click();expect(page.get_by_text('Without a campus centre, the distance limit cannot be enforced. Set a centre before accepting off-campus orders.',exact=True)).to_be_visible();assert locations[b]['lat'] is None and locations[a]['lat']==7.3
        fail_read=True;page.reload();page.get_by_role('button',name='Delivery area',exact=True).click();expect(page.get_by_role('button',name='Retry',exact=True)).to_be_visible();expect(page.get_by_role('button',name='Save radius',exact=True)).to_have_count(0);fail_read=False;page.get_by_role('button',name='Retry',exact=True).click();expect(page.get_by_label('Delivery radius (km)',exact=True)).to_have_value('15');ctx.close()
        role='admin';ctx=context(browser);page=ctx.new_page();page.goto('http://127.0.0.1:5242/admin?section=delivery');page.get_by_role('button',name='Delivery area',exact=True).click();expect(page.get_by_label('Delivery radius (km)',exact=True)).to_have_value('15');expect(page.get_by_label('Campus',exact=True)).to_have_count(0);expect(page.get_by_label('Campus centre point',exact=True)).to_have_value('7.3, 5.14');ctx.close();browser.close()
    print(json.dumps({'super_local_selection_scopes_centre_and_radius':True,'late_old_campus_response_ignored':True,'radius_validation_and_single_save':True,'public_configuration_changes_only_target':True,'missing_setting_uses_server_metadata_not_client_default':True,'centre_save_clear_and_map_link':True,'force_only_for_explicit_outside_country_error':True,'failed_read_retry_without_fake_default_or_save':True,'campus_admin_uses_own_profile':True,'database_writes':0}))
finally:
    os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
