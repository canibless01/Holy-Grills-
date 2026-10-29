"""Signup school/department selection using the user's full FUTA catalogue; no Auth writes."""
import csv,json,os,signal,subprocess,tempfile,time
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import sync_playwright,expect
repo=Path(__file__).resolve().parents[1]
rows=[{'id':f'department-{i}','name':name,'faculty':faculty} for i,(name,faculty) in enumerate(csv.reader((repo.parent/'docs/data/futa-departments-2026-10-29.tsv').open(),delimiter='\t'))]
rows.append({'id':'postgraduate','name':'Postgraduate','faculty':'Postgraduate'})
c='70000001-cafe-cafe-cafe-000000000001';other='22222222-2222-4222-8222-222222222222';writes=[]
def fixture(route):
    req=route.request;url=urlparse(req.url);path=url.path;query=parse_qs(url.query);data={}
    if path.endswith('/campuses'):data=[{'id':c,'name':'FUTA Main Campus'},{'id':other,'name':'Other controlled campus'}]
    elif path.endswith('/departments'):data={'departments':rows if query.get('campus_id')==[c] else [{'id':'other-department','name':'Other programme','faculty':'Other school'}]}
    elif path.endswith('/academic-levels'):data={'levels':[{'id':'level','name':'100 Level','value':'100'},{'id':'pg','name':'Postgraduate','value':'PG'}]}
    elif path.endswith('/auth/register'):writes.append(req.post_data_json);data={'status':'check_email','message':'Controlled registration accepted'}
    route.fulfill(status=200,json=data)
out=Path(tempfile.mkdtemp(prefix='hg-futa-signup-'))
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5238','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
try:
    time.sleep(2)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        for width in (390,1280):
            ctx=browser.new_context(viewport={'width':width,'height':900});ctx.route('**/api/**',fixture)
            ctx.add_init_script("localStorage.setItem('hg_campus_id','"+c+"')")
            page=ctx.new_page();page.set_default_timeout(10000);page.goto('http://127.0.0.1:5238/signup')
            page.get_by_role('button',name='Essential only',exact=True).click()
            school=page.get_by_label('School / faculty',exact=True);department=page.get_by_label('What are you studying?',exact=True)
            expect(school.locator('option')).to_have_count(12);expect(department).to_be_disabled()
            found=[]
            for name in sorted({r['faculty'] for r in rows}):
                school.select_option(name)
                visible=department.locator('option').evaluate_all('(options)=>options.filter(o=>o.value).map(o=>o.textContent)')
                assert visible==sorted((r['name'] for r in rows if r['faculty']==name),key=str.casefold)
                found.extend(visible)
            assert len(found)==52 and len(set(found))==52
            school.select_option('Postgraduate')
            school_search=page.get_by_role('searchbox',name='Search schools or faculties',exact=True)
            department_search=page.get_by_role('searchbox',name='Search departments',exact=True)
            school_search.fill('computing');school_search.press('Enter');assert not writes if width==390 else True
            expect(school.locator('option')).to_have_count(3) # match plus preserved Postgraduate choice and placeholder
            school_search.fill('no school matches');expect(page.get_by_text('No matches. Clear your search to browse all options.',exact=True)).to_be_visible();expect(school).to_have_value('Postgraduate')
            school_search.fill('');school.select_option('School of Computing (SOC)');expect(department.locator('option')).to_have_count(6)
            department_search.fill('software');expect(department.locator('option')).to_have_count(2);department_search.fill('')
            cs=next(r for r in rows if r['name']=='Computer Science');department.select_option(cs['id'])
            school.select_option('School of Agriculture and Agricultural Technology (SAAT)');expect(department).to_have_value('')
            food=next(r for r in rows if r['name']=='Food Science and Technology');department.select_option(food['id'])
            page.get_by_label('Campus',exact=True).select_option(other)
            expect(school).to_have_value('');expect(department).to_have_value('');expect(department).to_be_disabled();expect(school.locator('option')).to_have_count(2)
            page.get_by_label('Campus',exact=True).select_option(c);expect(school.locator('option')).to_have_count(12)
            page.get_by_label('Full Name',exact=True).fill('Controlled signup');page.get_by_label('Email',exact=True).fill('signup@example.invalid');page.get_by_label('Phone Number',exact=True).fill('08012345678');page.get_by_label("When's your birthday?",exact=True).fill('2000-01-01')
            page.get_by_role('button',name='Create Account',exact=True).click();expect(page.get_by_text('Please select your school or faculty.',exact=True)).to_be_visible()
            school.select_option('School of Computing (SOC)');department.select_option(cs['id']);page.get_by_label('Your level',exact=True).select_option('level')
            page.get_by_label('Password (min 8, uppercase + number + special)',exact=True).fill('ControlledOnly!123');page.get_by_label('Confirm Password',exact=True).fill('ControlledOnly!123');page.get_by_role('checkbox').nth(0).check()
            page.get_by_role('button',name='Create Account',exact=True).click();expect(page.get_by_text('Controlled registration accepted',exact=True)).to_be_visible()
            assert writes[-1]['department']=='Computer Science' and writes[-1]['campus_id']==c and 'faculty' not in writes[-1]
            school.select_option('Postgraduate');department.select_option('postgraduate');page.get_by_label('Your level',exact=True).select_option('pg')
            page.get_by_role('button',name='Create Account',exact=True).click();page.wait_for_timeout(150)
            assert writes[-1]['department']=='Postgraduate' and writes[-1]['academic_level']=='PG'
            ctx.close()
        browser.close()
    print(json.dumps({'mobile_and_desktop':True,'original_51_plus_postgraduate_in_11_schools':True,'school_and_department_search':True,'postgraduate_signup':True,'school_and_campus_change_clear_department':True,'school_required_before_department':True,'registration_sends_canonical_department_backend_derives_faculty':True,'auth_writes':0}))
finally:
    os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
