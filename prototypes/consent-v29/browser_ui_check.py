"""Optional real-browser verification. Requires installed Playwright and Chromium.

No dependencies are downloaded by this script. It creates an isolated local-only
fixture and denies non-loopback page requests. A browser launch failure is a failed
verification, never silently counted as a pass. No screenshots are saved.
"""
import argparse
import json
import threading
from owner_ui_service import OwnerUIService
from local_owner_app import LoopbackServer


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chromium',default='/usr/bin/chromium',help='Explicit installed Chromium executable')
    args=parser.parse_args()
    ui=OwnerUIService();server=LoopbackServer(ui)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    report={'scope':'fictional loopback UI only','browser_passed':False,'visual_review_performed':False}
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=args.chromium,headless=True)
            try:
                context=browser.new_context(viewport={'width':1280,'height':900})
                blocked=[];errors=[]
                def route(r):
                    if r.request.url.startswith(server.origin+'/'):r.continue_()
                    else:blocked.append(r.request.url);r.abort()
                context.route('**/*',route)
                page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(server.origin);page.get_by_role('heading',name='Start with explicit identities').wait_for()
                def confirm(phrase):
                    page.locator('#confirmation').fill(phrase);page.locator('#dialogConfirm').click()
                    page.locator('#confirmDialog').wait_for(state='hidden')
                for owner in ('alice','bob','charlie','dana'):
                    article=page.locator('article').filter(has=page.get_by_role('heading',name=owner,exact=True))
                    article.get_by_role('button',name='Review binding').click();confirm('BIND '+owner)
                    if owner!='dana':article.get_by_role('button',name='Binding approved').wait_for()
                page.get_by_role('heading',name='alice’s inbox').wait_for()
                page.get_by_role('button',name='Prepare next review').click()
                page.get_by_role('button',name='Approve exact request').wait_for()
                page.get_by_role('button',name='Approve exact request').click();page.locator('#dialogCancel').click()
                assert ui.state('alice')['inbox'][0]['state']=='pending'
                page.get_by_role('button',name='Defer',exact=True).click()
                page.get_by_role('button',name='Open review').click()
                page.get_by_role('button',name='Resume review').wait_for()
                assert page.get_by_role('button',name='Approve exact request').count()==0
                page.get_by_role('button',name='Resume review').click()
                for _ in range(25):
                    owner=page.locator('#owner').input_value()
                    page.get_by_role('button',name='Approve exact request').click();confirm('APPROVE '+owner)
                    page.get_by_role('button',name='Submit approved request').click()
                    page.get_by_text('Submitted means the control was applied or the message was enqueued. It is not evidence of delivery.').wait_for()
                    if page.get_by_role('button',name='View delivery status').count():
                        page.get_by_role('button',name='View delivery status').click()
                        page.get_by_role('button',name='Start approved delivery').click();confirm('SEND '+owner)
                        page.get_by_role('button',name='Process received message').click()
                        page.get_by_role('heading',name='Received and processed locally').wait_for()
                    if ui.state('alice')['summary']['agreed']:break
                    page.get_by_role('button',name='Prepare next review').click()
                    page.get_by_role('button',name='Approve exact request').wait_for()
                assert ui.state('alice')['summary']=={'agreed':True,'receiver_receipts':12,'transitions':12}
                page.reload();page.get_by_role('button',name='Refresh status').wait_for()
                page.go_back();page.wait_for_timeout(50)
                assert ui.state('alice')['summary']['receiver_receipts']==12
                page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(50)
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                assert not blocked and not errors
                report.update(browser_passed=True,full_flow={'receipts':12,'transitions':12},nonlocal_page_requests=blocked,page_errors=errors,
                              tested=['binding','dialog back','defer/resume','approve/submit','send/process','reload/back','mobile overflow'])
            finally:browser.close()
    except Exception as exc:
        report.update(error_type=type(exc).__name__,reason=str(exc).splitlines()[0])
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2);ui.close()
    print(json.dumps(report,indent=2))
    return 0 if report['browser_passed'] else 2


if __name__=='__main__':raise SystemExit(main())
