"""Native admin academic controls with controlled HTTP; no production configuration writes."""
import json,os,signal,subprocess,tempfile,time
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
repo=Path(__file__).resolve().parents[1];out=Path(tempfile.mkdtemp(prefix='hg-academic-admin-'))
c='11111111-1111-4111-8111-111111111111';role='admin';depts=[];levels=[];writes=[];fail_load=False

def fixture(route):
    global depts,levels
    req=route.request;path=urlparse(req.url).path;method=req.method;data={}
    if path.endswith('/auth/me'):data={'id':'staff','role':role,'campus_id':c,'profile':{'id':'staff','role':role,'campus_id':c}}
    elif path.endswith('/campuses'):data=[{'id':c,'name':'Controlled campus'}]
    elif '/admin/departments' in path or '/admin/academic-levels' in path:
        is_dept='/admin/departments' in path;table=depts if is_dept else levels;key='departments' if is_dept else 'levels';base='/api/admin/departments' if is_dept else '/api/admin/academic-levels'
        if method=='GET':
            if fail_load:route.fulfill(status=503,json={'error':'Controlled temporary failure'});return
            data={key:table}
        else:
            body=req.post_data_json if method in ('POST','PATCH') and req.post_data else {};writes.append((method,path,body))
            if 'bad slug'==body.get('slug'):route.fulfill(status=400,json={'error':'Invalid slug'});return
            if method=='POST' and path==base:
                row={'id':f'row-{len(writes)}','campus_id':c,'is_active':True,**body};table.append(row);data=row
            else:
                row=next(row for row in table if row['id']==path.split('/')[-2 if path.endswith('/restore') else -1])
                if method=='PATCH':row.update(body);data=row
                else:row['is_active']=path.endswith('/restore');data={'message':'Controlled visibility saved'}
    elif path.endswith('/departments'):data={'departments':[row for row in depts if row['is_active']]}
    elif path.endswith('/academic-levels'):data={'levels':[row for row in levels if row['is_active']]}
    route.fulfill(status=200,json=data)
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5239','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
def context(browser):
    ctx=browser.new_context(viewport={'width':1280,'height':900});ctx.route('**/api/**',fixture)
    ctx.add_init_script("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_campus_id','"+c+"');localStorage.setItem('hg_user_role','"+role+"');localStorage.setItem('hg_campus_id','"+c+"');")
    return ctx
