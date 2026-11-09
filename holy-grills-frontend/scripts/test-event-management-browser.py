"""Admin event operations on mobile/desktop; controlled API, no production writes."""
import os,signal,subprocess,tempfile,time,uuid
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import sync_playwright,expect
repo=Path(__file__).resolve().parents[1];out=Path(tempfile.mkdtemp(prefix='hg-event-management-'))
a='11111111-1111-4111-8111-111111111111';b='22222222-2222-4222-8222-222222222222';ticket='33333333-3333-4333-8333-333333333333';tier='44444444-4444-4444-8444-444444444444'
png='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII='
expect.set_options(timeout=15000)
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5268','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
try:
 time.sleep(2)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  for width in (360,393,768,1280,1440,1536,1920):
   state={'checked':False,'lost':True,'regs_fail':True,'tier_fail':True,'sales_fail':True,'tier_active':True};reads=[];writes=[];errors=[]
   event_rows=[{'id':str(uuid.UUID(int=i+100)),'title':f'Campus event {i}','campus_id':a,'is_published':True,'location':'FUTA','starts_at':'2026-11-12T09:00:00+00:00','ends_at':'2026-11-12T12:00:00+00:00','capacity':100,'max_attendees':100,'hp_per_attendee':25,'hp_reward':25,'funding_source':'host_prepaid'} for i in range(26)]
   event_rows[0].update(title='Flame Night: Live Grill & Music',location='FUTA Main Campus, Amphitheatre',is_featured=True,is_paid=True,capacity=300,max_attendees=300,hp_per_attendee=100)
   def api(route):
    request=route.request;url=urlparse(request.url);path=url.path;q=parse_qs(url.query);data={}
    if path.endswith('/auth/me'):data={'id':'controlled','role':'super_admin','campus_id':a,'profile':{'id':'controlled','role':'super_admin','campus_id':a},'is_active':True}
    elif path.endswith('/upload/status'):data={'configured':True,'cloud_name':'test-cloud'}
    elif path.endswith('/upload/signature'):data={'signature':'controlled','timestamp':1,'api_key':'controlled','cloud_name':'test-cloud','folder':'events'}
    elif path.endswith('/campuses'):data=[{'id':a,'name':'Campus A','is_active':True},{'id':b,'name':'Campus B','is_active':True}]
    elif path.endswith('/events/admin'):
     reads.append(q);offset=int(q.get('offset',['0'])[0]);data={'events':event_rows[offset:offset+int(q.get('limit',['25'])[0])]}
    elif path.endswith('/checkin'):
     writes.append((path,request.post_data_json));replay=state['checked'];state['checked']=True
     if state['lost']:state['lost']=False;route.fulfill(status=409,json={'error':'Controlled lost check-in response; retry same ticket'});return
     data={'completed':True,'replayed':replay,'hp_added_to_active':25}
    elif path.endswith('/registrants'):
     if state['regs_fail']:route.fulfill(status=503,json={'error':'Controlled registrant failure'});return
     data={'registrants':[{'ticket_id':ticket,'full_name':'=Attendee','email':'attendee@example.invalid','tier_name':'Regular','checked_in':state['checked'],'status':'confirmed','payment_status':'paid','refundable':not state['checked']}]}
    elif path.endswith('/qr'):data={'event_id':event_rows[0]['id'],'qr_payload':f"hg-event:{event_rows[0]['id']}:"+'a'*32,'qr_image':png}
    elif path.endswith('/tiers'):
     if state['tier_fail']:route.fulfill(status=503,json={'error':'Controlled tier failure'});return
     data=[{'id':tier,'name':'Regular','price_naira':9999,'capacity':100,'sold_count':2,'is_active':state['tier_active']}]
    elif '/events/tiers/' in path and request.method=='PATCH':
     writes.append((path,request.post_data_json));state['tier_active']=request.post_data_json['is_active'];data={'id':tier,'is_active':state['tier_active']}
    elif path.endswith('/sales'):
     if state['sales_fail']:route.fulfill(status=503,json={'error':'Controlled sales failure'});return
     data={'summary':{'confirmed_count':1,'capacity':100,'confirmed_cash':1600},'tiers':[{'id':tier,'name':'Regular','price_naira':9999,'capacity':100,'sold_count':2,'confirmed_count':1}]}
    elif '/events/' in path and request.method=='PATCH':
     body=request.post_data_json;writes.append((path,body));next(row for row in event_rows if row['id']==path.split('/')[-1]).update(body);data=body
    route.fulfill(status=200,json=data)
   context=browser.new_context(viewport={'width':width,'height':1000},accept_downloads=True);context.route('**/api/**',api)
   context.route('https://api.cloudinary.com/**',lambda route:route.fulfill(json={'secure_url':'https://res.cloudinary.com/test-cloud/image/upload/events/native.png'}))
   context.route('https://res.cloudinary.com/**',lambda route:route.fulfill(content_type='image/png',body=__import__('base64').b64decode(png.split(',')[1])))
   context.add_init_script("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_role','super_admin');localStorage.setItem('hg_user_campus_id','"+a+"');localStorage.setItem('hg_admin_campus_id','"+a+"');")
   page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto('http://127.0.0.1:5268/admin?section=events');expect(page.get_by_text('Flame Night: Live Grill & Music',exact=True)).to_be_visible()
   page.evaluate("localStorage.setItem('hg_cookie_consent',JSON.stringify({essential:true,analytics:false,date:new Date().toISOString()}))")
   consent=page.get_by_role('button',name='Essential only',exact=True)
   if consent.is_visible():consent.click()
   card=page.get_by_role('article',name='Flame Night: Live Grill & Music',exact=True)
   title=card.get_by_role('heading',name='Flame Night: Live Grill & Music',exact=True)
   title_box=title.bounding_box();card_box=card.bounding_box()
   assert title_box['width']>220,(width,title_box)
   assert title_box['height']<100,(width,title_box)
   assert card_box['x']>=0 and card_box['x']+card_box['width']<=width+1,(width,card_box)
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),f'Horizontal overflow at {width}'
   heading=page.get_by_role('heading',name='Events',exact=True)
   expect(heading).to_be_visible()
   assert heading.evaluate('(el)=>el.scrollWidth<=el.clientWidth'),f'Header truncation at {width}'
   for name in ('Ticket Tiers','Sales Dashboard','Registrants','Refund history','QR','Edit event'):
    box=card.get_by_role('button',name=name,exact=True).bounding_box()
    assert box['height']>=44 and box['width']>=70,(width,name,box)
    assert box['y']>=title_box['y']+title_box['height'],(width,name,box)
   page.screenshot(path=str(out/f'events-layout-{width}.png'),full_page=False)
   print(f'PASS width={width}: long title/venue, readable header, no horizontal overflow, labelled touch controls; screenshot={out}/events-layout-{width}.png',flush=True)
   if width not in (393,1280):
    assert not errors,errors
    context.close();continue
   page.get_by_role('button',name='Next events',exact=True).click();expect(page.get_by_text('Campus event 25',exact=True)).to_be_visible();assert reads[-1]['offset']==['25']
   page.get_by_role('switch').first.click();expect(page.get_by_text('Draft',exact=True)).to_be_visible();assert writes[-1][1]=={'is_published':False}
   page.get_by_role('button',name='Previous events',exact=True).click();expect(page.get_by_text('Flame Night: Live Grill & Music',exact=True)).to_be_visible()
   page.get_by_role('button',name='Edit event',exact=True).first.click();dialog=page.get_by_role('dialog',name='Edit Event',exact=True)
   expect(dialog.get_by_label('Starts (WAT)',exact=True)).to_have_value('2026-11-12T10:00');expect(dialog.get_by_label('Ends (WAT)',exact=True)).to_have_value('2026-11-12T13:00');expect(dialog.get_by_label('Funding Source',exact=True)).to_have_value('host_prepaid')
   dialog.locator('input[type=file]').set_input_files({'name':'event.png','mimeType':'image/png','buffer':__import__('base64').b64decode(png.split(',')[1])})
   expect(dialog.locator('img')).to_have_attribute('src','https://res.cloudinary.com/test-cloud/image/upload/events/native.png')
   dialog.get_by_role('button',name='Save Changes',exact=True).click();expect(dialog).to_have_count(0)
   assert writes[-1][1]['image_url']=='https://res.cloudinary.com/test-cloud/image/upload/events/native.png'
   page.get_by_role('button',name='QR',exact=True).first.click();page.get_by_role('button',name='Generate QR',exact=True).click();qr=page.get_by_role('dialog',name='Event Check-in QR',exact=True);expect(qr.get_by_alt_text('Venue check-in QR code',exact=True)).to_be_visible();assert qr.get_by_alt_text('Venue check-in QR code',exact=True).evaluate('(img)=>img.complete&&img.naturalWidth>0')
   expect(qr.get_by_role('link',name='Download venue QR',exact=True)).to_have_attribute('download',f"event-{event_rows[0]['id']}-venue-qr.png");qr.get_by_role('button',name='Close dialog',exact=True).click()
   page.get_by_role('button',name='Registrants',exact=True).first.click();regs=page.get_by_role('dialog',name='Event Registrants',exact=True);expect(regs.get_by_role('alert')).to_be_visible();expect(regs.get_by_text('No registrants match your filters.',exact=True)).to_have_count(0)
   state['regs_fail']=False;regs.get_by_role('button',name='Retry',exact=True).click();expect(regs.get_by_text('=Attendee',exact=True)).to_be_visible();regs.get_by_label('Find attendee',exact=True).fill('attendee@example.invalid');expect(regs.get_by_text('=Attendee',exact=True)).to_be_visible()
   regs.get_by_role('button',name='Check in attendee',exact=True).evaluate('(b)=>{b.click();b.click()}');expect(regs.get_by_role('alert')).to_contain_text('Controlled lost check-in response');assert len([w for w in writes if w[0].endswith('/checkin')])==1
   regs.get_by_role('button',name='Check in attendee',exact=True).click();expect(regs.get_by_text('✓ Checked in',exact=True)).to_be_visible();expect(regs.get_by_role('status')).to_contain_text('already checked in');assert len([w for w in writes if w[0].endswith('/checkin')])==2
   with page.expect_download() as download:regs.get_by_role('button',name='Export CSV',exact=True).click()
   assert "'=Attendee" in Path(download.value.path()).read_text()
   regs.get_by_role('button',name='Close dialog',exact=True).click();page.get_by_role('button',name='Ticket Tiers',exact=True).first.click();tiers=page.get_by_role('dialog',name='Ticket Tiers',exact=True);expect(tiers.get_by_role('alert')).to_be_visible();state['tier_fail']=False;tiers.get_by_role('button',name='Retry',exact=True).click();expect(tiers.get_by_text('Regular',exact=True)).to_be_visible()
   tiers.get_by_role('switch',name='Sell Regular tickets',exact=True).click();expect(tiers.get_by_role('switch',name='Sell Regular tickets',exact=True)).to_have_attribute('aria-checked','false');assert writes[-1][1]=={'is_active':False};tiers.get_by_role('button',name='Close dialog',exact=True).click()
   page.get_by_role('button',name='Sales Dashboard',exact=True).first.click();sales=page.get_by_role('dialog',name='Ticket Sales Dashboard',exact=True);expect(sales.get_by_role('alert')).to_be_visible();state['sales_fail']=False;sales.get_by_role('button',name='Retry',exact=True).click();expect(sales.get_by_text('Cash on confirmed tickets',exact=True)).to_be_visible();expect(sales.get_by_text('₦1,600',exact=True)).to_be_visible()
   assert not errors,errors
   context.close();print(f'PASS width={width}: event paging/publication, WAT editing, funding, local QR display/download, read Retry, attendee search/admission replay, CSV formula defense, tier sales switch and recorded cash report')
  browser.close()
finally:
 os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
