"""Every native calendar modal field/type, scope, retire/restore and failure; no DB writes."""
import json,os,signal,subprocess,tempfile,time
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
repo=Path(__file__).resolve().parents[1];out=Path(tempfile.mkdtemp(prefix='hg-calendar-'))
a='11111111-1111-4111-8111-111111111111';b='22222222-2222-4222-8222-222222222222';role='super_admin';periods=[];writes=[];fail_load=False;fail_save=False

def fixture(route):
    global fail_save
    req=route.request;path=urlparse(req.url).path;method=req.method;data={}
    if path.endswith('/auth/me'):data={'id':'staff','role':role,'campus_id':a,'profile':{'id':'staff','role':role,'campus_id':a}}
    elif path.endswith('/campuses'):data=[{'id':a,'name':'Campus A'},{'id':b,'name':'Campus B'}]
    elif '/admin/academic-calendar' in path:
        if method=='GET':
            if fail_load:route.fulfill(status=503,json={'error':'Controlled load failure'});return
            data={'academic_calendar':periods}
        else:
            body=req.post_data_json;writes.append((method,body))
            if fail_save:fail_save=False;route.fulfill(status=503,json={'error':'Controlled save failure'});return
            if method=='POST':row={'id':f'period-{len(writes)}','is_active':True,**body};periods.append(row)
            else:row=next(p for p in periods if p['id']==path.split('/')[-1]);row.update(body)
            data=row
    elif path.endswith('/academic-calendar'):data={'academic_calendar':[p for p in periods if p['is_active']]}
    route.fulfill(status=200,json=data)
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5240','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
def context(browser):
    ctx=browser.new_context(viewport={'width':1280,'height':950});ctx.route('**/api/**',fixture)
    ctx.add_init_script("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_campus_id','"+a+"');localStorage.setItem('hg_user_role','"+role+"');localStorage.setItem('hg_admin_campus_id','"+b+"');localStorage.removeItem('hg_admin_scope_all');")
    return ctx
try:
    time.sleep(2)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);ctx=context(browser);page=ctx.new_page();page.set_default_timeout(10000);page.goto('http://127.0.0.1:5240/admin?section=academiccalendar')
        expect(page.get_by_text('No academic calendar periods yet',exact=True)).to_be_visible()
        for kind in ('semester','exam','break','holiday','orientation','graduation'):
            page.get_by_role('button',name='Add Period',exact=True).click();dialog=page.get_by_role('dialog')
            expect(dialog.get_by_label('Campus',exact=True)).to_have_value(b)
            dialog.get_by_label('Period type',exact=True).select_option(kind);dialog.get_by_label('Name',exact=True).fill('Controlled '+kind)
            dialog.get_by_label('Start date',exact=True).fill('2026-10-26');dialog.get_by_label('End date',exact=True).fill('2026-12-31');dialog.get_by_label('Academic year',exact=True).fill('2026-2027');dialog.get_by_label('Description (optional)',exact=True).fill('Controlled description')
            if kind=='semester':
                dialog.get_by_label('End date',exact=True).fill('2026-10-25');before=len(writes);dialog.get_by_role('button',name='Create Period',exact=True).click();expect(page.get_by_text('End date must be on or after start date.',exact=True).first).to_be_visible();assert len(writes)==before
                dialog.get_by_label('End date',exact=True).fill('2026-12-31');fail_save=True;dialog.get_by_role('button',name='Create Period',exact=True).click();expect(page.get_by_text('Controlled save failure',exact=True).first).to_be_visible();expect(dialog.get_by_label('Name',exact=True)).to_have_value('Controlled semester')
            before=len(writes);dialog.get_by_role('button',name='Create Period',exact=True).evaluate('(button)=>{button.click();button.click()}')
            expect(page.get_by_role('button',name='Edit period Controlled '+kind,exact=True)).to_be_visible();assert len(writes)==before+1 and writes[-1][1]['campus_id']==b and writes[-1][1]['description']=='Controlled description'
        page.get_by_role('button',name='Edit period Controlled semester',exact=True).click();dialog=page.get_by_role('dialog');dialog.get_by_label('Campus',exact=True).select_option('');dialog.get_by_label('Name',exact=True).fill('Global semester');dialog.get_by_role('button',name='Save Changes',exact=True).click();expect(page.get_by_role('button',name='Edit period Global semester',exact=True)).to_be_visible();assert periods[0]['campus_id'] is None
        page.get_by_role('button',name='Edit period Controlled graduation',exact=True).click();dialog=page.get_by_role('dialog');dialog.get_by_role('checkbox').uncheck();dialog.get_by_role('button',name='Save Changes',exact=True).click();expect(dialog).not_to_be_visible();assert not periods[-1]['is_active']
        assert page.evaluate("async()=> (await (await fetch('/api/academic-calendar')).json()).academic_calendar.every(p=>p.period_type!=='graduation')")
        page.get_by_role('button',name='Edit period Controlled graduation',exact=True).click();dialog=page.get_by_role('dialog');dialog.get_by_role('checkbox').check();dialog.get_by_role('button',name='Save Changes',exact=True).click();expect(dialog).not_to_be_visible();assert periods[-1]['is_active']
        fail_load=True;page.reload();expect(page.get_by_role('button',name='Retry',exact=True)).to_be_visible();fail_load=False;page.get_by_role('button',name='Retry',exact=True).click();expect(page.get_by_role('button',name='Edit period Global semester',exact=True)).to_be_visible();ctx.close()
        role='admin';ctx=context(browser);page=ctx.new_page();page.goto('http://127.0.0.1:5240/admin?section=academiccalendar');expect(page.get_by_text('Global semester',exact=True)).to_be_visible();expect(page.get_by_role('button',name='Edit period Global semester',exact=True)).to_have_count(0)
        page.get_by_role('button',name='Add Period',exact=True).click();dialog=page.get_by_role('dialog');expect(dialog.get_by_label('Campus',exact=True)).to_be_disabled();expect(dialog.get_by_label('Campus',exact=True)).to_have_value(a)
        dialog.get_by_label('Name',exact=True).fill('Own campus semester');dialog.get_by_label('Start date',exact=True).fill('2026-10-26');dialog.get_by_label('End date',exact=True).fill('2026-12-31');dialog.get_by_label('Academic year',exact=True).fill('2026-2027');dialog.get_by_role('button',name='Create Period',exact=True).click();expect(page.get_by_role('button',name='Edit period Own campus semester',exact=True)).to_be_visible();assert writes[-1][1]['campus_id']==a
        ctx.close();browser.close()
    print(json.dumps({'all_six_period_types_and_fields':True,'selected_campus_and_explicit_global':True,'campus_admin_pin_and_global_controls':True,'date_validation_and_save_failure_preserve_form':True,'duplicate_click_guard':True,'retire_restore_public_list':True,'read_retry':True,'database_writes':0}))
finally:
    os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
