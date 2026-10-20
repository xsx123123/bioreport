"""Verify a rendered bilingual report and capture the requested UI matrix.

python scripts/verify_report_ui.py report.html --before old-report.html --output output/ui-review
"""
import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def verify(source, output, before=None):
    output.mkdir(parents=True, exist_ok=True)
    results = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=['--no-sandbox'])
        for version, path in [('before', before), ('after', source)]:
            if path is None:
                continue
            context = browser.new_context(color_scheme='dark')
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(path.resolve().as_uri(), wait_until='load', timeout=120000)
            page.wait_for_function("document.querySelector('#report')?.contentDocument?.querySelector('.report-navbar')", timeout=120000)
            page.locator('#loading').wait_for(state='hidden', timeout=120000)
            frame = page.locator('#report').element_handle().content_frame()
            if version == 'after':
                assert frame.evaluate("document.documentElement.dataset.reportTheme") == 'dark'
            for lang in ['zh', 'en']:
                if lang == 'en':
                    selector = '[data-report-language] [data-language="en"]' if version == 'after' else '[data-report-language]'
                    frame.locator(selector).click()
                    page.wait_for_function("document.querySelector('#report')?.contentDocument?.documentElement.lang === 'en'", timeout=120000)
                    page.locator('#loading').wait_for(state='hidden', timeout=120000)
                    frame = page.locator('#report').element_handle().content_frame()
                for width in [1366, 2560]:
                    page.set_viewport_size({'width': width, 'height': 900})
                    for theme in ['light', 'dark']:
                        if frame.evaluate('document.documentElement.dataset.reportTheme') != theme:
                            frame.locator('button[data-report-theme]').click()
                        if version == 'after':
                            assert frame.locator(f'[data-language="{lang}"]').get_attribute('aria-pressed') == 'true'
                            expected = ('Switch to dark mode' if theme == 'light' else 'Switch to light mode') if lang == 'en' else ('切换到深色模式' if theme == 'light' else '切换到浅色模式')
                            assert frame.locator('button[data-report-theme]').get_attribute('title') == expected
                        links = frame.locator('.report-navbar a.nav-link')
                        for index in range(links.count()):
                            links.nth(index).click()
                            page.wait_for_timeout(250)
                            active = frame.locator('.report-page[data-active="true"]')
                            assert active.count() == 1
                            item = dict(version=version, language=lang, width=width, theme=theme, page=index+1)
                            item['overflow'] = frame.evaluate('document.documentElement.scrollWidth > innerWidth + 2')
                            if version == 'after':
                                assert not item['overflow'], item
                                assert active.locator('h2').all_text_contents().count('RNA-seq Result') == 0
                                assert frame.locator('#toc-title').inner_text() == ('Contents' if lang == 'en' else '本页目录')
                                for selector in ['.report-language-control', '.report-theme-control']:
                                    assert round(frame.locator(selector).bounding_box()['height']) == 36
                                assert frame.locator('.report-menu a.nav-link').count() == links.count()
                            for region in active.locator('.report-data-table').all():
                                if not region.is_visible():
                                    continue
                                region.scroll_into_view_if_needed()
                                region.locator('table[data-ready="true"]').wait_for(timeout=60000)
                                if version == 'after':
                                    for button in region.locator('button.dt-button').all():
                                        assert round(button.bounding_box()['height']) == 32
                                        assert button.locator('svg').count() == 1
                                    gap = region.evaluate('n=>{const controls=n.querySelector(".dt-container > .d-flex");const table=n.querySelector(".dt-scroll");return controls && table ? table.getBoundingClientRect().top-controls.getBoundingClientRect().bottom : null;}')
                                    assert gap is None or gap <= 16, gap
                            for scroll in active.locator('.dt-scroll-body').all():
                                scroll.scroll_into_view_if_needed()
                                page.wait_for_timeout(100)
                                if version == 'after':
                                    scroll.evaluate('(n)=>{n.scrollLeft=0;n.dispatchEvent(new Event("scroll"));}')
                                    more = scroll.evaluate('n=>n.scrollWidth>n.clientWidth+2')
                                    assert scroll.evaluate('n=>n.parentElement.classList.contains("report-scroll-more")') == more
                                    scroll.evaluate('(n)=>{n.scrollLeft=n.scrollWidth;n.dispatchEvent(new Event("scroll"));}')
                                    assert not scroll.evaluate('n=>n.parentElement.classList.contains("report-scroll-more")')
                            frame.evaluate('window.scrollTo(0,0)')
                            page.wait_for_timeout(250)
                            page.screenshot(path=str(output / f'{version}-{lang}-{theme}-{width}-page{index+1}.png'))
                            results.append(item)
            assert not errors, errors
            context.close()
        browser.close()
    (output / 'matrix.json').write_text(json.dumps(results, indent=2), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--before', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    verify(args.source, args.output, args.before)
