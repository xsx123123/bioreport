"""Report presentation language; analysis keys and evidence stay unchanged."""
from copy import deepcopy
import base64
import gzip
import html
import json
import os
import re
from pathlib import Path
import tempfile


def language(config=None):
    value = (config or {}).get('report', {}).get('language') or os.environ.get('BIOREPORT_LANGUAGE', 'zh')
    return 'en' if str(value).lower().startswith('en') else 'zh'


def is_rna(config):
    from .registry import get_registry
    report = config.get('report', {})
    modules = report.get('modules', report.get('sections', ()))
    if not modules and not report.get('type'):
        return bool(config.get('input_files', {}).get('tpm_file'))
    return report.get('type') == 'rna-seq' or any(get_registry().canonical(m).startswith('rna.') for m in modules)


def languages(config):
    return ['zh', 'en'] if is_rna(config) else [language(config)]


def localized_config(config, lang):
    result = deepcopy(config)
    report = result.setdefault('report', {})
    report['language'] = lang
    title = report.get('title', 'RNA-seq Analysis Report')
    if lang == 'en':
        report['title'] = report.get('title_en') or (translate(title, 'en') if not any('\u4e00' <= c <= '\u9fff' for c in title) else 'RNA-seq Analysis Report')
    return result


_CATALOG = json.loads(Path(__file__).with_name('translations.en.json').read_text(encoding='utf-8'))
_PATTERN = re.compile('|'.join(re.escape(k) for k in sorted(_CATALOG, key=len, reverse=True) if len(k) >= 3 or ('{' in k and len(k) > 1)))


def translate(value, lang=None):
    if not isinstance(value, str) or (lang or language()) != 'en':
        return value
    if value in _CATALOG:
        return _CATALOG[value]
    value = _PATTERN.sub(lambda match: _CATALOG[match.group()], value)
    return value.replace("].", "]. ")

def add_language_switch(path, config, lang, layout='single'):
    """Attach offline-safe navigation between complete language editions."""
    from .config import report_artifact_name
    from bs4 import BeautifulSoup
    path = Path(path)
    paths = [p for p in path.parent.rglob('*.html') if not (lang == 'zh' and p.relative_to(path.parent).parts[0] == 'en')] if layout == 'website' else [path]
    for page in paths:
        soup = BeautifulSoup(page.read_text(encoding='utf-8'), 'html.parser')
        if soup.head is None or soup.body is None:
            continue
        soup.html['lang'] = 'en' if lang == 'en' else 'zh-CN'
        other = 'zh' if lang == 'en' else 'en'
        if layout == 'website':
            relative = page.relative_to(path.parent)
            other_root = path.parent.parent if lang == 'en' else path.parent / 'en'
            target = Path(os.path.relpath(other_root / relative, page.parent)).as_posix()
        else:
            target = report_artifact_name(config, 'html', other)
        button = soup.select_one('[data-report-language]')
        if button is None:
            button = soup.new_tag('button', attrs={'data-report-language':'', 'class':'report-control', 'type':'button'})
            (soup.select_one('.navbar') or soup.body).append(button)
        button.clear()
        icon = soup.new_tag('svg', attrs={
            'class': 'report-language-icon', 'viewBox': '0 0 24 24',
            'aria-hidden': 'true', 'focusable': 'false',
        })
        icon.append(soup.new_tag('circle', attrs={'cx':'12','cy':'12','r':'10'}))
        icon.append(soup.new_tag('path', attrs={'d':'M2 12h20M12 2a15.3 15.3 0 0 1 0 20M12 2a15.3 15.3 0 0 0 0 20'}))
        button.append(icon)
        label = soup.new_tag('span')
        label.string = '中文' if lang == 'en' else 'English'
        button.append(label)
        button['data-language-target'] = target
        button.name = 'a'
        button.attrs.pop('type', None)
        button['href'] = target
        button['hreflang'] = 'zh-CN' if other == 'zh' else 'en'
        button['aria-label'] = 'Switch to Chinese' if lang == 'en' else 'Switch to English'
        button['title'] = button['aria-label']
        script = soup.new_tag('script')
        script.string = 'window.BIOREPORT_LANGUAGE_EDITION = ' + json.dumps(lang) + ';' + "document.addEventListener('click', function(e) { const a = e.target.closest('[data-language-target]'); if (!a || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return; e.preventDefault(); e.stopImmediatePropagation(); location.href = a.href + location.hash; }, true);"
        soup.head.insert(0, script)
        page.write_text(str(soup), encoding='utf-8')


