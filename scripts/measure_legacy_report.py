import json,time
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path('/home/zj/zj_code_libarary/bioreport/output/performance-20261020/before')
with sync_playwright() as pw:
 b=pw.chromium.launch(headless=True,args=['--no-sandbox']);p=b.new_page(viewport={'width':1440,'height':1000});errors=[];p.on('pageerror',lambda e:errors.append(str(e)))
 t=time.perf_counter();p.goto('http://127.0.0.1:8767/before/X101SC26098749-Z01-J001_report.html',wait_until='domcontentloaded',timeout=120000)
 p.locator('#loading').wait_for(state='hidden',timeout=120000);visible=time.perf_counter()-t
 f=p.frames[-1];f.wait_for_function("[...document.querySelectorAll('.plotly-graph-div')].every(n=>n._fullLayout) && !!document.querySelector('.dt-container')",timeout=120000);ready=time.perf_counter()-t
 p.screenshot(path=str(root/'desktop.png'))
 r=time.perf_counter();f.evaluate("location.hash='#report-page-5'");f.locator('.report-page:visible input[type=search]').first.wait_for(timeout=30000);results=time.perf_counter()-r
 sw=time.perf_counter();p.locator('[data-edition=en]').click();p.wait_for_function("document.querySelector('#report').contentDocument?.documentElement?.lang==='en'",timeout=120000);p.locator('#loading').wait_for(state='hidden',timeout=120000);switch=time.perf_counter()-sw
 result={'browser':b.version,'home_visible_s':visible,'home_ready_s':ready,'results_navigation_and_search_s':results,'switch_s':switch,'errors':errors}
 (root/'browser.json').write_text(json.dumps(result,indent=2));print(result);b.close()
