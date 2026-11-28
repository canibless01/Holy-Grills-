"""Native newsletter inputs, pagination, preview, response-loss and unsubscribe recovery."""
import os,re,signal,subprocess,tempfile,time,uuid
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import sync_playwright,expect
repo=Path(__file__).resolve().parents[1];out=Path(tempfile.mkdtemp(prefix='hg-newsletter-'));C='11111111-1111-4111-8111-111111111111';U='22222222-2222-4222-8222-222222222222'
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5285','--strictPort'],cwd=repo,env=dict(os.environ,VITE_API_BASE_URL='/api'),start_new_session=True,stdout=(out/'vite.log').open('w'),stderr=subprocess.STDOUT)
expect.set_options(timeout=15000)
try:
 time.sleep(2)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  for width,role in ((393,'admin'),(1280,'super_admin')):
   state={'subfail':True,'loss':True,'unsubscribe_loss':True,'campaigns':[{'id':str(uuid.uuid4()),'subject':'Campaign '+str(i),'body':'First\n\nSecond','status':'queued','campus_id':C,'sent_count':0,'created_at':'2026-11-13T10:00:00Z'} for i in range(26)],'subs':[{'id':str(uuid.uuid4()),'email':f'person{i}@example.invalid','created_at':'2026-11-13T10:00:00Z','source':'footer'} for i in range(26)]};writes=[];errors=[];reads=[]
   def api(route):
    req=route.request;url=urlparse(req.url);path=url.path;query=parse_qs(url.query);data={}
    if path.endswith('/auth/me'):data={'id':U,'role':role,'campus_id':C,'is_active':True,'profile':{'id':U,'role':role,'campus_id':C}}
    elif path.endswith('/campuses'):data=[{'id':C,'name':'FUTA','is_active':True}]
    elif path.endswith('/newsletter'):
     if state['subfail']:state['subfail']=False;route.fulfill(status=503,json={'error':'Controlled newsletter read failure'});return
     offset=int(query.get('offset',['0'])[0]);limit=int(query.get('limit',['0'])[0]);assert limit==25;reads.append(('subs',offset));data=state['subs'][offset:offset+limit]
    elif path.endswith('/newsletter/admin-unsubscribe'):
     email=req.post_data_json['email'];state['subs']=[s for s in state['subs'] if s['email']!=email]
     if state['unsubscribe_loss']:state['unsubscribe_loss']=False;route.fulfill(status=503,json={'error':'Controlled unsubscribe response loss'});return
     data={'message':'Unsubscribed'}
    elif path.endswith('/newsletter/campaigns/test'):
     assert req.post_data_json=={'subject':'Launch invitation','body':'First paragraph\n\nSecond paragraph'};data={'sent_to':'admin@example.invalid'}
    elif path.endswith('/newsletter/campaigns'):
     if req.method=='POST':
      body=req.post_data_json;writes.append(body);assert body['subject']=='Launch invitation' and body['body']=='First paragraph\n\nSecond paragraph'
      if role=='admin':assert 'campus_id' not in body and 'all_campuses' not in body
      else:assert body['campus_id']==C
      row=next((c for c in state['campaigns'] if c['id']==body['request_id']),None)
      if row is None:row={'id':body['request_id'],'subject':body['subject'],'body':body['body'],'status':'queued','campus_id':C};state['campaigns'].insert(0,row)
      if state['loss']:state['loss']=False;route.fulfill(status=503,json={'error':'Controlled committed campaign response loss'});return
      assert writes[0]==writes[1];data={'campaign':row,'replayed':True}
     else:
      offset=int(query.get('offset',['0'])[0]);limit=int(query.get('limit',['0'])[0]);assert limit==25;reads.append(('campaigns',offset));data=state['campaigns'][offset:offset+limit]
    elif path.endswith('/cancel'):
     row=next(c for c in state['campaigns'] if c['id']==path.split('/')[-2]);row['status']='cancelled';data={'campaign':row}
    elif '/newsletter/campaigns/' in path:data=next(c for c in state['campaigns'] if c['id']==path.split('/')[-1])
    elif any(path.endswith(s) for s in ('/sections','/early-supporters')):data=[]
    route.fulfill(json=data)
   ctx=browser.new_context(viewport={'width':width,'height':1000});ctx.route('**/api/**',api);ctx.add_init_script("sessionStorage.setItem('hg_access_token','controlled');localStorage.setItem('hg_user_role','"+role+"');localStorage.setItem('hg_admin_campus_id','"+C+"');localStorage.setItem('hg_user_campus_id','"+C+"');localStorage.setItem('hg_cookie_consent',JSON.stringify({essential:true,analytics:false,date:new Date().toISOString()}));")
   page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto('http://127.0.0.1:5285/admin?section=storefront');page.get_by_role('button',name=re.compile('^Newsletter')).click();expect(page.get_by_text('Newsletter reports could not be loaded. Retry before making changes.',exact=True)).to_be_visible();page.get_by_role('button',name='Retry',exact=True).click();expect(page.get_by_text('person0@example.invalid',exact=True)).to_be_visible()
   page.get_by_role('button',name='Next subscribers',exact=True).click();expect(page.get_by_text('person25@example.invalid',exact=True)).to_be_visible();expect(page.get_by_text('person0@example.invalid',exact=True)).to_have_count(0);page.get_by_role('button',name='Previous subscribers',exact=True).click();expect(page.get_by_text('person0@example.invalid',exact=True)).to_be_visible()
   page.get_by_role('button',name='Next campaigns',exact=True).click();expect(page.get_by_text('Campaign 25',exact=True)).to_be_visible();page.get_by_role('button',name='Previous campaigns',exact=True).click();expect(page.get_by_text('Campaign 0',exact=True)).to_be_visible()
   page.get_by_role('button',name='Unsubscribe',exact=True).first.click();expect(page.get_by_text('Controlled unsubscribe response loss',exact=True)).to_be_visible();expect(page.get_by_role('button',name='Unsubscribe',exact=True).first).to_be_enabled();page.get_by_role('button',name='Unsubscribe',exact=True).first.click();expect(page.get_by_text('person0@example.invalid',exact=True)).to_have_count(0)
   page.get_by_role('button',name='New',exact=True).click();form=page.get_by_role('dialog',name='New newsletter campaign',exact=True);form.get_by_role('button',name='Queue campaign',exact=True).click();assert not writes;form.get_by_label('Subject',exact=True).fill('Launch invitation');form.get_by_label('Message',exact=True).fill('First paragraph\n\nSecond paragraph')
   if role=='super_admin':form.get_by_label('Campus',exact=True).select_option(C)
   form.get_by_role('button',name='Send test to me',exact=True).click();expect(page.get_by_text('Preview accepted for delivery to admin@example.invalid.',exact=True)).to_be_visible();form.get_by_role('button',name='Queue campaign',exact=True).evaluate('(b)=>{b.click();b.click()}');expect(page.get_by_text('Controlled committed campaign response loss',exact=True)).to_be_visible();assert len(writes)==1;form.get_by_role('button',name='Queue campaign',exact=True).click();expect(form).to_have_count(0);assert len(writes)==2;expect(page.get_by_text('Launch invitation',exact=True)).to_be_visible()
   row=page.locator('div.flex.items-center.gap-3.rounded-xl').filter(has=page.get_by_text('Launch invitation',exact=True));row.get_by_role('button',name='View',exact=True).click();detail=page.get_by_role('dialog',name='Launch invitation',exact=True);expect(detail.get_by_text('First paragraph\n\nSecond paragraph',exact=True)).to_be_visible();detail.get_by_role('button',name='Close dialog',exact=True).click();row.get_by_role('button',name='Cancel',exact=True).click();page.get_by_role('button',name='Stop',exact=True).click();expect(row.get_by_text('cancelled',exact=True)).to_be_visible();assert ('subs',25) in reads and ('campaigns',25) in reads;assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');assert not errors,errors;ctx.close();print(f'PASS {width} {role}: read Retry, both pagers, unsubscribe recovery, fields/test, stable creation retry, detail/paragraphs, cancel',flush=True)
  browser.close()
finally:os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
