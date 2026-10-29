"""Native Gates/Hostels fields and lifecycle with controlled HTTP, never production writes."""
import json,os,signal,subprocess,tempfile,time
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
repo=Path(__file__).resolve().parents[1];out=Path(tempfile.mkdtemp(prefix='hg-locations-'))
a='11111111-1111-4111-8111-111111111111';b='22222222-2222-4222-8222-222222222222';role='admin';gates=[{'id':'foreign','name':'Foreign gate','campus_id':b,'is_active':True,'base_fee':999}];hostels=[];writes=[];fail_save=False;fail_read=False

def fixture(route):
    global fail_save
    req=route.request;path=urlparse(req.url).path;method=req.method;data={}
    if path.endswith('/auth/me'):data={'id':'staff','role':role,'campus_id':a,'profile':{'id':'staff','role':role,'campus_id':a}}
    elif path.endswith('/campuses'):data=[{'id':a,'name':'Campus A'},{'id':b,'name':'Campus B'}]
    elif '/delivery/admin/gates' in path or '/delivery/admin/hostels' in path:
        gate='/gates' in path;rows=gates if gate else hostels;key='gates' if gate else 'hostels';base='/api/delivery/admin/'+key
        if method=='GET':
            if fail_read:route.fulfill(status=503,json={'error':'Controlled read failure'});return
            data={key:rows}
        else:
            body=req.post_data_json if req.post_data else {};writes.append((method,path,body))
            if fail_save:fail_save=False;route.fulfill(status=503,json={'error':'Controlled save failure'});return
            if method=='POST':
                if any(r['name'].lower()==body['name'].lower() and r['campus_id']==body.get('campus_id') for r in rows):route.fulfill(status=409,json={'error':'Edit or restore the existing location'});return
                row={'id':f'location-{len(writes)}','is_active':True,**body};rows.append(row);data=row
            else:
                row=next(r for r in rows if r['id']==path.split('/')[-1])
                if method=='DELETE':row['is_active']=False;data={'message':'Controlled hidden'}
                else:row.update(body);data=row
    elif path.endswith('/delivery/gates'):data={'gates':[r for r in gates if r['is_active'] and r['campus_id']==a]}
    elif path.endswith('/delivery/hostels'):data={'hostels':[r for r in hostels if r['is_active'] and r['campus_id']==a]}
    route.fulfill(status=200,json=data)
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5241','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
def context(browser):
    ctx=browser.new_context(viewport={'width':1280,'height':950});ctx.route('**/api/**',fixture)
    ctx.add_init_script("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_campus_id','"+a+"');localStorage.setItem('hg_user_role','"+role+"');localStorage.setItem('hg_admin_campus_id','"+a+"');")
    return ctx