try:
    time.sleep(2)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);ctx=context(browser);page=ctx.new_page();page.set_default_timeout(10000)
        page.goto('http://127.0.0.1:5239/admin?section=departments')
        expect(page.get_by_text('No entries yet. Add the first one above.',exact=True)).to_be_visible();page.get_by_role('button',name='Add',exact=True).click()
        dialog=page.get_by_role('dialog');dialog.get_by_label('Name',exact=True).fill('Controlled department');dialog.get_by_role('button',name='Save',exact=True).click()
        expect(page.get_by_text('Enter both the department name and faculty.',exact=True).first).to_be_visible();assert not writes
        dialog.get_by_label('Faculty',exact=True).fill('Controlled faculty');dialog.get_by_label('Slug (optional)',exact=True).fill('bad slug');dialog.get_by_role('button',name='Save',exact=True).click();expect(dialog).to_be_visible();expect(page.get_by_text('Invalid slug',exact=True).first).to_be_visible()
        dialog.get_by_label('Slug (optional)',exact=True).fill('controlled-department');dialog.get_by_label('Sort order',exact=True).fill('0');before=len(writes)
        dialog.get_by_role('button',name='Save',exact=True).evaluate('(button)=>{button.click();button.click()}')
        expect(page.get_by_role('button',name='Edit Controlled department',exact=True)).to_be_visible();assert len(writes)==before+1 and depts[0]['sort_order']==0
        page.get_by_role('button',name='Edit Controlled department',exact=True).click();dialog=page.get_by_role('dialog');dialog.get_by_label('Name',exact=True).fill('Renamed department');dialog.get_by_label('Faculty',exact=True).fill('Renamed faculty');dialog.get_by_role('button',name='Save',exact=True).click()
        expect(page.get_by_role('button',name='Edit Renamed department',exact=True)).to_be_visible();assert depts[0]['faculty']=='Renamed faculty'
        page.get_by_role('switch',name='Visibility Renamed department',exact=True).click();expect(page.get_by_role('switch',name='Visibility Renamed department',exact=True)).not_to_be_checked()
        assert page.evaluate("async()=> (await (await fetch('/api/departments')).json()).departments.length")==0
        page.get_by_role('switch',name='Visibility Renamed department',exact=True).click();expect(page.get_by_role('switch',name='Visibility Renamed department',exact=True)).to_be_checked()
        assert page.evaluate("async()=> (await (await fetch('/api/departments')).json()).departments[0].faculty")=='Renamed faculty'
        page.get_by_role('searchbox',name='Search academic settings',exact=True).fill('no matches');expect(page.get_by_text('No matching academic settings.',exact=True)).to_be_visible();page.get_by_role('searchbox',name='Search academic settings',exact=True).fill('')
        page.get_by_role('button',name='Academic Levels',exact=True).click();page.get_by_role('button',name='Add',exact=True).click();dialog=page.get_by_role('dialog')
        dialog.get_by_label('Name',exact=True).fill('Postgraduate');dialog.get_by_label('Stored value',exact=True).fill('PG');dialog.get_by_label('Level rank',exact=True).fill('0');dialog.get_by_label('Sort order',exact=True).fill('6');dialog.get_by_role('button',name='Save',exact=True).click()
        expect(page.get_by_role('button',name='Edit Postgraduate',exact=True)).to_be_visible();assert levels[0]['rank']==0 and levels[0]['value']=='PG'
        page.get_by_role('button',name='Edit Postgraduate',exact=True).click();dialog=page.get_by_role('dialog');dialog.get_by_label('Stored value',exact=True).fill('PG-EDIT');dialog.get_by_label('Level rank',exact=True).fill('-1');before=len(writes);dialog.get_by_role('button',name='Save',exact=True).click();assert len(writes)==before
        dialog.get_by_label('Level rank',exact=True).fill('0');dialog.get_by_role('button',name='Save',exact=True).click();expect(dialog).not_to_be_visible();assert levels[0]['value']=='PG-EDIT'
        page.get_by_role('switch',name='Visibility Postgraduate',exact=True).click();expect(page.get_by_role('switch',name='Visibility Postgraduate',exact=True)).not_to_be_checked();page.get_by_role('switch',name='Visibility Postgraduate',exact=True).click();expect(page.get_by_role('switch',name='Visibility Postgraduate',exact=True)).to_be_checked()
        depts.append({'id':'global','name':'Global department','faculty':'Global school','campus_id':None,'is_active':True})
        fail_load=True;page.reload();expect(page.get_by_role('button',name='Retry',exact=True)).to_be_visible();fail_load=False;page.get_by_role('button',name='Retry',exact=True).click()
        expect(page.get_by_text('Global department',exact=True)).to_be_visible();expect(page.get_by_role('button',name='Edit Global department',exact=True)).to_have_count(0);expect(page.get_by_role('switch',name='Visibility Global department',exact=True)).to_have_count(0)
        ctx.close();role='super_admin';ctx=context(browser);page=ctx.new_page();page.goto('http://127.0.0.1:5239/admin?section=departments');expect(page.get_by_role('button',name='Edit Global department',exact=True)).to_be_visible();ctx.close();browser.close()
    print(json.dumps({'empty_and_load_retry':True,'department_create_edit_hide_restore_public_result':True,'required_fields_and_error_preserve_modal':True,'duplicate_save_guard':True,'sort_zero_preserved':True,'level_create_edit_rank_validation_hide_restore':True,'admin_cannot_edit_global_super_can':True,'database_writes':0}))
finally:
    os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
