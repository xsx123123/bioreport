"""Audit real bilingual single-file reports without network access.

Usage: python scripts/verify_report_theme.py report.html --output output/theme-audit
"""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright


def audit(source, output, axe=None, desktop_only=False, pages=None):
    output.mkdir(parents=True, exist_ok=True)
    results = []
    errors = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=['--no-sandbox'])
        context = browser.new_context()
        remote = []
        context.route('http://**/*', lambda route: (remote.append(route.request.url), route.abort()))
        context.route('https://**/*', lambda route: (remote.append(route.request.url), route.abort()))
        page = context.new_page()
        print('Opening report', flush=True)
        page.on('pageerror', lambda error: errors.append(error.stack or str(error)))
        page.goto(source.resolve().as_uri(), wait_until='load', timeout=120000)
        page.wait_for_function("document.querySelector('#report')?.contentDocument?.querySelector('.report-navbar')", timeout=120000)
        page.locator('#loading').wait_for(state='hidden', timeout=120000)
        print('Report loaded', flush=True)
        for language in ['zh', 'en']:
            if language == 'en':
                page.frame_locator('#report').locator('[data-report-language]').click()
                page.wait_for_function("document.querySelector('#report')?.contentDocument?.documentElement?.lang === 'en'", timeout=120000)
                page.locator('#loading').wait_for(state='hidden', timeout=120000)
            report = page.locator('#report').element_handle().content_frame()
            report.wait_for_function("document.querySelector('table.dataTable') && window.Plotly", timeout=60000)
            print('Language: '+language, flush=True)
            for width, height in ([(1440,900)] if desktop_only else [(1440,900),(1920,1080),(768,1024),(390,844)]):
                page.set_viewport_size({'width':width,'height':height})
                page.wait_for_timeout(350)
                links = report.locator('.report-navbar a.nav-link')
                for index in range(links.count()):
                    if pages and index + 1 not in pages:
                        continue
                    # Navigation is collapsed on narrow screens.
                    if not links.nth(index).is_visible():
                        report.locator('.report-nav-toggle').click()
                    print(f'Checking {language} {width} page {index+1}', flush=True)
                    links.nth(index).click()
                    page.wait_for_timeout(350)
                    active = report.locator('.report-page[data-active="true"]')
                    assert active.count() == 1
                    dimensions = report.evaluate('''() => ({innerWidth:innerWidth, width:document.documentElement.scrollWidth,
                        body:document.querySelector('main').getBoundingClientRect().width})''')
                    item = dict(language=language, viewport=[width,height], page=index+1, **dimensions)
                    if dimensions['width'] > dimensions['innerWidth'] + 2:
                        errors.append(f'Page overflow: {item}')
                    charts = active.locator('.plotly-graph-div').evaluate_all('''nodes=>nodes.map(node=>{
                        const scroll=node.closest('.report-chart-scroll');
                        const rect=scroll?.getBoundingClientRect();
                        return {ready:!!node._fullLayout && node._fullData.length>0,width:node.getBoundingClientRect().width,
                            size:node._fullLayout?._size,
                            scroll:scroll?{left:rect.left,right:rect.right,viewport:scroll.clientWidth,canvas:scroll.scrollWidth}:null};
                    })''')
                    assert all(chart['ready'] for chart in charts)
                    for chart in charts:
                        if chart['width'] > dimensions['innerWidth'] + 2:
                            scroll=chart['scroll']
                            assert scroll and scroll['left'] >= -2 and scroll['right'] <= dimensions['innerWidth']+2
                            assert scroll['canvas'] > scroll['viewport'] and scroll['canvas'] >= chart['width']-2
                        if chart['width'] > 0:
                            assert chart['size']['w'] > 20 and chart['size']['h'] > 20, chart
                    item['charts'] = len(charts)
                    diagrams = active.locator('.report-mermaid-svg').evaluate_all('''nodes=>nodes.map(node=>{
                        const selection=window.getSelection();selection.selectAllChildren(node);
                        const selected=selection.toString();selection.removeAllRanges();
                        return {width:node.viewBox.baseVal.width,height:node.viewBox.baseVal.height,
                            labels:node.querySelectorAll('.nodeLabel').length,selection:selected.length};
                    })''')
                    assert all(diagram['width']>0 and diagram['height']>0 and diagram['labels']>0 and diagram['selection']>0 for diagram in diagrams)
                    item['static_diagrams'] = diagrams
                    if active.locator('.mission-grid').count():
                        assert active.locator('.mission-card').count() == 2
                        assert active.locator('.feature-card').count() == 4
                        assert active.locator('.tech-role').count() == 6
                        assert active.locator('.roadmap-card').count() == 3
                        if language == 'en':
                            assert not __import__('re').search('[\u4e00-\u9fff]', active.inner_text())
                        page.screenshot(path=str(output/f'{language}-{width}-about.png'), full_page=True)
                        active.screenshot(path=str(output/f'{language}-{width}-about-content.png'))
                    if active.locator('.dt-container, .dataTables_wrapper').count():
                        table = active.locator('table.dataTable').first
                        wrapper = active.locator('.dt-container, .dataTables_wrapper').first
                        search = wrapper.locator('input[type="search"]').first
                        assert search.count() == 1
                        search.fill('__no_matching_bioreport_record__')
                        page.wait_for_timeout(350)
                        assert wrapper.locator('td.dt-empty, td.dataTables_empty').count() > 0
                        search.fill('')
                        page.wait_for_timeout(350)
                        # scrollX creates a separate visible header table.
                        header = wrapper.locator('.dt-scroll-head th, .dataTables_scrollHead th').first
                        if not header.count(): header = table.locator('thead th').first
                        header.click()
                        page.wait_for_timeout(150)
                        next_page = wrapper.locator('button.next:not(.disabled), a.next:not(.disabled)').first
                        if next_page.count():
                            next_page.click();page.wait_for_timeout(150)
                            wrapper.locator('button.first:not(.disabled), a.first:not(.disabled)').first.click()
                        item['table'] = {'search': True, 'sort': True, 'pagination': True,
                                         'info': wrapper.locator('.dt-info, .dataTables_info').inner_text()}
                        if width == 1440:
                            wrapper.screenshot(path=str(output/f'{language}-{width}-page-{index+1}-table.png'))
                        item['scroll'] = active.locator('.dt-scroll-body, .dataTables_scrollBody').evaluate_all('(nodes)=>nodes.map(n=>({client:n.clientWidth,scroll:n.scrollWidth}))')
                    if axe and width == 1440:
                        report.add_script_tag(path=str(axe))
                        item['accessibility'] = report.evaluate('''async () => {
                            const result = await axe.run(document.body,
                                {runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}});
                            return result.violations.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))}));
                        }''')
                    results.append(item)
                    (output/'theme-audit-progress.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
                # Save results-page comparison at every requested viewport.
                link = links.filter(has_text='Results' if language == 'en' else '分析结果').first
                if link.count():
                    if not link.is_visible(): report.locator('.report-nav-toggle').click()
                    link.click();page.wait_for_timeout(300)
                    page.screenshot(path=str(output/f'{language}-{width}-results.png'), full_page=True)
        browser.close()
    violations = sum(len(item.get('accessibility', [])) for item in results)
    result = dict(status='FAIL' if errors or remote or violations else 'PASS', errors=errors, remote_requests=remote, accessibility_violations=violations, results=results)
    (output/'theme-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('html', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--axe', type=Path)
    parser.add_argument('--pages', help='Comma-separated page numbers for a scoped development check')
    parser.add_argument('--desktop-only', action='store_true', help='Limit this run to 1440×900; useful for a separate accessibility audit')
    args = parser.parse_args()
    try:
        result = audit(args.html,args.output,args.axe,args.desktop_only,{int(page) for page in args.pages.split(',')} if args.pages else None)
    except Exception as error:
        args.output.mkdir(parents=True,exist_ok=True)
        result = {'status':'FAIL','errors':[f'{type(error).__name__}: {error}']}
        (args.output/'theme-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k != 'results'},ensure_ascii=False))
    raise SystemExit(result['status'] != 'PASS')
