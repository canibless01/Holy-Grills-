"""Real form/calendar components with controlled HTTP, no auth/email writes."""
import json,os,signal,subprocess,tempfile,time
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import sync_playwright,expect
repo=Path(__file__).resolve().parents[1];out=Path(tempfile.mkdtemp(prefix='hg-signup-schedule-'))
c='11111111-1111-4111-8111-111111111111';wid='22222222-2222-4222-8222-222222222222';writes=[];refs_fail=False;milestones=[]
calendar=[{'date':'2099-01-01','reason':'full','windows':[{'id':wid,'date':'2099-01-01','is_full':True,'is_closed':False,'remaining':0}]},
 {'date':'2099-01-02','reason':'closed_today','windows':[]},
 {'date':'2099-01-03','reason':'open','windows':[{'id':wid,'date':'2099-01-03','is_full':False,'is_closed':False,'remaining':3,'opens_at':'10:00:00','closes_at':'20:00:00','delivery_starts_at':'12:00','delivery_ends_at':'14:00'}]}]
def fixture(route):
    req=route.request;path=urlparse(req.url).path;data={}
    if path.endswith('/campuses'):data=[{'id':c,'name':'Controlled campus','is_active':True}]
    elif path.endswith('/departments'):
        if refs_fail:route.fulfill(status=503,json={'error':'This list is temporarily unavailable. Please try again.'});return
        data={'departments':[{'id':'department','name':'Engineering'}]}
    elif path.endswith('/academic-levels'):data={'levels':[{'id':'level','name':'100 Level','value':'100L'}]}
    elif path.endswith('/auth/register'):
        writes.append(req.post_data_json);data={'status':'check_email','message':'Controlled registration accepted'}
    elif path.endswith('/auth/me'):data={'id':'controlled-admin','role':'admin','campus_id':c,'profile':{'id':'controlled-admin','role':'admin','campus_id':c}}
    elif path.endswith('/delivery-windows/status'):data={'is_open':False,'windows':[],'calendar':calendar,'reason':'full'}
    elif path.endswith('/ambassadors/staff/ambassadors'):data={'ambassadors':[]}
    elif path.endswith('/ambassadors/staff/milestones'):
        if req.method=='POST':milestones.append({'id':wid,'is_active':True,'campus_id':c,**req.post_data_json});data={'milestone':milestones[-1]}
        else:data={'milestones':milestones}
    elif path.endswith('/ambassadors/staff/promo-messages'):data={'messages':[]}
    elif path.endswith('/ambassadors/staff/reviews'):data={'reviews':[]}
    elif path.endswith('/cart'):data={'items':[]}
    route.fulfill(status=200,json=data)
