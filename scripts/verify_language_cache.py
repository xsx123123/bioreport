"""Offline browser checks for cached bilingual editions and bounded warm switches."""
import argparse
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright


def verify(source, engine):
    errors, remote = [], []
    with sync_playwright() as pw:
        browser = getattr(pw, engine).launch()
        context = browser.new_context(viewport={'width':1440, 'height':900})
        context.add_init_script('''const Decoder = window.DecompressionStream;
          window.__decodeCount=0;
          window.DecompressionStream=function(...args){window.__decodeCount++;return new Decoder(...args);};''')
        for scheme in ['http','https']:
            context.route(scheme+'://**/*', lambda route:(remote.append(route.request.url),route.abort()))
        page=context.new_page()
        page.on('pageerror',lambda error:errors.append(str(error)))
        start=time.perf_counter()
        page.goto(source.resolve().as_uri(),wait_until='load',timeout=120000)
        page.locator('#loading').wait_for(state='hidden',timeout=120000)
        result={'home_visible_s':time.perf_counter()-start,'engine':engine,'browser':browser.version}
        frame=page.locator('#report').element_handle().content_frame()
        frame.evaluate("window.__cachedDocumentProbe='original';location.hash='#report-page-5'")
        region=frame.locator('.report-page[data-active=true] .report-data-table').first
        if region.count():region.scroll_into_view_if_needed()
        frame.locator('.report-page[data-active=true] input[type=search]').first.wait_for(timeout=60000)
        start=time.perf_counter()
        frame.locator('[data-report-language]').click(no_wait_after=True)
        page.wait_for_function("document.querySelector('#report')?.contentDocument?.documentElement?.lang==='en'",timeout=120000)
        page.locator('#loading').wait_for(state='hidden',timeout=120000)
        result['first_switch_s']=time.perf_counter()-start
        cdp=context.new_cdp_session(page) if engine=='chromium' else None
        if cdp: cdp.send('Performance.enable')
        result['warm_switches_s'],result['heap_bytes']=[],[]
        result['automation_round_trip_s']=[]
        # Frame visibility changes can make Playwright's click protocol wait
        # after the document has already painted. Measure user latency from
        # the real DOM click to the shell's post-paint loading dismissal.
        page.evaluate('''() => {
          const loading=document.getElementById('loading');
          new MutationObserver(()=>{
            if(loading.hidden && window.__switchStart!==undefined)
              window.__switchMS=performance.now()-window.__switchStart;
          }).observe(loading,{attributes:true,attributeFilter:['hidden']});
        }''')
        for index in range(10):
            language='zh' if index%2==0 else 'en'
            frame=page.locator('#report').element_handle().content_frame()
            theme=frame.evaluate('document.documentElement.dataset.reportTheme')
            frame.evaluate('''() => document.addEventListener('click',event=>{
              if(event.target.closest('[data-report-language]')) {
                parent.__switchStart=parent.performance.now();parent.__switchMS=null;
              }
            },{capture:true,once:true})''')
            start=time.perf_counter()
            frame.locator('[data-report-language]').click(no_wait_after=True)
            page.wait_for_function("lang=>document.querySelector('#report')?.contentDocument?.documentElement?.lang.startsWith(lang)",arg=language)
            page.locator('#loading').wait_for(state='hidden')
            result['automation_round_trip_s'].append(time.perf_counter()-start)
            elapsed=page.evaluate('window.__switchMS')/1000
            result['warm_switches_s'].append(elapsed)
            print('warm switch', index, round(elapsed,4), flush=True)
            assert elapsed<=1,(engine,index,elapsed)
            frame=page.locator('#report').element_handle().content_frame()
            assert frame.evaluate('location.hash')=='#report-page-5'
            assert frame.evaluate('document.documentElement.dataset.reportTheme')==theme
            if language=='zh': assert frame.evaluate('window.__cachedDocumentProbe')=='original'
            assert page.locator('iframe').count()==2
            assert page.locator('iframe:not([hidden])').count()==1
            if cdp:
                cdp.send('HeapProfiler.collectGarbage')
                metrics=cdp.send('Performance.getMetrics')['metrics']
                result['heap_bytes'].append(next(m['value'] for m in metrics if m['name']=='JSHeapUsedSize'))
        if result['heap_bytes']:
            first,last=result['heap_bytes'][0],result['heap_bytes'][-1]
            assert last-first<max(10_000_000,first*.1),result['heap_bytes']
        frame=page.locator('#report').element_handle().content_frame()
        frame.locator('button[data-report-theme]').click()
        theme=frame.evaluate('document.documentElement.dataset.reportTheme')
        frame.locator('[data-report-language]').click(no_wait_after=True)
        page.wait_for_function("document.querySelector('#report')?.contentDocument?.documentElement?.lang.startsWith('zh')")
        page.locator('#loading').wait_for(state='hidden')
        frame=page.locator('#report').element_handle().content_frame()
        assert frame.evaluate('document.documentElement.dataset.reportTheme')==theme
        result['decodes']=page.evaluate('window.__decodeCount')
        assert result['decodes']==2
        result.update(errors=errors,remote_requests=remote)
        assert not errors and not remote,result
        fallback=context.new_page()
        fallback.add_init_script('window.DecompressionStream=undefined;')
        fallback.goto(source.resolve().as_uri(),wait_until='load',timeout=120000)
        fallback.locator('#loading button').wait_for()
        message=fallback.locator('#loading').inner_text()
        assert '此浏览器' in message and 'This browser' in message
        result['unsupported_fallback']=True
        browser.close()
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('--engine',choices=['chromium','firefox'],default='chromium')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=verify(args.source,args.engine)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
