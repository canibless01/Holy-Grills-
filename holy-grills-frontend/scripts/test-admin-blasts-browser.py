"""Native campaign composer/history/analytics. Controlled API, no real send."""
import os,re,signal,subprocess,tempfile,time,uuid
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import sync_playwright,expect
repo=Path(__file__).resolve().parents[1];out=Path(tempfile.mkdtemp(prefix='hg-blasts-'));C='11111111-1111-4111-8111-111111111111';U='22222222-2222-4222-8222-222222222222';P='33333333-3333-4333-8333-333333333333';IMAGE='https://res.cloudinary.com/test-cloud/image/upload/menu.png'
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5286','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
expect.set_options(timeout=15000)
try:
 time.sleep(2)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  for width in (393,1280):
   state={'read_fail':True,'create_loss':True,'test_loss':True,'preview_hold':None,'hold_next':True,'analytics_fail':True,'analytics_hold':None,'hold_analytics':False,'blasts':[{'id':str(uuid.uuid4()),'title':'History '+str(i),'body':'Saved body','channels':['email'],'tracking_enabled':True,'status':'sent','metadata':{},'created_at':'2026-11-13T10:00:00Z'} for i in range(26)]};creates=[];tests=[];errors=[];reads=[]
   def api(route):
    request=route.request;url=urlparse(request.url);path=url.path;query=parse_qs(url.query);data={}
    if path.endswith('/auth/me'):data={'id':U,'email':'admin@example.invalid','role':'super_admin','campus_id':C,'is_active':True,'profile':{'id':U,'email':'admin@example.invalid','role':'super_admin','campus_id':C}}
    elif path.endswith('/campuses'):data=[{'id':C,'name':'FUTA','is_active':True}]
    elif path.endswith('/upload/status'):data={'configured':False,'cloud_name':'test-cloud','missing':[]}
    elif path.endswith('/admin/users'):data=[{'id':P,'full_name':'Audit recipient','email':'recipient@example.invalid','is_active':True}]
    elif path.endswith('/email-health'):data={}
    elif path.endswith('/email-subscriptions/backfill'):state['syncs']=state.get('syncs',0)+1;data={'started':True,'limit':500}
    elif path.endswith('/blasts/preview'):
     if state['hold_next']:state['hold_next']=False;state['preview_hold']=route;return
     data={'recipient_count':1}
    elif path.endswith('/blasts/test'):
     body=request.post_data_json;tests.append(body);assert body['test_email']=='admin@example.invalid'
     if state['test_loss']:state['test_loss']=False;route.fulfill(status=503,json={'error':'Controlled test response loss'});return
     assert tests[0]['request_id']==body['request_id'];data={'blast_id':body['request_id'],'email':{'status':'queued','error':'Controlled email awaiting provider'}}
    elif path.endswith('/blasts'):
     if request.method=='POST':
      body=request.post_data_json;creates.append(body)
      row=next((r for r in state['blasts'] if r['id']==body['request_id']),None)
      if row is None:row={**body,'id':body['request_id'],'status':'scheduled' if body.get('send_at') else 'sent'};state['blasts'].insert(0,row)
      if state['create_loss']:state['create_loss']=False;route.fulfill(status=503,json={'error':'Controlled campaign response loss'});return
      data={'blast':row,'already_created':len(creates)>1,'sent_to':1}
     else:
      if state['read_fail']:state['read_fail']=False;route.fulfill(status=503,json={'error':'Controlled history failure'});return
      offset=int(query.get('offset',['0'])[0]);limit=int(query.get('limit',['0'])[0]);assert limit==25;reads.append((offset,query.get('status',[''])[0]));rows=[r for r in state['blasts'] if not query.get('status') or r['status']==query['status'][0]];data={'blasts':rows[offset:offset+limit]}
    elif path.endswith('/analytics'):
     if state['analytics_fail']:state['analytics_fail']=False;route.fulfill(status=503,json={'error':'Controlled analytics failure'});return
     if state['hold_analytics']:state['hold_analytics']=False;state['analytics_hold']=route;return
     data={'blast_id':path.split('/')[-2],'recipient_count':10,'open_count':2,'click_count':1,'open_rate':20,'click_rate':10,'click_to_open_rate':50,'link_clicks':{},'recent_opens':[{'timestamp':'2026-11-13T10:00:00Z','user_agent':None}],'recent_clicks':[]}
    elif path.endswith('/cancel'):
     row=next(r for r in state['blasts'] if r['id']==path.split('/')[-2]);row['status']='cancelled';data=row
    elif path.endswith('/retry'):
     row=next(r for r in state['blasts'] if r['id']==path.split('/')[-2]);row['status']='sent';data={'sent_to':1}
    elif path.endswith('/dispatch/recovery'):data={'deliveries':[]}
    route.fulfill(json=data)
   context=browser.new_context(viewport={'width':width,'height':1000},timezone_id='UTC');context.route('**/api/**',api);context.route('https://res.cloudinary.com/**',lambda r:r.fulfill(path=str(repo/'scripts/fixtures/event-ticket-qr.png'),content_type='image/png'));context.add_init_script("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_role','super_admin');localStorage.setItem('hg_admin_campus_id','"+C+"');localStorage.setItem('hg_user_campus_id','"+C+"');localStorage.setItem('hg_cookie_consent',JSON.stringify({essential:true,analytics:false,date:new Date().toISOString()}));")
   page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto('http://127.0.0.1:5286/admin?section=notifications');page.get_by_role('button',name='Retry',exact=True).click();expect(page.get_by_text('History 0',exact=True)).to_be_visible();page.get_by_role('button',name='Next campaigns',exact=True).click();expect(page.get_by_text('History 25',exact=True)).to_be_visible();page.get_by_role('button',name='Previous campaigns',exact=True).click();expect(page.get_by_text('History 0',exact=True)).to_be_visible()
   page.get_by_role('button',name='Analytics',exact=True).first.click();dialog=page.get_by_role('dialog',name='Email Analytics',exact=True);expect(dialog.get_by_text('Controlled analytics failure',exact=True)).to_be_visible();dialog.get_by_role('button',name='Retry',exact=True).click();expect(dialog.get_by_text('Audience',exact=True)).to_be_visible();dialog.get_by_role('button',name='Close campaign analytics',exact=True).click()
   page.get_by_role('button',name='Sync existing email subscribers',exact=True).evaluate('(b)=>{b.click();b.click()}');expect(page.get_by_text('Email subscriber sync started',exact=True)).to_be_visible();assert state.get('syncs')==1
   page.get_by_label('Title (required)',exact=True).fill('Launch campaign');page.get_by_role('textbox',name='Write your notification message with rich formatting...',exact=True).fill('Fresh menu\nSecond paragraph');page.get_by_placeholder('Plain text fallback (auto-generated from rich text if empty)').fill('Fresh menu\n\nSecond paragraph');page.get_by_label('Email',exact=True).check();page.get_by_label(re.compile('Enable open & click tracking')).check();page.get_by_label('Destination path (optional)',exact=True).fill('/menu');page.get_by_role('button',name='Preview recipients',exact=True).click()
   page.locator('select').filter(has=page.locator('option[value="student"]')).select_option('student');assert state['preview_hold'];state['preview_hold'].fulfill(json={'recipient_count':999});page.wait_for_timeout(100);expect(page.get_by_text('999 recipients in this audience.',exact=True)).to_have_count(0);page.get_by_role('button',name='Preview recipients',exact=True).click();expect(page.get_by_text('1 recipients in this audience.',exact=True)).to_be_visible()
   safe=page.evaluate("""async()=>{const m=await import('/src/lib/blastPreview.ts');return m.safeBlastHtml('<p onclick=\"alert(1)\">Safe <strong>text</strong><img src=x onerror=\"alert(1)\"><script>alert(1)</script><a href=\"javascript:alert(1)\">link</a></p>');}""");assert '<strong>text</strong>' in safe and not any(part in safe for part in ('onclick','onerror','<img','<script','javascript:'))
   page.get_by_placeholder('https://…/image.jpg').fill(IMAGE);page.get_by_role('button',name='Use',exact=True).click();page.get_by_role('button',name='Add Image',exact=True).click();page.get_by_placeholder('https://…/image.jpg').first.fill(IMAGE);page.get_by_role('button',name='Use',exact=True).first.click();page.get_by_placeholder('Alt text (visible when images are blocked)').fill('Fresh meal');page.get_by_placeholder('Optional: Click link (e.g., https://holygrills.online/menu)').fill('/menu');page.get_by_role('button',name='Add CTA',exact=True).click();page.get_by_placeholder('Button label (e.g., Order Now)').fill('Browse menu');page.get_by_placeholder('https://holygrills.online/menu',exact=True).fill('/menu');page.locator('select').filter(has=page.locator('option[value="secondary"]')).select_option('secondary')
   page.get_by_placeholder('Search name, nickname or email').fill('Audit');page.get_by_role('button',name='Audit recipient · recipient@example.invalid',exact=True).click();page.get_by_role('button',name='Preview',exact=True).click();preview=page.get_by_role('dialog',name='Email Preview',exact=True);expect(preview.get_by_text('Launch campaign',exact=True)).to_be_visible();preview.get_by_role('button',name='Close email preview',exact=True).click()
   page.get_by_role('button',name='Test to Me',exact=True).click();expect(page.get_by_text('Controlled test response loss',exact=True)).to_be_visible();page.get_by_role('button',name='Test Deliverability',exact=True).click();expect(page.get_by_text('Controlled email awaiting provider',exact=True)).to_be_visible();assert len(tests)==2
   page.get_by_role('button',name='Send Blast Now',exact=True).click();confirm=page.get_by_role('dialog',name='Send to everyone now?',exact=True);expect(confirm).to_contain_text('1 selected accounts');confirm.get_by_role('button',name='Confirm & Send',exact=True).evaluate('(b)=>{b.click();b.click()}');expect(page.get_by_text('Controlled campaign response loss',exact=True)).to_be_visible();assert len(creates)==1 and creates[0]['request_id']!=tests[0]['request_id'];page.get_by_role('button',name='Send Blast Now',exact=True).click();page.get_by_role('button',name='Confirm & Send',exact=True).click();expect(page.get_by_label('Title (required)',exact=True)).to_have_value('');assert creates[0]==creates[1];assert creates[0]['target_segment']['user_ids']==[P] and creates[0]['action_url']=='/menu';assert creates[0]['tracking_enabled'] is True;assert creates[0]['push_image']==IMAGE and creates[0]['images'][0]['alt']=='Fresh meal' and creates[0]['cta_blocks'][0]['style']=='secondary'
   page.get_by_label('Title (required)',exact=True).fill('Scheduled campaign');page.get_by_placeholder('Plain text fallback (auto-generated from rich text if empty)').fill('Later');page.get_by_label('Schedule (WAT, optional)',exact=True).fill('2027-12-01T12:00');page.get_by_role('button',name='Schedule Campaign',exact=True).click();expect(page.get_by_label('Title (required)',exact=True)).to_have_value('');assert creates[-1]['send_at']=='2027-12-01T11:00:00.000Z';page.get_by_label('Campaign status',exact=True).select_option('scheduled');expect(page.get_by_text('Scheduled campaign',exact=True)).to_be_visible();page.get_by_role('button',name='Cancel campaign',exact=True).evaluate('(b)=>{b.click();b.click()}');expect(page.get_by_text('Scheduled campaign',exact=True)).to_have_count(0);page.get_by_label('Campaign status',exact=True).select_option('cancelled');expect(page.get_by_text('Scheduled campaign',exact=True)).to_be_visible();assert (25,'') in reads;assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');assert not errors,errors;context.close();print(f'PASS {width}: history/retry/paging/analytics, stale preview, recipient/link/rich fields, own tests, independent intent retries, WAT schedule/cancel',flush=True)
  browser.close()
finally:os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
