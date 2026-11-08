"""Native controls on mobile/desktop; all API/provider traffic is synthetic."""
import json
import os
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect

BASE = os.environ.get('HG_BROWSER_BASE', 'http://127.0.0.1:4186')
UID = '11111111-1111-4111-8111-111111111111'
PID = '22222222-2222-4222-8222-222222222222'
CAMPUS = '70000001-cafe-cafe-cafe-000000000001'
REF = 'HG-AUTO-' + PID.replace('-', '') + '-1'

with sync_playwright() as p:
 browser = p.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox'])
 for width in (393, 1280):
  ctx = browser.new_context(viewport={'width': width, 'height': 950}, is_mobile=width < 500)
  ctx.add_init_script(f"localStorage.setItem('hg_access_token','synthetic');localStorage.setItem('hg_user_role','student');localStorage.setItem('hg_campus_id','{CAMPUS}');localStorage.setItem('hg_user_campus_id','{CAMPUS}');")
  calls = []; errors = []; stored = []; bodies = []; paid = [False]; stops = []
  def api(route):
   path = urlparse(route.request.url).path
   calls.append(path); data = {}
   if path.endswith('/auth/me'): data = {'id': UID, 'role': 'student', 'campus_id': CAMPUS, 'full_name': 'Synthetic Student'}
   elif path.endswith('/hp/balance'): data = {'active': 0, 'pending': 0}
   elif path.endswith('/wallet'): data = {'balance': 200 if paid[0] else 0}
   elif path.endswith('/campuses'): data = {'campuses': [{'id': CAMPUS, 'name': 'FUTA', 'slug': 'futa', 'is_active': True}]}
   elif path.endswith('/auto-funding'):
    if route.request.method == 'POST':
     body = route.request.post_data_json; bodies.append(body)
     stored[:] = [{'id': PID, 'amount_kobo': 20000, 'interval_days': 2, 'stop_after': 3, 'state': 'draft', 'successful_payments': 0, 'total_credited_kobo': 0, 'setup_reference': REF, 'checkout_url': 'https://checkout.paystack.com/synthetic'}]
     data = {'plan': stored[0]}
    else: data = {'plans': stored, 'limits': {'minimum_amount': 100, 'maximum_amount': 1000000, 'maximum_interval_days': 365, 'consent_version': 'wallet-auto-funding-v1', 'fee_payer': 'holy_grills'}}
   elif '/auto-funding/' in path and path.endswith('/verify'):
    paid[0] = True; stored[0].update(state='active', successful_payments=1, total_credited_kobo=20000, checkout_url=None)
    data = {'payment_status': 'paid', 'plan': stored[0]}
   elif '/auto-funding/' in path and path.endswith('/stop'):
    stops.append(route.request.post_data_json); stored[0].update(state='stopped', in_flight=True)
    data = {'plan': stored[0]}
   elif '/notifications' in path: data = {'notifications': []}
   elif 'cart' in path: data = {'items': []}
   elif any(x in path for x in ('orders', 'tiers', 'transactions', 'saved', 'feature-flags', 'order-locks')): data = []
   route.fulfill(status=200, json=data)
  ctx.route('**/api/**', api)
  ctx.route('https://*.onesignal.com/**', lambda r: r.abort())
  ctx.route('https://checkout.paystack.com/**', lambda r: r.fulfill(status=200, content_type='text/html', body='<p>Simulated Paystack checkout</p>'))
  page = ctx.new_page(); page.on('pageerror', lambda error: errors.append(str(error)))
  page.goto(BASE + '/dashboard', wait_until='domcontentloaded')
  expect(page.get_by_role('heading', name='Welcome back', exact=False)).to_be_visible()
  if page.get_by_role('button', name='Essential only').count(): page.get_by_role('button', name='Essential only').click()
  auto_link = page.get_by_role('link', name='Automatic funding Your amount. Your schedule.')
  expect(auto_link).to_be_visible()
  grid = auto_link.locator('..')
  assert grid.locator(':scope > a').count() == 4
  assert len(grid.evaluate('(el) => getComputedStyle(el).gridTemplateColumns').split()) == 2
  assert not any(path.endswith('/auto-funding') for path in calls)
  page.goto(BASE + '/wallet', wait_until='domcontentloaded')
  expect(page.get_by_role('button', name='Set up or manage')).to_be_visible()
  assert not any(path.endswith('/auto-funding') for path in calls)
  page.get_by_role('button', name='Set up or manage').click()
  amount = page.get_by_label('Amount per contribution (₦)')
  expect(amount).to_be_visible()
  amount.fill('200.001'); page.get_by_label('Contribute every (days)').fill('2')
  page.get_by_label('Total contributions, including today').fill('3')
  consent = page.get_by_role('checkbox', name='I authorize', exact=False)
  consent.check(); page.get_by_role('button', name='Authorize and fund', exact=False).click()
  assert len(bodies) == 0  # Native precision check prevents a money intent.
  amount.fill('200'); consent.check()
  page.get_by_role('button', name='Authorize and fund', exact=False).click()
  expect(page.get_by_text('Simulated Paystack checkout')).to_be_visible()
  assert bodies[0]['amount'] == 200 and bodies[0]['interval_days'] == 2 and bodies[0]['stop_after'] == 3 and bodies[0]['consent'] is True
  page.goto(BASE + f'/wallet?auto_funding={PID}&reference={REF}', wait_until='domcontentloaded')
  expect(page.get_by_text('Payment received. Your wallet is ready to use.', exact=False)).to_be_visible()
  expect(page.get_by_text('Active', exact=True)).to_be_visible()
  assert not any(path.endswith('/wallet/fund/card/verify') for path in calls)
  page.get_by_role('button', name='Stop automatic funding', exact=True).click()
  assert len(stops) == 0
  page.get_by_role('button', name='Yes, stop funding', exact=True).click()
  expect(page.get_by_text('Stopped', exact=True)).to_be_visible()
  expect(page.get_by_text('Future payments stopped.', exact=False)).to_be_visible()
  assert len(stops) == 1 and paid[0]
  assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
  assert not errors, errors
  print(json.dumps({'width': width, 'four_equal_dashboard_cards': True, 'lazy_funding_read': True, 'native_validation': True, 'exact_200_debit_intent': True, 'auto_return_isolated': True, 'stop_confirmation': True, 'production_writes': 0}), flush=True)
  ctx.close()
 browser.close()