try:
    time.sleep(2)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);ctx=context(browser);page=ctx.new_page();page.set_default_timeout(10000);page.goto('http://127.0.0.1:5241/admin?section=delivery');page.get_by_role('button',name='Zones & Fees',exact=True).click()
        expect(page.get_by_role('button',name='Edit gate Foreign gate',exact=True)).to_have_count(0)
        page.get_by_role('button',name='Add gate',exact=True).click();dialog=page.get_by_role('dialog');expect(dialog.get_by_label('Latitude',exact=True)).to_have_value('');expect(dialog.get_by_label('Longitude',exact=True)).to_have_value('');expect(dialog.get_by_label('Campus',exact=True)).to_be_disabled()
        dialog.get_by_label('Name',exact=True).fill('Controlled gate');dialog.get_by_label('Base fee (₦)',exact=True).fill('500');dialog.get_by_label('Rate per km (₦)',exact=True).fill('100');dialog.get_by_label('Minimum fee (₦)',exact=True).fill('200');dialog.get_by_label('Latitude',exact=True).fill('7.3');before=len(writes);dialog.get_by_role('button',name='Save',exact=True).click();expect(page.get_by_text('Enter both latitude and longitude within Nigeria, or leave both blank.',exact=True).first).to_be_visible();assert len(writes)==before
        dialog.get_by_label('Longitude',exact=True).fill('5.14');fail_save=True;dialog.get_by_role('button',name='Save',exact=True).click();expect(page.get_by_text('Controlled save failure',exact=True).first).to_be_visible();expect(dialog.get_by_label('Name',exact=True)).to_have_value('Controlled gate')
        before=len(writes);dialog.get_by_role('button',name='Save',exact=True).evaluate('(button)=>{button.click();button.click()}');expect(page.get_by_role('button',name='Edit gate Controlled gate',exact=True)).to_be_visible();assert len(writes)==before+1;gate=gates[-1];assert gate['lat']==7.3 and gate['lon']==5.14 and gate['rate_per_km']==100 and gate['min_fee']==200
        page.get_by_role('button',name='Edit gate Controlled gate',exact=True).click();dialog=page.get_by_role('dialog');dialog.get_by_label('Latitude',exact=True).fill('');dialog.get_by_label('Longitude',exact=True).fill('');dialog.get_by_label('Minimum fee (₦)',exact=True).fill('600');dialog.get_by_role('button',name='Save',exact=True).click();expect(dialog).not_to_be_visible();assert gate['lat'] is None and gate['lon'] is None and gate['min_fee']==600
        page.get_by_role('button',name='Add hostel',exact=True).click();dialog=page.get_by_role('dialog');expect(dialog.get_by_label('Nearest gate (optional)',exact=True).locator('option')).to_have_count(2)
        dialog.get_by_label('Name',exact=True).fill('Controlled hostel');dialog.get_by_label('Delivery fee (₦)',exact=True).fill('350');dialog.get_by_label('Nearest gate (optional)',exact=True).select_option(gate['id']);dialog.get_by_role('button',name='Save',exact=True).click();expect(page.get_by_role('button',name='Edit hostel Controlled hostel',exact=True)).to_be_visible();assert hostels[-1]['gate_id']==gate['id']
        page.get_by_role('button',name='Edit hostel Controlled hostel',exact=True).click();dialog=page.get_by_role('dialog');dialog.get_by_label('Delivery fee (₦)',exact=True).fill('375');dialog.get_by_role('button',name='Save',exact=True).click();expect(dialog).not_to_be_visible();assert hostels[-1]['delivery_fee']==375
        page.get_by_role('button',name='Edit hostel Controlled hostel',exact=True).click();page.get_by_role('dialog').get_by_role('button',name='Hide',exact=True).click();expect(page.get_by_role('button',name='Restore',exact=True)).to_be_visible();assert page.evaluate("async()=> (await (await fetch('/api/delivery/hostels')).json()).hostels.length")==0
        page.get_by_role('button',name='Restore',exact=True).click();expect(page.get_by_role('button',name='Restore',exact=True)).to_have_count(0);assert hostels[-1]['is_active']
        page.get_by_role('button',name='Edit gate Controlled gate',exact=True).click();page.get_by_role('dialog').get_by_role('button',name='Hide',exact=True).click();expect(page.get_by_role('button',name='Restore gate',exact=True)).to_be_visible();assert page.evaluate("async()=> (await (await fetch('/api/delivery/gates')).json()).gates.length")==0
        page.get_by_role('button',name='Restore gate',exact=True).click();expect(page.get_by_role('button',name='Restore gate',exact=True)).to_have_count(0);assert gate['is_active']
        fail_read=True;page.reload();expect(page.get_by_role('alert')).to_contain_text('Some delivery data could not be loaded. Retry to refresh it.');fail_read=False;page.get_by_role('button',name='Retry',exact=True).click();page.get_by_role('button',name='Zones & Fees',exact=True).click();expect(page.get_by_role('button',name='Edit gate Controlled gate',exact=True)).to_be_visible();ctx.close()
        role='super_admin';ctx=context(browser);page=ctx.new_page();page.goto('http://127.0.0.1:5241/admin?section=delivery');page.get_by_role('button',name='Zones & Fees',exact=True).click();expect(page.get_by_role('button',name='Edit gate Foreign gate',exact=True)).to_be_visible();page.get_by_role('button',name='Add gate',exact=True).click();dialog=page.get_by_role('dialog');expect(dialog.get_by_label('Campus',exact=True)).to_be_enabled();dialog.get_by_label('Campus',exact=True).select_option(b);dialog.get_by_label('Name',exact=True).fill('Super gate');dialog.get_by_label('Base fee (₦)',exact=True).fill('0');dialog.get_by_label('Minimum fee (₦)',exact=True).fill('0');dialog.get_by_role('button',name='Save',exact=True).click();expect(dialog).not_to_be_visible();assert gates[-1]['campus_id']==b
        ctx.close();browser.close()
    print(json.dumps({'all_gate_and_hostel_fields':True,'no_example_pin':True,'coordinate_pair_validation':True,'failed_save_preserves_fields':True,'duplicate_click_guard':True,'explicit_clear_pin':True,'same_campus_gate_selector':True,'hostel_gate_edit_hide_restore_public_result':True,'load_retry':True,'super_selects_target_campus':True,'database_writes':0}))
finally:
    os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
