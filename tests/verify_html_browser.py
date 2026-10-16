"""Exercise the actual rendered HTML offline in Chromium; never mock Plotly/DOM."""
import argparse
import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright


def verify(source, output):
    output.mkdir(parents=True,exist_ok=True)
    checks=[];errors=[]
    try:
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True,args=['--no-sandbox'],timeout=15000)
            page=browser.new_page(viewport={'width':1440,'height':1100})
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(source.resolve().as_uri(),wait_until='load',timeout=120000)
            page.wait_for_function("typeof Plotly !== 'undefined'",timeout=30000)
            links=page.locator('.report-navbar a.nav-link')
            for i in range(links.count()):
                link=links.nth(i);name=link.inner_text();target=link.get_attribute('aria-controls')
                link.click();page.wait_for_timeout(250)
                visible=page.locator('.report-page:visible')
                if visible.count()!=1 or visible.first.get_attribute('id')!=target:
                    raise AssertionError('Navigation failed: '+name)
                checks.append('navigation:'+name)
            # Enter each real report page and inspect actual Plotly layouts.
            for i in range(links.count()):
                links.nth(i).click();page.wait_for_timeout(200)
                charts=page.locator('.report-page:visible .plotly-graph-div')
                for j in range(charts.count()):
                    assert charts.nth(j).evaluate('(node)=>!!node._fullLayout && node._fullData.length>0')
                if charts.count():checks.append('plotly:'+str(charts.count()))
            assert page.locator('table').count()>0
            assert page.evaluate("!!document.querySelector('table.dataTable, .dt-container, .itables')")
            checks.append('ITables initialized')
            assert page.locator('#TOC a').count()>0
            # The about page hides the TOC by design; return to a content page first.
            page.locator('.report-navbar a.nav-link').first.click()
            page.wait_for_timeout(250)
            page.locator('#TOC a').first.click(timeout=10000);page.wait_for_timeout(250)
            checks.append('TOC navigation')
            page.screenshot(path=str(output/'html.png'),full_page=True)
            browser.close()
    except Exception as error:
        errors.append(type(error).__name__+': '+str(error)[:4000])
    result={'status':'FAIL' if errors else 'PASS','checks':checks,'errors':errors}
    (output/'html-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('html',type=Path);parser.add_argument('--output',type=Path,default=Path('output/html-validation'))
    parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    if args.worker:
        result=verify(args.html,args.output)
    else:
        args.output.mkdir(parents=True,exist_ok=True)
        command=[sys.executable,__file__,str(args.html),'--output',str(args.output),'--worker']
        process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
        try:
            stdout,stderr=process.communicate(timeout=90)
            target=args.output/'html-validation.json'
            if target.exists():result=json.loads(target.read_text())
            else:result={'status':'FAIL','checks':[],'errors':[f'Browser worker exited {process.returncode}: '+stderr[-3000:]]}
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL)
            process.communicate()
            result={'status':'FAIL','checks':[],'errors':['Browser process did not finish within 90 seconds; runtime verification unavailable on this host.']}
        (args.output/'html-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False));raise SystemExit(result['status']!='PASS')
