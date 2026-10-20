"""Measure a bilingual offline report; results are samples, not acceptance gates."""
import argparse
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


def measure(source):
    remote, errors = [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=['--no-sandbox'])
        page = browser.new_page(viewport={'width': 1440, 'height': 900})
        for scheme in ['http', 'https']:
            page.route(scheme + '://**/*', lambda route: (
                remote.append(route.request.url), route.abort()))
        page.on('pageerror', lambda error: errors.append(str(error)))
        start = time.perf_counter()
        page.goto(source.resolve().as_uri(), wait_until='load', timeout=120000)
        page.locator('#loading').wait_for(state='hidden', timeout=120000)
        result = {'home_visible_s': time.perf_counter() - start,
                  'browser': browser.version, 'bytes': source.stat().st_size}
        frame = page.locator('#report').element_handle().content_frame()
        start = time.perf_counter()
        frame.evaluate("location.hash='#report-page-5'")
        region=frame.locator('.report-page[data-active=true] .report-data-table').first
        if region.count():
            region.scroll_into_view_if_needed()
        frame.locator('.report-page[data-active=true] input[type=search]').first.wait_for(timeout=120000)
        result['results_search_control_s'] = time.perf_counter() - start
        result['language_switches_s'] = []
        result['language_switch_round_trip_s'] = []
        page.evaluate('''() => {
            const loading=document.getElementById('loading');
            new MutationObserver(()=>{
                if(loading.hidden && window.__switchStart!==undefined)
                    window.__switchMS=performance.now()-window.__switchStart;
            }).observe(loading,{attributes:true,attributeFilter:['hidden']});
        }''')
        for language in ['en', 'zh']:
            frame.evaluate('''() => document.addEventListener('click',event=>{
                if(event.target.closest('[data-report-language]')) {
                    parent.__switchStart=parent.performance.now();parent.__switchMS=null;
                }
            },{capture:true,once:true})''')
            start = time.perf_counter()
            frame.locator('[data-report-language]').click(no_wait_after=True)
            page.wait_for_function("language => document.querySelector('#report')?.contentDocument?.documentElement?.lang.startsWith(language)",
                                   arg=language, timeout=120000)
            page.locator('#loading').wait_for(state='hidden', timeout=120000)
            result['language_switch_round_trip_s'].append(time.perf_counter() - start)
            result['language_switches_s'].append(page.evaluate('window.__switchMS')/1000)
            frame = page.locator('#report').element_handle().content_frame()
        result.update(errors=errors, remote_requests=remote,
                      method='One cold file:// navigation; switches measure DOM click to post-paint loading dismissal. Automation round trips are recorded separately; host load is uncontrolled.')
        browser.close()
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = measure(args.report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