harness=repo/'src/components/__audit_schedule_harness.tsx'
harness.write_text("""import React from 'react';import {MemoryRouter} from 'react-router-dom';import {HolyGrillProvider} from '@/lib/HolyGrillContext';import {CampusProvider} from '@/lib/campusContext';import Panel from './ScheduleOrderPanel';export default function Harness(){return <MemoryRouter initialEntries={['/checkout']}><HolyGrillProvider><CampusProvider><Panel showBack={false} onConfirm={window=>{(globalThis as any).selectedWindow=window}}/></CampusProvider></HolyGrillProvider></MemoryRouter>}""")
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5227','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
try:
    time.sleep(2)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);ctx=browser.new_context(viewport={'width':390,'height':844},timezone_id='America/New_York');ctx.route('**/api/**',fixture)
        ctx.add_init_script("localStorage.setItem('hg_campus_id','"+c+"')")
        page=ctx.new_page();page.set_default_timeout(8000);page.on('pageerror',lambda error:print(str(error)));page.goto('http://127.0.0.1:5227/signup');page.get_by_role('button',name='Essential only',exact=True).click()
        page.get_by_label('Full Name',exact=True).fill('Controlled Signup');page.get_by_label('Email',exact=True).fill('audit@example.invalid');page.get_by_label('Phone Number',exact=True).fill('08012345678')
        page.get_by_role('button',name='Create Account',exact=True).click()
        expect(page.get_by_text('Please enter your date of birth.',exact=True)).to_be_visible();assert not writes
        page.get_by_label("When's your birthday?",exact=True).fill('2000-01-01');page.get_by_label('What are you studying?',exact=True).select_option('department');page.get_by_label('Your level',exact=True).select_option('level')
        page.get_by_label('Password (min 8, uppercase + number + special)',exact=True).fill('ControlledOnly!123');page.get_by_label('Confirm Password',exact=True).fill('ControlledOnly!123')
        page.get_by_role('checkbox').nth(0).check();expect(page.get_by_role('checkbox').nth(1)).not_to_be_checked();page.get_by_role('button',name='Create Account',exact=True).click()
        expect(page.get_by_text('Controlled registration accepted',exact=True)).to_be_visible();assert writes[-1]['promotional_emails'] is False
        page.get_by_role('checkbox').nth(1).check();page.get_by_role('button',name='Create Account',exact=True).click();page.wait_for_timeout(200);assert writes[-1]['promotional_emails'] is True
        refs_fail=True;page.goto('http://127.0.0.1:5227/signup');expect(page.get_by_role('button',name='Retry',exact=True)).to_be_visible();expect(page.get_by_label('Campus',exact=True)).to_be_visible();refs_fail=False;page.get_by_role('button',name='Retry',exact=True).click();expect(page.get_by_role('button',name='Create Account',exact=True)).to_be_enabled()
        page.goto('http://127.0.0.1:5227/faq');page.evaluate("""async()=>{const R=await import('/node_modules/.vite/deps/react.js');const React=R.default||R;const D=await import('/node_modules/.vite/deps/react-dom_client.js');const {default:Harness}=await import('/src/components/__audit_schedule_harness.tsx');document.getElementById('root').hidden=true;const host=document.createElement('div');document.body.append(host);(D.createRoot||D.default.createRoot)(host).render(React.createElement(Harness));}""")
        expect(page.get_by_text('Fully booked',exact=True)).to_be_visible();expect(page.get_by_text('Unavailable',exact=True)).to_be_visible();expect(page.get_by_text('3 slots remaining',exact=True)).to_be_visible()
        page.get_by_role('button',name='Use this date',exact=True).click();selected=page.evaluate('window.selectedWindow');assert selected['date']=='2099-01-03' and selected['id']==wid and selected['campus_id']==c
        saved=json.loads(page.evaluate("sessionStorage.getItem('hg_scheduled_window')"));assert saved==selected
        page.evaluate("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_campus_id','"+c+"')")
        page.goto('http://127.0.0.1:5227/admin?section=ambassadors');expect(page.get_by_role('button',name='Add Ambassador tag',exact=True)).to_be_visible();page.get_by_role('button',name='Performance milestones',exact=True).click();expect(page.get_by_role('button',name='New milestone',exact=True)).to_be_visible();page.get_by_role('button',name='New milestone',exact=True).click();page.get_by_role('button',name='Save milestone',exact=True).click();expect(page.get_by_text('1 configured milestone',exact=True)).to_be_visible();assert milestones[0]['threshold']==3 and milestones[0]['reward_type']=='meal_discount'
        page.goto('http://127.0.0.1:5227/admin?section=ambassadorpromo');expect(page.get_by_role('heading',name='Promo Distribution',exact=True)).to_be_visible()
        page.goto('http://127.0.0.1:5227/admin?section=ambassadorreviews');expect(page.get_by_text('No active ambassadors for this campus yet.',exact=True)).to_be_visible()
        browser.close()
    print(json.dumps({'missing_birthday_blocks_network':True,'separate_optional_consent_false_and_true':True,'academic_reference_retry_keeps_campus':True,'full_closed_and_remaining_slots':True,'selected_date_and_campus_saved':True,'ambassador_admin_screens_render':True}))
finally:
    harness.unlink(missing_ok=True);os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
