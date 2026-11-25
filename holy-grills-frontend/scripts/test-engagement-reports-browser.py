"""Read-only local fixture weekly sharing and HP source reconciliation."""
import os,json
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('HG_BROWSER_BASE','http://127.0.0.1:4187');C='70000001-cafe-cafe-cafe-000000000001';U='11111111-1111-4111-8111-111111111111'
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
 for width in [393,1280]:
  reads=[];errors=[];ctx=browser.new_context(viewport={'width':width,'height':950},service_workers='block');ctx.add_init_script(f"localStorage.setItem('hg_access_token','synthetic');localStorage.setItem('hg_user_role','admin');localStorage.setItem('hg_campus_id','{C}');localStorage.setItem('hg_user_campus_id','{C}');localStorage.setItem('hg_cookie_consent',JSON.stringify({{essential:true,analytics:false}}));window.copiedReport='';Object.defineProperty(navigator,'clipboard',{{value:{{writeText:async text=>{{window.copiedReport=text}}}}}});")
  def api(route):
   req=route.request;url=urlparse(req.url);path=url.path;data={}
   if path.endswith('/auth/me'):data={'id':U,'full_name':'Local admin','role':'admin','campus_id':C,'is_active':True}
   elif path.endswith('/campuses'):data={'campuses':[{'id':C,'name':'FUTA','slug':'futa','is_active':True}]}
   elif path.endswith('/ambassadors/staff/ambassadors'):data={'ambassadors':[]}
   elif path.endswith('/ambassadors/staff/weekly-report'):
    reads.append(parse_qs(url.query));data={'week_start':'2026-11-23','week_end':'2026-11-29','share_text':'Holy Grills ambassador week\nNick: 2 delivered orders and 1 signup.','ambassadors':[]}
   elif path.endswith('/analytics/hp-reconciliation'):data={'profile_active_balance':1000,'ledger_active_remaining':900,'pending_amount':20,'active_balance_difference':100,'sources':[{'source':'welcome','active_remaining':900,'pending':20,'active_awarded_in_period':1000}]}
   elif path.endswith('/analytics/items'):data=[]
   elif path.endswith('/analytics/brand-partnerships'):data={'brand_partnerships':[]}
   elif path.endswith('/notifications'):data={'notifications':[]}
   route.fulfill(status=200,json=data)
  ctx.route('**/api/**',api);ctx.route('https://*.onesignal.com/**',lambda r:r.abort());page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(BASE+'/admin?section=ambassadors',wait_until='domcontentloaded');expect(page.get_by_role('heading',name='Weekly ambassador report',exact=True)).to_be_visible();assert len(reads)==0
  page.get_by_label('Week containing',exact=True).fill('2026-11-25');page.get_by_role('button',name='Prepare report',exact=True).click();expect(page.get_by_role('textbox',name='Weekly ambassador report',exact=True)).to_have_value('Holy Grills ambassador week\nNick: 2 delivered orders and 1 signup.');assert reads[-1]['week']==['2026-11-25']
  page.get_by_role('button',name='Copy report',exact=True).click();assert 'Nick' in page.evaluate('window.copiedReport');href=page.get_by_role('link',name='Share report on WhatsApp',exact=True).get_attribute('href');assert '2 delivered orders' in parse_qs(urlparse(href).query)['text'][0]
  page.goto(BASE+'/admin?section=analytics',wait_until='domcontentloaded');page.get_by_role('button',name='Customers & Engagement',exact=True).click();expect(page.get_by_role('heading',name='HP balances by source',exact=True)).to_be_visible();expect(page.get_by_role('cell',name='welcome',exact=True)).to_be_visible();expect(page.get_by_text('Reconciliation difference',exact=True)).to_be_visible();assert not errors,errors
  print(json.dumps({'width':width,'passed':True,'external_messages_sent':0,'report_reads':len(reads)}),flush=True);ctx.close()
 browser.close()
