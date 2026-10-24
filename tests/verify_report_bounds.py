"""Verify real report scroll boundaries on desktop and mobile.

Usage: python tests/verify_report_bounds.py REPORT.html --browser firefox
"""
import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def verify(source, browser_name):
    output = Path(__file__).resolve().parents[1] / 'output/report-bounds-validation'
    output.mkdir(parents=True, exist_ok=True)
    checks = []
    with sync_playwright() as p:
        try:
            browser = getattr(p, browser_name).launch(args=['--no-sandbox'] if browser_name == 'chromium' else [])
            page = browser.new_page(viewport={'width': 1440, 'height': 900})
            page.goto(source.resolve().as_uri(), wait_until='domcontentloaded')
            if page.locator('iframe#report').count():
                frame = page.locator('iframe#report').element_handle().content_frame()
            else:
                frame = page.main_frame
            frame.wait_for_function("document.body.classList.contains('report-routing-ready')", timeout=120000)
            logos = frame.evaluate('''async () => {
              const images = [...document.querySelectorAll('.report-footer img')];
              await Promise.all(images.map(image => image.decode()));
              return images.map(image => ({name:image.alt, local:image.src.startsWith('data:'),
                width:image.naturalWidth, height:image.naturalHeight}));
            }''')
            assert [image['name'] for image in logos] == ['BioReport', 'Quarto'], logos
            assert all(image['width'] > 0 and image['height'] > 0 and image['local'] for image in logos), logos
            for size in ({'width': 1440, 'height': 900}, {'width': 390, 'height': 844}):
                page.set_viewport_size(size)
                count = frame.locator('.report-page').count()
                for index in range(count):
                    result = frame.evaluate('''async index => {
                      document.documentElement.style.scrollBehavior = 'auto';
                      const selected = document.querySelectorAll('.report-page')[index];
                      const hash = '#' + selected.id;
                      // Wait for the router's hashchange handler and its own
                      // layout frame before measuring the scroll boundary.
                      if (location.hash !== hash) await new Promise(resolve => {
                        window.addEventListener('hashchange', () =>
                          requestAnimationFrame(() => requestAnimationFrame(resolve)), {once:true});
                        location.hash = hash;
                      });
                      await document.fonts.ready;
                      await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
                      scrollTo({top:0, behavior:'instant'});
                      const heading = [...selected.querySelectorAll('h1,h2,h3')].find(n=>n.getClientRects().length);
                      const top = heading.getBoundingClientRect().top;
                      const navbar = document.querySelector('.report-navbar').getBoundingClientRect();
                      scrollTo({top:document.documentElement.scrollHeight, behavior:'instant'});
                      await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
                      const footer = document.querySelector('.report-footer').getBoundingClientRect();
                      return {page:selected.id, width:innerWidth, height:innerHeight,
                        headingTop:top, navbarBottom:navbar.bottom, footerBottom:footer.bottom,
                        footerHeight:footer.height, scrollY, scrollHeight:document.documentElement.scrollHeight,
                        overscroll:getComputedStyle(document.documentElement).overscrollBehaviorY};
                    }''', index)
                    assert result['headingTop'] >= result['navbarBottom'] - 1, result
                    if size['width'] >= 1280:
                        assert result['headingTop'] - result['navbarBottom'] <= 32, result
                    assert abs(result['footerBottom'] - result['height']) <= 2, result
                    assert result['overscroll'] == 'none', result
                    checks.append(result)
                    print('PASS', result['page'], size, 'footer gap:', round(result['height'] - result['footerBottom'], 2), flush=True)
            if page.locator('iframe#report').count():
                assert page.evaluate('document.documentElement.scrollHeight === innerHeight')
            (output / 'verification.json').write_text(json.dumps({'source': str(source), 'browser': browser_name,
                                                                 'logos': logos, 'checks': checks}, ensure_ascii=False, indent=2))
            print('PASS: report top and footer boundaries', flush=True)
            browser.close()
        except BaseException:
            import traceback
            traceback.print_exc()
            raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('--browser', default='chromium', choices=['chromium', 'firefox'])
    args = parser.parse_args()
    verify(args.source, args.browser)
