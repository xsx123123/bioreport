"""Finalize the shared Quarto website and offline launch instructions."""
from pathlib import Path
import html
import shutil


def finalize_website(directory: Path, config: dict):
    from bs4 import BeautifulSoup
    from .i18n import languages
    for lang in languages(config):
        for page in (directory / 'qmd').glob(f'site-{lang}-*.html'):
            soup = BeautifulSoup(page.read_text(encoding='utf-8'), 'html.parser')
            # Quarto injects AMD shims for any HTML cell, even when our output
            # uses ordinary scripts and locally bundled ES modules exclusively.
            for script in list(soup.select('script')):
                source = script.get('src', '')
                if source.startswith('https://cdn.jsdelivr.net/npm/') and any(
                    name in source for name in ('jquery@', 'requirejs@')
                ):
                    script.decompose()
                elif (script.string or '').strip() == "define('jquery', [],function() {return window.jQuery;})":
                    script.decompose()
            other = 'en' if lang == 'zh' else 'zh'
            button = soup.select_one('[data-report-language]')
            if button:
                button.name = 'a'
                button.attrs.pop('type', None)
                button['href'] = page.name.replace(f'site-{lang}-', f'site-{other}-')
                button['data-language-target'] = button['href']
                button['aria-label'] = f'Current language: {lang}; switch to {other}'
                button['title'] = button['aria-label']
                button.string = '中文 / English'
            for link in soup.select('.report-navbar a.nav-link'):
                if link.get('href') == page.name:
                    link['aria-current'] = 'page'
            script = soup.new_tag('script')
            script.string = 'window.BIOREPORT_LANGUAGE_EDITION = ' + repr(lang) + ';document.documentElement.dataset.reportLanguage=' + repr(lang) + ';'
            soup.head.insert(0, script)
            page.write_text(str(soup), encoding='utf-8')
    title = html.escape(config.get('report', {}).get('title', 'BioReport'))
    entry = f'<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>{title}</title><body><h1>{title}</h1><p><a href="qmd/site-zh-index.html" lang="zh-CN">中文</a> · <a href="qmd/site-en-index.html" lang="en">English</a></p></body></html>'
    (directory / 'index.html').write_text(entry, encoding='utf-8')
    (directory / 'en').mkdir(exist_ok=True)
    (directory / 'en/index.html').write_text('<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=../qmd/site-en-index.html"><a href="../qmd/site-en-index.html">English</a>', encoding='utf-8')
    shutil.copyfile(Path(__file__).with_name('serve_report.py'), directory / 'serve-report.py')
    (directory / 'START-REPORT.txt').write_text('''Requires Python 3.10+ on Windows, macOS or Linux.
Run: python serve-report.py
Windows: py -3 serve-report.py
Open the printed loopback URL. Stop with Ctrl+C.
All report resources are local; internet access is unnecessary.
Use HTTP; file:// does not support Quarto ES modules reliably.
''', encoding='utf-8')
