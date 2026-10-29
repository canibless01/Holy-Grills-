"""Actual Menu/Home components; controlled transport only, no provider writes.
Covers automatic recovery, campus-safe retained content, empty vs failure,
request sharing, reconnect and the real 20-second public-read deadline.
"""
import json, os, signal, subprocess, tempfile, time
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright, expect

repo = Path(__file__).resolve().parents[1]
out = Path(tempfile.mkdtemp(prefix='hg-storefront-return-'))
a, b = '11111111-1111-4111-8111-111111111111', '22222222-2222-4222-8222-222222222222'
state = {'phase': 'transient', 'failures': {}, 'reads': [], 'auth': True}

def api(route):
    req = route.request; url = urlparse(req.url); path = url.path
    scope = req.headers.get('x-campus-id') or 'global'; params = parse_qs(url.query)
    data = {}; resource = path.rsplit('/', 1)[-1]
    if path.endswith('/campuses'): data = {'campuses': [{'id': a, 'name': 'Campus A'}, {'id': b, 'name': 'Campus B'}]}
    elif path.endswith('/auth/me'):
        data = {'id': 'controlled-student', 'role': 'student', 'campus_id': a, 'profile': {'id': 'controlled-student', 'full_name': 'Controlled Student', 'role': 'student', 'campus_id': a}}
    elif '/storefront/' in path and resource in ('banners', 'sections', 'early-supporters'):
        state['reads'].append({'resource': resource, 'scope': scope, 'params': params, 'phase': state['phase']})
        # Existing popup/tier-icon helpers are separate from the shared homepage reads.
        if params: route.fulfill(json=[]); return
        assert 'authorization' not in req.headers, 'Published content must not wait for authenticated reads'
        key = (resource, scope)
        failed = state['failures'].get(key, 0)
        if state['phase'] == 'outage' or (state['phase'] == 'transient' and failed == 0):
            state['failures'][key] = failed + 1
            route.fulfill(status=503, json={'error': 'Controlled transient outage'}); return
        if state['phase'] == 'slow' and resource == 'banners': time.sleep(13)
        if state['phase'] == 'unauthorized': route.fulfill(status=401, json={'error': 'Controlled refusal'}); return
        if state['phase'] == 'empty': route.fulfill(json=[]); return
        campus = 'B' if scope == b else 'A'; suffix = ' updated' if state['phase'] == 'updated' else ' edited' if state['phase'] == 'edited' else ''
        if resource == 'banners':
            data = [{'id': 'hero-' + campus, 'placement': 'hero', 'is_active': True, 'title': 'Hero ' + campus + suffix,
                     'image_url': '/icons/icon-192.png', 'action_label': 'Browse menu', 'action_url': '/menu'}]
        elif resource == 'sections':
            data = [{'id': kind + campus, 'section_type': kind, 'title': title + ' ' + campus + suffix, 'is_active': True,
                     'content': {'image_url': '/icons/icon-192.png', 'name': 'Review ' + campus, 'review': 'Real feedback fixture', 'rating': 5}}
                    for kind, title in [('how_its_made', 'Craft'), ('whats_inside', 'Inside'), ('catering', 'Catering'), ('testimonial', 'Review')]]
        else: data = [{'id': 'supporter', 'name': 'Supporter ' + campus, 'photo_url': '/icons/icon-192.png'}]
    elif path.endswith('/storefront/feature-flags'): data = []
    elif path.endswith('/hp/tiers'): data = []
    elif path.endswith('/menu/categories'): data = []
    elif path.endswith('/menu/items'): data = {'items': []}
    elif path.endswith('/cart'): data = {'items': []}
    elif path.endswith('/orders'): data = []
    elif path.endswith('/hp/balance'): data = {'active': 0, 'pending': 0, 'hp_earned_120day': 0}
    elif path.endswith('/leaderboard/my-rank'): data = {'rank': None, 'rank_entry': None}
    route.fulfill(status=200, json=data)

