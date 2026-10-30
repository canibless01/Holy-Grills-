"""Actual production boot and worker controller changes; controlled API reads only.

Run against scripts/serve-static.mjs after build. No subscription or send.
"""
import argparse,json,os,time
from pathlib import Path
from playwright.sync_api import sync_playwright

parser=argparse.ArgumentParser()
parser.add_argument('--origin',default='http://127.0.0.1:4175')
parser.add_argument('--output',default='../work/shared-worker-browser.json')
args=parser.parse_args()
result={'mode':'actual production boot and real service worker activation; controlled API reads, SDK-style query registration, no subscription/send'}
with sync_playwright() as pw:
    options={'server':os.environ['HTTPS_PROXY'],'bypass':'localhost,127.0.0.1'} if os.environ.get('HTTPS_PROXY') else None
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'],**({'proxy':options} if options else {}))
    context=browser.new_context()
    context.route('**/api/**',lambda route:route.fulfill(json={'campuses':[]} if route.request.url.endswith('/campuses') else []))
    page=context.new_page()
    try:
        page.goto(args.origin,wait_until='domcontentloaded')
        page.wait_for_function('()=>Boolean(navigator.serviceWorker.controller)',timeout=45000)
        page.evaluate("window.__sharedWorkerDraft='keep me'")
        # Exactly the same root script, with the query OneSignal uses.
        worker='/service-worker.js?appId=471bd695-2342-4521-aa0f-8c93d7ce805f&sdkVersion=160610'
        page.evaluate('(url)=>{navigator.serviceWorker.register(url)}',worker)
        page.wait_for_timeout(6000)
        result['document_preserved_on_sdk_registration']=page.evaluate("window.__sharedWorkerDraft==='keep me'")
        result['controller_after_sdk']=page.evaluate('navigator.serviceWorker.controller?.scriptURL')
        assert result['document_preserved_on_sdk_registration'],result
        assert 'appId=' in result['controller_after_sdk'],result
        # A subsequent app boot must retain the SDK-owned query URL.
        page.reload(wait_until='domcontentloaded')
        page.wait_for_timeout(4000)
        page.evaluate("window.__returnDraft='keep on return'")
        page.wait_for_timeout(3000)
        result['controller_on_return']=page.evaluate('navigator.serviceWorker.controller?.scriptURL')
        result['return_document_preserved']=page.evaluate("window.__returnDraft==='keep on return'")
        assert result['controller_on_return']==result['controller_after_sdk'] and result['return_document_preserved'],result
        result['pass']=True
    finally:
        Path(args.output).parent.mkdir(parents=True,exist_ok=True)
        Path(args.output).write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2))
        browser.close()
