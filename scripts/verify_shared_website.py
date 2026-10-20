"""Exercise the real offline bilingual website with Playwright Chromium."""
import argparse,csv,json,time,traceback
from pathlib import Path
from playwright.sync_api import sync_playwright

p=argparse.ArgumentParser();p.add_argument('url');p.add_argument('output',type=Path);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
result={'checks':[],'errors':[],'external':[],'bad_responses':[],'timings':{},'viewports':[],'charts':[]}
with sync_playwright() as pw:
 b=pw.chromium.launch(args=['--no-sandbox']);result['browser']=b.version
 ctx=b.new_context(viewport={'width':1440,'height':1000},permissions=['clipboard-read','clipboard-write'])
 def route(r):
  if r.request.url.startswith(a.url) or r.request.url.startswith(('data:','blob:')):r.continue_()
  else:result['external'].append(r.request.url);r.abort()
 ctx.route('**/*',route);page=ctx.new_page();page.on('pageerror',lambda e:result['errors'].append(str(e)));page.on('response',lambda r:result['bad_responses'].append([r.status,r.url]) if r.status>=400 else None)
 try:
  t=time.perf_counter();page.goto(a.url+'/qmd/site-zh-index.html',wait_until='domcontentloaded');page.locator('.report-navbar').wait_for();page.locator('#quarto-document-content').wait_for();result['timings']['home_visible_s']=time.perf_counter()-t
  page.locator('button[data-report-theme]').click();page.wait_for_function("document.documentElement.dataset.reportTheme==='dark'");result['timings']['home_ready_s']=time.perf_counter()-t;page.locator('button[data-report-theme]').click();result['checks'].append('theme toggle')
  home_requests=page.evaluate("performance.getEntriesByType('resource').map(n=>({url:n.name,ms:n.duration,bytes:n.transferSize}))");result['home_resources']=home_requests
  assert not any('plotly.min.js' in n['url'] or 'table-' in n['url'] or '/mermaid/' in n['url'] for n in home_requests)
  result['checks'].append('home excludes Plotly, Mermaid runtime and full DEG data')
  page.screenshot(path=str(a.output/'desktop.png'))
  t=time.perf_counter();page.locator('a[data-report-language]').focus();page.keyboard.press('Enter');page.wait_for_url('**/site-en-index.html');page.locator('.report-navbar').wait_for();result['timings']['language_switch_s']=time.perf_counter()-t
  assert page.locator('html').get_attribute('lang')=='en';result['checks'].append('keyboard language switch and English state')
  page.locator('a[data-report-language]').click();page.wait_for_url('**/site-zh-index.html')
  t=time.perf_counter();page.goto(a.url+'/qmd/site-zh-results.html',wait_until='domcontentloaded');page.locator('#quarto-document-content').wait_for();result['timings']['results_visible_s']=time.perf_counter()-t
  table=page.locator('.report-data-table[data-row-count="23075"]');table.scroll_into_view_if_needed();table.locator('table[data-ready=true]').wait_for(timeout=30000);result['timings']['deg_search_ready_s']=time.perf_counter()-t
  node=table.locator('table[data-ready=true]');assert node.evaluate('(n)=>n._reportTable.rows().count()')==23075
  sample=node.evaluate('(n)=>n._reportTable.row(0).data()[0]');search=table.locator('input[type=search]');search.fill(sample);page.wait_for_function("document.querySelector('.report-data-table[data-row-count=\"23075\"] table[data-ready=true]')._reportTable.rows({search:'applied'}).count()===1")
  search.fill('');page.wait_for_timeout(200);node.evaluate('(n)=>n._reportTable.search(\'\').draw()')
  headers=table.locator('.dt-scroll-head th');headers.nth(2).click();assert node.evaluate('(n)=>n._reportTable.order()[0][0]')==2
  table.locator('button.next').click();assert node.evaluate('(n)=>n._reportTable.page.info().page')==1
  table.locator('button.buttons-copy').click();page.wait_for_timeout(250);clipboard=page.evaluate('navigator.clipboard.readText()');assert sample in clipboard and len(clipboard.splitlines())>=23076
  with page.expect_download() as dl:table.locator('button.buttons-csv').click()
  path=a.output/'deg-export.csv';dl.value.save_as(path)
  with path.open(encoding='utf-8-sig',newline='') as f:rows=[row for row in csv.reader(f) if row]
  assert len(rows)==23076
  result['checks'].append('full DEG: 23075 rows, search, numeric sorting, pagination, full clipboard and CSV export')
  page.screenshot(path=str(a.output/'results.png'))
  for lang in ('zh','en'):
   for name in ('qc','results'):
    page.goto(a.url+f'/qmd/site-{lang}-{name}.html');page.wait_for_function("[...document.querySelectorAll('.plotly-graph-div')].every(n=>n._fullLayout)")
    charts=page.locator('.plotly-graph-div');assert charts.count()>0
    for i in range(charts.count()):
     chart=charts.nth(i)
     panes=chart.evaluate("(n)=>{const ids=[];for(let p=n.parentElement;p;p=p.parentElement)if(p.classList.contains('tab-pane'))ids.unshift(p.id);return ids;}")
     for pane in panes:
      control=page.locator('[data-bs-target="#'+pane+'"], a[href="#'+pane+'"]')
      if control.count():control.first.click()
     chart.scroll_into_view_if_needed();assert chart.evaluate('(n)=>n._fullData.length>0')
     chart.evaluate('(n)=>Plotly.relayout(n,{"dragmode":"zoom"})')
     chart.evaluate('(n)=>Plotly.Fx.hover(n,[{curveNumber:0,pointNumber:0}])')
    result['charts'].append({'language':lang,'page':name,'count':charts.count()})
    first=charts.first;first.evaluate('(n)=>Plotly.restyle(n,{visible:"legendonly"},[0])');assert first.evaluate('(n)=>n.data[0].visible')=='legendonly';first.evaluate('(n)=>Plotly.restyle(n,{visible:true},[0])')
    # Exercise local export without changing the published high resolution default.
    exported=first.evaluate('(n)=>Plotly.toImage(n,{format:"png",width:320,height:200,scale:1})');assert exported.startswith('data:image/png')
  result['checks'].append('all Plotly charts initialized; zoom, hover, legend and PNG export on both languages')
  for width in (1440,768,390):
   page.set_viewport_size({'width':width,'height':900});page.goto(a.url+'/qmd/site-en-index.html');page.wait_for_timeout(200)
   bounds=page.locator('.report-navbar').evaluate('(n)=>({width:n.scrollWidth,client:n.clientWidth,children:[...n.children].map(c=>({x:c.getBoundingClientRect().x,right:c.getBoundingClientRect().right}))})')
   result['viewports'].append({'width':width,'bounds':bounds,'document_width':page.evaluate('document.documentElement.scrollWidth')})
   assert bounds['width']<=width+1
   if width<1000:
    page.locator('.report-nav-toggle').click();page.locator('.report-menu').wait_for(state='visible');page.locator('.report-menu .nav-link').last.click()
   page.screenshot(path=str(a.output/f'viewport-{width}.png'))
  result['checks'].append('desktop, tablet and mobile navigation')
 except Exception as error:result['errors'].append(traceback.format_exc())
 finally:
  result['status']='PASS' if not any(result[key] for key in ('errors','external','bad_responses')) else 'FAIL'
  (a.output/'browser.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False));b.close()
