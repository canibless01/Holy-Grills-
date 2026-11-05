"""Actual promo editor with controlled HTTP; no remote campaign writes."""
import json, os, signal, subprocess, tempfile, time
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect

repo = Path(__file__).resolve().parents[1]
scratch = Path(tempfile.mkdtemp(prefix='hg-promo-editor-'))
campus = '11111111-1111-4111-8111-111111111111'
promo = {'id': 'promo-test', 'code': 'LAUNCH10', 'discount_type': 'percentage',
         'discount_value': 10, 'scope': 'cart', 'is_active': True, 'used_count': 0,
         'starts_at': '2026-10-27T08:15:37Z', 'ends_at': '2026-11-03T19:45:22Z'}
updates, creates = [], []

def fixture(route):
    req = route.request
    path = urlparse(req.url).path
    data = []
    if path.endswith('/auth/me'):
        data = {'id': 'controlled-admin', 'role': 'admin', 'campus_id': campus,
                'profile': {'id': 'controlled-admin', 'role': 'admin', 'campus_id': campus}}
    elif path.endswith('/campuses'):
        data = [{'id': campus, 'name': 'Controlled campus', 'is_active': True}]
    elif path.endswith('/admin/promo-codes/promo-test'):
        body = req.post_data_json
        updates.append(body)
        if 'code' in body or 'campus_id' in body:
            route.fulfill(status=400, json={'error': 'Locked field sent'})
            return
        promo.update(body)
        data = {'promo_code': promo}
    elif path.endswith('/admin/promo-codes'):
        if req.method == 'POST':
            creates.append(req.post_data_json)
            data = {**creates[-1], 'id': 'new-promo'}
        else:
            data = [promo]
    elif path.endswith('/cart'):
        data = {'items': []}
    elif any(part in path for part in ('messages', 'config', 'feature-flags', 'balance', 'streak')):
        data = {}
    route.fulfill(status=200, json=data)

proc = subprocess.Popen(['npm', 'run', 'dev', '--', '--host', '127.0.0.1', '--port', '5219', '--strictPort'],
    cwd=repo, env=dict(os.environ, VITE_API_BASE_URL='/api'), start_new_session=True,
    stdout=(scratch/'vite.log').open('w'), stderr=subprocess.STDOUT)
try:
    time.sleep(2)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox'])
        ctx = browser.new_context(viewport={'width': 1280, 'height': 1000}, timezone_id='America/New_York')
        ctx.route('**/api/**', fixture)
        ctx.add_init_script("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_campus_id','"+campus+"');localStorage.setItem('hg_user_campus_id','"+campus+"');localStorage.setItem('hg_admin_campus_id','"+campus+"')")
        page = ctx.new_page()
        page.goto('http://127.0.0.1:5219/admin?section=promos')
        page.get_by_role('button', name='Essential only', exact=True).click()
        page.get_by_role('button', name='Edit', exact=True).click()
        expect(page.get_by_label('Code', exact=True)).to_be_disabled()
        expect(page.get_by_label('Starts At', exact=True)).to_have_value('2026-10-27T09:15')
        page.get_by_label('Description (optional)', exact=True).fill('Updated campaign')
        page.get_by_role('button', name='Save Changes', exact=True).click()
        expect(page.get_by_role('dialog')).to_have_count(0)
        assert updates[-1]['starts_at'] == '2026-10-27T08:15:37Z'
        assert updates[-1]['ends_at'] == '2026-11-03T19:45:22Z'
        assert 'code' not in updates[-1] and 'campus_id' not in updates[-1]
        page.get_by_role('button', name='Create Promo Code', exact=True).click()
        page.get_by_label('Code', exact=True).fill('newlaunch')
        page.get_by_label('Starts At', exact=True).fill('2026-11-04T10:30')
        page.get_by_label('Ends At', exact=True).fill('2026-11-05T22:00')
        page.get_by_role('button', name='Create Promo', exact=True).click()
        expect(page.get_by_role('dialog')).to_have_count(0)
        assert creates[-1]['code'] == 'NEWLAUNCH'
        assert creates[-1]['starts_at'] == '2026-11-04T09:30:00.000Z'
        assert creates[-1]['ends_at'] == '2026-11-05T21:00:00.000Z'
        browser.close()
    print(json.dumps({'edit_saves_without_locked_fields': True,
        'unmodified_timestamps_preserved': True, 'new_campaign_uses_lagos_time_in_foreign_browser': True}))
finally:
    os.killpg(proc.pid, signal.SIGTERM)
