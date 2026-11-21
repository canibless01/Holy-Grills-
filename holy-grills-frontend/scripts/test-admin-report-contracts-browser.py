"""Populated report contracts using actual API field names; no real data or writes."""
import json,os,signal,subprocess,tempfile,time
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1];C='11111111-1111-4111-8111-111111111111'
out=Path(tempfile.mkdtemp(prefix='hg-report-contract-'))
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5219','--strictPort'],cwd=ROOT,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
fixtures={
 'sales':{'total_revenue':1200,'order_count':4,'average_order_value':300},
 'revenue':{'total_revenue':1200,'order_count':4,'average_order_value':300,'payment_method_breakdown':{'card':2,'wallet':1,'split':1,'hp_or_free':0}},
 'payment-methods':{'total_orders':4,'counts':{'card':2,'wallet':1,'split':1,'hp_or_free':0},'percentages':{'card':50,'wallet':25,'split':25,'hp_or_free':0},'revenue_by_method':{'card':600,'wallet':300,'split':300,'hp_or_free':0}},
 'addon-acceptance':{'total_orders':4,'orders_with_addons':3,'attachment_rate':75,'top_addons':[{'name':'Controlled cheese','quantity':6,'revenue':600}]},
 'order-sources':{'total_orders':4,'order_sources':[{'order_source':'website','count':4,'revenue':1200}]},
 'orders':{'total_orders':4,'status_funnel':[]},'users':{'total_users':8},'items':[],'retention':{'retention':[]},'brand-partnerships':{'brand_partnerships':[]},
 'hp':{'hp_earned_active':100,'hp_spent':20,'hp_expired':0,'hp_pending':10,'hp_in_circulation':80,'redemption_rate':20,'tier_distribution':[{'tier':'Ember','slug':'ember','count':3},{'tier':'Blaze','slug':'blaze','count':2}]},
 'demographics':{'by_department':[{'department':'Controlled Engineering','order_count':4,'revenue':1200}],'by_faculty':[{'faculty':'Controlled Faculty','order_count':4,'revenue':1200}],'by_academic_level':[{'academic_level':'300','order_count':4,'revenue':1200}]},
 'engagement':{'total_reviews_left':7,'total_referrals_made':8,'total_event_checkins':9},
 'squad-orders':{'total_orders':4,'squad_orders_count':1,'squad_order_pct':25,'avg_items_per_squad_order':3,'avg_squad_group_size':2},
 'retention-ltv':{'total_students':8,'ordering_customers':4,'repeat_customers':2,'repeat_customer_rate':50,'total_revenue':1200,'arpu':150,'customer_ltv':300},
 'referral-network':{'total_referrals':8,'completed_referrals':3,'top_referrers':[{'referrer_id':'controlled','name':'Controlled Referrer','referral_count':4,'hp_earned':50}]},
 'delivery-locations':{'total_orders':4,'locations':[{'location':'Controlled Hostel','delivery_type':'on_campus','order_count':3,'revenue':900},{'location':'Controlled Gate','delivery_type':'off_campus','order_count':1,'revenue':300}]},
 'order-timing':{'total_orders':4,'hourly_distribution':{'9':1,'15':3},'day_of_week_distribution':{'Monday':1,'Tuesday':3}},
 'academic-calendar':{'academic_periods':[{'name':'Controlled Exam','period_type':'exam','total_orders':4,'total_revenue':1200,'avg_orders_per_day':2}],'normal_day_baseline':{'window_days':90,'normal_days':2,'avg_orders_per_day':2,'avg_revenue_per_day':600}},
}
try:
 time.sleep(2)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  for width in (393,1280):
   reads=[];exports=[];errors=[];state={'payment_fail':False}
   ctx=browser.new_context(viewport={'width':width,'height':1000},accept_downloads=True)
   ctx.add_init_script(f"sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_campus_id','{C}');localStorage.setItem('hg_user_campus_id','{C}');localStorage.setItem('hg_cookie_consent',JSON.stringify({{essential:true,analytics:false,date:new Date().toISOString()}}));")
   def api(route):
    req=route.request;url=urlparse(req.url);path=url.path;key=path.rsplit('/',1)[-1];data=[]
    if '/analytics/' in path: assert req.method=='GET',f'Unexpected reporting write: {req.method} {path}'
    if path.endswith('/auth/me'):data={'id':'controlled-admin','role':'admin','campus_id':C,'full_name':'Controlled admin'}
    elif path.endswith('/campuses'):data=[{'id':C,'name':'Controlled campus','is_active':True}]
    elif '/analytics/' in path:
     q=parse_qs(url.query);reads.append((key,q))
     if key=='export':exports.append(q);route.fulfill(status=200,content_type='text/csv',body='id,amount\ncontrolled,200\n');return
     if key=='payment-methods' and state['payment_fail']:route.fulfill(status=503,json={'error':'Controlled payment chart failure'});return
     data=fixtures.get(key,{})
    route.fulfill(status=200,json=data)
   ctx.route('**/api/**',api);ctx.route('https://*.onesignal.com/**',lambda r:r.abort())
   page=ctx.new_page();page.set_default_timeout(15000);page.on('pageerror',lambda e:errors.append(str(e)));page.goto('http://127.0.0.1:5219/admin?section=analytics')
   expect(page.get_by_text('Controlled cheese',exact=True).first).to_be_visible();expect(page.get_by_text('75%',exact=True)).to_be_visible();expect(page.get_by_text('Payment Method Split',exact=True)).to_be_visible()
   # Click chart once more after changing dates: every supported panel uses the same range.
   page.get_by_label('From date',exact=True).fill('2026-11-01');page.get_by_label('To date',exact=True).fill('2026-11-03')
   expect(page.get_by_text('Controlled cheese',exact=True).first).to_be_visible()
   for key in ('sales','revenue','payment-methods','addon-acceptance','order-sources','hp'):
    q=[q for name,q in reads if name==key][-1];assert q['from_date']==['2026-11-01'] and q['to_date']==['2026-11-03'],(key,q)
   for name in ('orders','hp transactions','wallet transactions','users'):
    with page.expect_download() as dl:page.get_by_role('button',name=name,exact=True).click()
    assert Path(dl.value.path()).read_text()=='id,amount\ncontrolled,200\n'
   assert len(exports)==4 and all(q['from_date']==['2026-11-01'] for q in exports)
   page.get_by_role('button',name='Customers & Engagement',exact=True).click()
   expect(page.get_by_text('Controlled Engineering',exact=True)).to_be_visible();expect(page.get_by_text('Controlled Faculty',exact=True)).to_be_visible();expect(page.get_by_text('Controlled Referrer',exact=True)).to_be_visible()
   expect(page.get_by_text('Current Tier Distribution',exact=True)).to_be_visible();page.get_by_text('Current Tier Distribution',exact=True).scroll_into_view_if_needed()
   expect(page.get_by_text('Blaze: 2',exact=True)).to_be_visible();expect(page.get_by_text('Ember: 3',exact=True)).to_be_visible();expect(page.get_by_text('No tier data yet',exact=True)).to_have_count(0)
   assert 'Reviews Left' in page.locator('body').inner_text() and 'Event Check-ins' in page.locator('body').inner_text()
   for key in ('demographics','squad-orders'):
    q=[q for name,q in reads if name==key][-1];assert q['from_date']==['2026-11-01'] and q['to_date']==['2026-11-03']
   page.get_by_role('button',name='Operations & Logistics',exact=True).click()
   expect(page.get_by_text('Controlled Hostel',exact=True)).to_be_visible();expect(page.get_by_text('Controlled Gate',exact=True)).to_be_visible();expect(page.get_by_text('Controlled Exam',exact=True)).to_be_visible()
   expect(page.get_by_text('Tuesday',exact=True).first).to_be_visible()
   for key in ('order-timing','delivery-locations'):
    q=[q for name,q in reads if name==key][-1];assert q['from_date']==['2026-11-01'] and q['to_date']==['2026-11-03']
   state['payment_fail']=True;page.get_by_role('button',name='Sales & Revenue',exact=True).click()
   expect(page.get_by_text("We couldn't load this page. Please try again.",exact=True)).to_be_visible();expect(page.get_by_text('Controlled cheese',exact=True).first).to_be_visible()
   state['payment_fail']=False;page.get_by_role('button',name='Retry',exact=True).click();expect(page.get_by_text('Payment Method Split',exact=True)).to_be_visible()
   assert not errors,errors
   print(json.dumps({'width':width,'actual_field_names_render':True,'nine_date_aware_panels':True,'all_four_exports':True,'isolated_chart_retry':True,'writes':0}),flush=True);ctx.close()
  browser.close()
finally:os.killpg(proc.pid,signal.SIGTERM)