harness = repo / 'src/components/__audit_storefront_return.tsx'
html = repo / '__audit_storefront_return.html'
harness.write_text("""import React from 'react';import {BrowserRouter,Routes,Route,Link} from 'react-router-dom';
import {AppProviders} from '@/App';import {HolyGrillProvider} from '@/lib/HolyGrillContext';import {CampusProvider,useCampus} from '@/lib/campusContext';
import Home from '@/pages/Home';import Menu from '@/pages/Menu';import {SoundProvider} from '@/lib/SoundProvider';import '@/index.css';
function Scope(){const c=useCampus();return <button onClick={()=>c.selectCampus('22222222-2222-4222-8222-222222222222')}>Select campus B</button>}
export default function Harness(){return <AppProviders><BrowserRouter><SoundProvider><HolyGrillProvider><CampusProvider><header style={{position:'relative',zIndex:100}}><nav><Link to='/'>Test Home</Link><Link to='/menu'>Test Menu</Link></nav><Scope/><input aria-label='Preserved draft'/></header><Routes><Route path='/' element={<Home/>}/><Route path='/menu' element={<Menu/>}/></Routes></CampusProvider></HolyGrillProvider></SoundProvider></BrowserRouter></AppProviders>}
""")
html.write_text("""<html><head><meta name='viewport' content='width=device-width,initial-scale=1'></head><body><div id='test-root'></div><script type='module'>import React from '/node_modules/.vite/deps/react.js';import DOM from '/node_modules/.vite/deps/react-dom_client.js';import Harness from '/src/components/__audit_storefront_return.tsx';history.replaceState(null,'','/menu');window.documentMarker='preserved';DOM.createRoot(document.getElementById('test-root')).render(React.createElement(Harness));</script></body></html>""")
proc = subprocess.Popen(['npm', 'run', 'dev', '--', '--host', '127.0.0.1', '--port', '5236', '--strictPort'], cwd=repo,
                        env=dict(os.environ, VITE_API_BASE_URL='/api'), start_new_session=True,
                        stdout=(out / 'vite.log').open('w'), stderr=subprocess.STDOUT)

def new_page(browser, phase='transient', auth=True):
    state.update(phase=phase, failures={}, reads=[], auth=auth)
    ctx = browser.new_context(viewport={'width': 393, 'height': 852})
    ctx.route('**/api/**', api)
    seed = {'hg_campus_id': a, 'hg_cookie_consent': json.dumps({'essential': True, 'analytics': False, 'date': '2026-10-29'})}
    if auth: seed.update(hg_access_token='controlled', hg_user_campus_id=a, hg_user_role='student')
    ctx.add_init_script('for(const[k,v]of Object.entries(' + json.dumps(seed) + '))localStorage.setItem(k,v)')
    page = ctx.new_page(); page.on('pageerror', lambda e: print('Browser error: ' + str(e), flush=True)); page.on('console', lambda m: print('Console error: '+m.text[:400], flush=True) if m.type=='error' else None); page.set_default_timeout(12000)
    page.goto('http://127.0.0.1:5236/__audit_storefront_return.html'); page.get_by_label('Preserved draft').fill('keep my draft')
    page.get_by_role('link', name='Test Home', exact=True).click()
    return ctx, page

def resume(page):
    page.evaluate("window.__clockOffset=(window.__clockOffset||0)+60000;if(!window.__realNow){window.__realNow=Date.now.bind(Date);Date.now=()=>window.__realNow()+window.__clockOffset}window.dispatchEvent(new Event('online'))")