def combine_language_editions(chinese_path, english_path, output_path, title='BioReport'):
    """Pack two rendered editions into one offline HTML with an in-page switch."""
    chinese_path, english_path, output_path = map(Path, (chinese_path, english_path, output_path))
    shell_title = html.escape(title, quote=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open('w', encoding='utf-8', newline='') as output:
        output.write(f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{shell_title}</title><style>
*{{box-sizing:border-box}}html,body{{height:100%;margin:0}}body{{font:14px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif;color:#26364a;background:#f3f7fb}}
iframe{{position:absolute;inset:0;display:block;width:100%;height:100%;border:0;background:#fff}}
iframe[hidden]{{display:block;visibility:hidden;pointer-events:none}}
.loading{{position:absolute;inset:0;z-index:2;display:grid;place-items:center;color:#63748a;background:#fff}}
.loading[hidden]{{display:none}}
</style></head><body><div class="loading" id="loading" role="status">正在载入报告...</div><iframe id="report" title="中文报告"></iframe>
''')
        output.write(r'''<script>
(() => {
  let frame = document.getElementById('report');
  const loading = document.getElementById('loading');
  // Exactly two editions: cache decoding promises and retain each live document.
  // A string-only cache still reparses all charts/tables on every srcdoc assignment.
  const sources = new Map();
  const decoding = new Map();
  const frames = new Map();
  const preparing = new Map();
  let current = '';
  let requested = 'zh';
  let sequence = 0;
  let idleScheduled = false;
  const unsupported = '此浏览器不支持离线报告解压，请使用新版 Chrome、Edge 或 Firefox。 / This browser cannot decompress the offline report. Please use a recent Chrome, Edge or Firefox.';

  function decode(language) {
    if (sources.has(language)) return Promise.resolve(sources.get(language));
    if (decoding.has(language)) return decoding.get(language);
    const pending = (async () => {
      if (typeof DecompressionStream !== 'function') throw new Error(unsupported);
      const data = document.getElementById('edition-' + language).textContent.replace(/\s/g, '');
      const binary = atob(data);
      const compressed = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) compressed[i] = binary.charCodeAt(i);
      const source = await new Response(new Blob([compressed]).stream().pipeThrough(new DecompressionStream('gzip'))).text();
      sources.set(language, source);
      return source;
    })();
    decoding.set(language, pending);
    pending.then(() => decoding.delete(language), () => decoding.delete(language));
    return pending;
  }

  function showError(error) {
    loading.hidden = false;
    loading.textContent = '报告载入失败 / Report could not load: ' + error.message + ' ';
    const retry = document.createElement('button');
    retry.type = 'button';
    retry.textContent = '重试 / Retry';
    retry.onclick = () => openEdition(requested).catch(showError);
    loading.append(retry);
  }

  function prepare(language) {
    if (frames.has(language)) return Promise.resolve(frames.get(language));
    if (preparing.has(language)) return preparing.get(language);
    const pending = (async () => {
      const source = await decode(language);
      const target = current ? document.createElement('iframe') : frame;
      target.title = language === 'en' ? 'English report' : '中文报告';
      if (target !== frame) {
        target.id = 'report-' + language;
        target.hidden = true;
        target.setAttribute('aria-hidden', 'true');
        document.body.append(target);
      }
      try {
        await new Promise((resolve, reject) => {
          target.onload = resolve;
          target.onerror = () => reject(new Error('Report frame failed to load'));
          target.srcdoc = source;
        });
      } catch (error) {
        if (target !== frame) target.remove();
        throw error;
      } finally {
        target.onload = target.onerror = null;
      }
      const button = target.contentDocument.querySelector('[data-report-language]');
      if (button) {
        button.textContent = language === 'zh' ? '中文 / English' : 'English / 中文';
        button.setAttribute('aria-label', language === 'zh' ? '当前语言：中文；切换到 English' : 'Current language: English; switch to 中文');
        button.onclick = event => {
          event?.preventDefault();
          openEdition(language === 'zh' ? 'en' : 'zh').catch(showError);
        };
      }
      frames.set(language, target);
      return target;
    })();
    preparing.set(language, pending);
    pending.then(() => preparing.delete(language), () => preparing.delete(language));
    return pending;
  }

  async function openEdition(language) {
    requested = language;
    if (language === current && loading.hidden) return;
    const ticket = ++sequence;
    const fragment = current ? frame.contentWindow.location.hash : '';
    const theme = current ? frame.contentDocument.documentElement.dataset.reportTheme : null;
    loading.hidden = false;
    loading.textContent = '正在载入报告 / Loading report…';
    const target = await prepare(language);
    if (ticket !== sequence) return;
    if (current && target !== frame) {
      frame.id = 'report-' + current;
      frame.hidden = true;
      frame.setAttribute('aria-hidden', 'true');
    }
    target.id = 'report';
    target.hidden = false;
    target.removeAttribute('aria-hidden');
    if (theme && target.contentDocument.documentElement.dataset.reportTheme !== theme) {
      target.contentDocument.querySelector('button[data-report-theme]')?.click();
    }
    frame = target;
    current = language;
    document.documentElement.lang = language === 'en' ? 'en' : 'zh-CN';
    frame.contentWindow.location.hash = fragment;
    // A restored chapter can trigger chart layout on hashchange. Keep the
    // loading status until that route has had a chance to paint.
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    if (ticket !== sequence) return;
    loading.hidden = true;
    if (!idleScheduled) {
      idleScheduled = true;
      // Decode only, after the first edition has had time to paint.
      setTimeout(() => {
        const predecode = () => decode(language === 'zh' ? 'en' : 'zh').catch(() => {});
        if (typeof requestIdleCallback === 'function') requestIdleCallback(predecode, {timeout:5000});
        else setTimeout(predecode, 0);
      }, 1000);
    }
  }
  document.addEventListener('DOMContentLoaded', () => openEdition('zh').catch(showError), {once:true});
})();
</script>
''')
        for language, source_path in (('zh', chinese_path), ('en', english_path)):
            output.write(f'<script id="edition-{language}" type="application/octet-stream">\n')
            with tempfile.TemporaryFile() as compressed:
                with source_path.open('rb') as source, gzip.GzipFile(fileobj=compressed, mode='wb', mtime=0) as archive:
                    while chunk := source.read(1024 * 1024):
                        archive.write(chunk)
                compressed.seek(0)
                output.flush()
                base64.encode(compressed, output.buffer)
                output.flush()
            output.write('</script>\n')
        output.write('</body></html>\n')


def localize_figure(figure):
    """Translate chart presentation text without touching coordinates or IDs."""
    if figure is None or language() != 'en':
        return figure
    import plotly.graph_objects as go
    result = go.Figure(figure)
    if result.layout.title.text:
        result.layout.title.text = translate(result.layout.title.text)
    for key in result.layout:
        if key.startswith(('xaxis', 'yaxis')):
            axis = result.layout[key]
            if axis.title.text:
                axis.title.text = translate(axis.title.text)
    for annotation in result.layout.annotations or ():
        if annotation.text:
            annotation.text = translate(annotation.text)
    return result