try:
    time.sleep(2)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox'])
        ctx, page = new_page(browser)
        expect(page.get_by_role('heading', name='Hero A', exact=True)).to_be_visible()
        expect(page.get_by_text('Craft A', exact=True)).to_be_visible()
        expect(page.get_by_text('Catering A', exact=True)).to_be_visible()
        expect(page.get_by_text('Supporter A', exact=True)).to_be_visible()
        counts = {kind: len([r for r in state['reads'] if r['resource'] == kind and not r['params']]) for kind in ['sections', 'banners', 'early-supporters']}
        assert counts == {'sections': 2, 'banners': 2, 'early-supporters': 2}, counts
        state['phase'] = 'edited'
        page.evaluate("async()=>{const {apiClient}=await import('/src/lib/apiClient.ts');await apiClient.patch('/storefront/sections/controlled',{title:'Controlled edit'})}")
        expect(page.get_by_text('Craft A edited', exact=True)).to_be_visible()
        expect(page.get_by_role('heading', name='Hero A', exact=True)).to_be_visible()

        page.get_by_role('link', name='Test Menu', exact=True).click(); state['phase'] = 'outage'
        # Expire freshness, retaining the successful campus snapshot.
        page.evaluate("window.__clockOffset=60000;window.__realNow=Date.now.bind(Date);Date.now=()=>window.__realNow()+window.__clockOffset")
        page.get_by_role('link', name='Test Home', exact=True).click()
        expect(page.get_by_role('heading', name='Hero A', exact=True)).to_be_visible(timeout=1000)
        page.wait_for_timeout(3500)
        expect(page.get_by_role('heading', name='Hero A', exact=True)).to_be_visible()
        state['phase'] = 'updated'; resume(page)
        expect(page.get_by_role('heading', name='Hero A updated', exact=True)).to_be_visible()
        expect(page.get_by_text('Craft A updated', exact=True)).to_be_visible()
        expect(page.get_by_label('Preserved draft')).to_have_value('keep my draft')
        assert page.evaluate('window.documentMarker') == 'preserved'
        state['phase'] = 'empty'; resume(page)
        expect(page.get_by_role('heading', name='Hero A updated', exact=True)).to_have_count(0)
        expect(page.get_by_text('Craft A updated', exact=True)).to_have_count(0)
        expect(page.get_by_role('button', name='Retry', exact=True)).to_have_count(0)
        ctx.close()
        ctx, page = new_page(browser, 'outage')
        retry = page.get_by_role('status', name='Home highlights', exact=True).get_by_role('button', name='Retry', exact=True)
        expect(retry).to_be_visible(); state['phase'] = 'ready'; retry.click()
        expect(page.get_by_role('heading', name='Hero A', exact=True)).to_be_visible()
        assert page.evaluate('window.documentMarker') == 'preserved'; ctx.close()
        ctx, page = new_page(browser, 'slow')
        expect(page.get_by_role('heading', name='Hero A', exact=True)).to_be_visible(timeout=20000)
        assert len([r for r in state['reads'] if r['resource'] == 'banners' and not r['params']]) == 1
        ctx.close()
        ctx, page = new_page(browser, 'unauthorized')
        expect(page.get_by_role('status', name='Home highlights', exact=True).get_by_role('button', name='Retry', exact=True)).to_be_visible()
        refused = len([r for r in state['reads'] if r['resource'] == 'banners' and not r['params']])
        page.wait_for_timeout(2000)
        assert len([r for r in state['reads'] if r['resource'] == 'banners' and not r['params']]) == refused
        ctx.close()
        ctx, page = new_page(browser, 'ready', auth=False)
        expect(page.get_by_role('heading', name='Hero A', exact=True)).to_be_visible()
        page.evaluate("""()=>{const original=window.fetch;window.fetch=async(...args)=>{const response=await original(...args);if(String(args[0]).split('?')[0].endsWith('/banners')&&args[1]?.headers?.['X-Campus-ID']==='11111111-1111-4111-8111-111111111111'){return await new Promise(resolve=>{window.releaseOldCampus=()=>resolve(response)})}return response}}""")
        resume(page)
        page.wait_for_function('typeof window.releaseOldCampus === "function"')
        page.get_by_role('button', name='Select campus B', exact=True).click()
        expect(page.get_by_role('heading', name='Hero B', exact=True)).to_be_visible()
        expect(page.get_by_role('heading', name='Hero A', exact=True)).to_have_count(0)
        expect(page.get_by_text('Inside B', exact=True)).to_be_visible()
        page.evaluate('window.releaseOldCampus()'); page.wait_for_timeout(300)
        expect(page.get_by_role('heading', name='Hero B', exact=True)).to_be_visible()
        expect(page.get_by_role('heading', name='Hero A', exact=True)).to_have_count(0)
        ctx.close(); browser.close()
    result = {'mode': 'actual React Menu/Home components; controlled transport only', 'first_transient_failure_recovers_without_refresh': True,
              'one_shared_resource_request_per_attempt': counts, 'return_to_home_keeps_last_good_content_during_outage': True,
              'reconnect_updates_all_sections': True, 'draft_and_document_preserved': True, 'successful_cms_edit_invalidates_fresh_content_immediately': True,
              'genuine_empty_response_removes_old_content': True, 'cold_failure_has_working_retry': True,
              'thirteen_second_read_survives_twenty_second_public_deadline_without_retry': True, 'unauthorized_not_automatically_retried': True, 'campus_caches_and_late_responses_isolated': True}
    (out / 'results.json').write_text(json.dumps(result, indent=2)); print(json.dumps(result, indent=2)); print('Evidence: ' + str(out / 'results.json'))
finally:
    harness.unlink(missing_ok=True); html.unlink(missing_ok=True)
    os.killpg(proc.pid, signal.SIGTERM); proc.wait(timeout=10)
