/* BioReport offline chart downloads. Local pdfmake runtime; no server or network required. */
(() => {
  'use strict';
  if (window.BioReportPlotlyExport) return;
  const settings = new WeakMap();
  const fontData = new Map();
  const messages = {
    zh: {
      open: '下载图表', title: '下载图表', format: '文件格式', width: '宽度（px）',
      height: '高度（px）', lock: '锁定宽高比', reset: '恢复默认', cancel: '取消',
      download: '下载', busy: '正在导出…',
      hint: '宽高为图表布局尺寸（96 px/英寸）。PNG 按 1000 DPI 高清渲染，输出宽高约为输入的 10.42 倍。SVG、PDF 保留矢量线条和文字。',
      output: '实际输出',
      invalid: '宽度和高度须为 100–16000 之间的整数。',
      pngLarge: '1000 DPI PNG 输出单边最多 16000 像素、总计最多 1.28 亿像素，请减小宽高或选择 SVG。',
      failed: '导出失败，请重试或减小尺寸。',
      tipPalette: '切换分组配色方案', tipScale: '切换连续色带',
    },
    en: {
      open: 'Download chart', title: 'Download chart', format: 'File format',
      width: 'Width (px)', height: 'Height (px)', lock: 'Lock aspect ratio',
      reset: 'Reset', cancel: 'Cancel', download: 'Download', busy: 'Exporting…',
      hint: 'Width and height set the chart layout (96 px/inch). PNG renders at 1000 DPI, with output dimensions about 10.42 times the input. SVG and PDF retain vector lines and text.',
      output: 'Output size',
      invalid: 'Width and height must be integers between 100 and 16000.',
      pngLarge: '1000 DPI PNG supports up to 16000 pixels per side and 128 million pixels total. Reduce the dimensions or choose SVG.',
      failed: 'Export failed. Please retry or reduce the dimensions.',
      tipPalette: 'Switch group color palette', tipScale: 'Switch color scale',
    },
  };
  // PNG resolution is not a user choice: every download carries 1000 DPI metadata.
  const PNG_DPI = 1000;
  const CSS_DPI = 96;
  let dialog, active, returnFocus;

  // Theme the Plotly color-switch dropdowns like the rest of the report and
  // give them a gentle hover/open animation plus a native tooltip. Plotly
  // draws the chips as inline-styled SVG, so overrides need !important.
  // Guarded: tests also load this file in a bare VM without a DOM.
  if (typeof document !== 'undefined') {
    const menuStyle = document.createElement('style');
    menuStyle.textContent = `
      .js-plotly-plot .updatemenu-header .updatemenu-item-rect {rx:6px;ry:6px;
        transition:fill .15s ease,stroke .15s ease;}
      .js-plotly-plot .updatemenu-header:hover .updatemenu-item-rect {
        fill:var(--br-surface-hover,#eef2f7) !important;
        stroke:var(--br-primary,#2563eb) !important;}
      .js-plotly-plot .updatemenu-dropdown-button {cursor:pointer;}
      .js-plotly-plot .updatemenu-dropdown-button .updatemenu-item-rect {transition:fill .12s ease;}
      .js-plotly-plot .updatemenu-dropdown-button:hover .updatemenu-item-rect {
        fill:var(--br-surface-hover,#eef2f7) !important;}
      .js-plotly-plot .updatemenu-dropdown-button {animation:bioreport-menu-in .16s ease-out;}
      @keyframes bioreport-menu-in {from {opacity:0;transform:translateY(-3px);} to {opacity:1;transform:none;}}
      @media print {.js-plotly-plot .updatemenu-container {display:none;}}
    `;
    document.head.append(menuStyle);
    document.addEventListener('mouseover', event => {
      const header = event.target.closest?.('.updatemenu-header');
      if (!header || header.dataset.reportTip) return;
      header.dataset.reportTip = 'true';
      const zh = (document.documentElement.lang || '').toLowerCase().startsWith('zh');
      const text = messages[zh ? 'zh' : 'en'];
      const label = header.textContent || '';
      const tip = document.createElementNS('http://www.w3.org/2000/svg', 'title');
      tip.textContent = label.startsWith('Scale:') ? text.tipScale : text.tipPalette;
      header.prepend(tip);
    });
  }

  function createDialog() {
    const style = document.createElement('style');
    style.textContent = `
      .report-export-dialog {box-sizing:border-box;width:min(440px,calc(100vw - 32px));
        max-height:calc(100dvh - 32px);overflow:auto;margin:auto;padding:24px;
        border:1px solid var(--br-border,#e2e8f0);border-radius:12px;
        background:var(--br-surface,#fff);color:var(--br-text,#334155);
        box-shadow:0 20px 60px #0003;font:14px/1.5 var(--bs-body-font-family,sans-serif);}
      .report-export-dialog::backdrop {background:#0f172a66;}
      .report-export-dialog h2 {margin:0 0 18px;font-size:19px;color:inherit;}
      .report-export-dialog label {display:block;margin-bottom:14px;}
      .report-export-dialog select,.report-export-dialog input[type=number] {
        display:block;box-sizing:border-box;width:100%;min-height:40px;margin-top:5px;
        padding:7px 10px;border:1px solid var(--br-border,#cbd5e1);border-radius:6px;
        background:var(--br-surface,#fff);color:inherit;font:inherit;}
      .report-export-size {display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:14px;}
      .report-export-dialog .report-export-lock {display:flex;align-items:center;gap:8px;}
      .report-export-lock input {margin:0;}
      .report-export-dialog p {margin:0 0 16px;font-size:13px;color:var(--br-muted,#52657d);}
      .report-export-dialog .report-export-status {color:#b91c1c;min-height:1.5em;}
      .report-export-actions {display:flex;flex-wrap:wrap;justify-content:flex-end;gap:8px;}
      .report-export-actions button {min-height:38px;padding:7px 14px;cursor:pointer;
        border:1px solid var(--br-border,#cbd5e1);border-radius:6px;font:inherit;
        background:var(--br-surface,#fff);color:inherit;}
      .report-export-actions button[type=submit] {background:#2563eb;color:#fff;border-color:#2563eb;}
      .report-export-dialog :focus-visible {outline:2px solid var(--br-primary,#2563eb);outline-offset:3px;}
      .report-export-dialog button:disabled {opacity:.6;cursor:wait;}
      @media print {.report-export-dialog {display:none;}}
    `;
    document.head.append(style);
    dialog = document.createElement('dialog');
    dialog.className = 'report-export-dialog';
    dialog.setAttribute('aria-labelledby', 'report-export-title');
    dialog.innerHTML = `<form novalidate>
      <h2 id="report-export-title"></h2>
      <label><span data-label="format"></span><select name="format" autofocus>
        <option value="png">PNG</option><option value="svg">SVG</option><option value="pdf">PDF</option>
      </select></label>
      <div class="report-export-size">
        <label><span data-label="width"></span><input name="width" type="number" min="100" max="16000" step="1" required></label>
        <label><span data-label="height"></span><input name="height" type="number" min="100" max="16000" step="1" required></label>
      </div>
      <label class="report-export-lock"><input name="lock" type="checkbox"><span data-label="lock"></span></label>
      <p data-label="hint"></p><p class="report-export-output" aria-live="polite"></p>
      <p class="report-export-status" role="status" aria-live="polite"></p>
      <div class="report-export-actions">
        <button type="button" data-label="reset"></button>
        <button type="button" data-label="cancel"></button>
        <button type="submit" data-label="download"></button>
      </div>
    </form>`;
    document.body.append(dialog);
    dialog.querySelector('[data-label=cancel]').onclick = () => dialog.close();
    dialog.querySelector('[data-label=reset]').onclick = () => fill(active.defaults);
    dialog.addEventListener('cancel', event => { if (active.busy) event.preventDefault(); });
    dialog.addEventListener('close', () => { if (returnFocus?.isConnected) returnFocus.focus(); });
    for (const dimension of ['width', 'height']) {
      dialog.querySelector(`[name=${dimension}]`).addEventListener('input', () => {
        const form = dialog.querySelector('form');
        const other = dimension === 'width' ? 'height' : 'width';
        const value = Number(form.elements[dimension].value);
        if (form.elements.lock.checked && value > 0) {
          form.elements[other].value = Math.round(dimension === 'width' ? value / active.ratio : value * active.ratio);
        }
        updateOutput();
      });
    }
    dialog.querySelector('[name=lock]').addEventListener('change', () => {
      const fields = dialog.querySelector('form').elements;
      if (Number(fields.width.value) > 0 && Number(fields.height.value) > 0)
        active.ratio = Number(fields.width.value) / Number(fields.height.value);
    });
    dialog.querySelector('[name=format]').addEventListener('change', updateOutput);
    dialog.querySelector('form').addEventListener('submit', exportChart);
  }

  function outputSize(format, width, height) {
    const scale = format === 'png' ? PNG_DPI / CSS_DPI : 1;
    return {width: Math.round(width * scale), height: Math.round(height * scale)};
  }

  function updateOutput() {
    const fields = dialog.querySelector('form').elements;
    const size = outputSize(fields.format.value, Number(fields.width.value), Number(fields.height.value));
    const text = messages[active.language] || messages.en;
    dialog.querySelector('.report-export-output').textContent =
      `${text.output}: ${size.width} × ${size.height} px${fields.format.value === 'png' ? ' · 1000 DPI' : ''}`;
  }

  function fill(value) {
    const fields = dialog.querySelector('form').elements;
    for (const name of ['format', 'width', 'height']) fields[name].value = value[name];
    fields.lock.checked = value.lock;
    active.ratio = value.width / value.height;
    dialog.querySelector('.report-export-status').textContent = '';
    updateOutput();
  }

  function open(chart, button) {
    if (!dialog) createDialog();
    if (dialog.open) return;
    active = settings.get(chart);
    active.chart = chart;
    returnFocus = button;
    const text = messages[active.language] || messages.en;
    dialog.querySelector('#report-export-title').textContent = text.title;
    for (const node of dialog.querySelectorAll('[data-label]')) node.textContent = text[node.dataset.label];
    fill(active.value);
    dialog.showModal();
  }

  // Use Plotly's actual button name rather than matching an English tooltip.
  // Rebind after relayout: responsive charts can recreate their modebar.
  function attach(chart, options) {
    if (settings.has(chart)) return;
    const defaults = {format: 'png', width: Math.round(options.width), height: Math.round(options.height), lock: true};
    settings.set(chart, {...options, defaults, value: {...defaults}, busy: false});
    const decorate = () => {
      const modebar = chart._fullLayout?._modeBar;
      const index = modebar?.buttonsNames.indexOf('toImage');
      const button = index >= 0 && modebar.buttonElements[index];
      if (!button || button.dataset.reportExport) return;
      const label = (messages[options.language] || messages.en).open;
      button.dataset.reportExport = 'true';
      button.setAttribute('data-title', label);
      button.setAttribute('aria-label', label);
      button.setAttribute('aria-haspopup', 'dialog');
      button.addEventListener('click', event => {
        event.preventDefault();
        event.stopImmediatePropagation();
        open(chart, button);
      }, true);
    };
    chart.on('plotly_afterplot', decorate);
    decorate();
  }

  async function exportChart(event) {
    event.preventDefault();
    if (active.busy) return;
    const state = active;
    const text = messages[state.language] || messages.en;
    const fields = dialog.querySelector('form').elements;
    const status = dialog.querySelector('.report-export-status');
    const width = Number(fields.width.value), height = Number(fields.height.value);
    const format = fields.format.value;
    const output = outputSize(format, width, height);
    if (![width, height].every(value => Number.isInteger(value) && value >= 100 && value <= 16000)) {
      status.textContent = text.invalid;
      return;
    }
    if (format === 'png' && (output.width > 16000 || output.height > 16000 || output.width * output.height > 128000000)) {
      status.textContent = text.pngLarge;
      return;
    }
    state.value = {format, width, height, lock: fields.lock.checked};
    state.busy = true;
    const controls = [...dialog.querySelectorAll('button,input,select')];
    controls.forEach(node => { node.disabled = true; });
    dialog.setAttribute('aria-busy', 'true');
    const submit = dialog.querySelector('[type=submit]');
    submit.textContent = text.busy;
    status.textContent = '';
    let canvas;
    try {
      await document.fonts.ready;
      const url = await Plotly.toImage(exportSnapshot(state.chart), {format: 'svg', width, height, scale: 1});
      const svg = await portableSvg(url);
      let blob;
      if (format === 'svg') blob = new Blob([svg], {type: 'image/svg+xml;charset=utf-8'});
      else if (format === 'pdf') blob = await vectorPdf(svg, width, height,
        state.pdfFonts || window.BioReportPlotlyFonts?.[state.pdfFontsKey]);
      else {
        // Rasterize the vector at the target resolution, keeping the original
        // layout and relative font sizes rather than enlarging a low-res PNG.
        canvas = await rasterize(svg, output.width, output.height, false);
        blob = await withDpi(await new Promise((resolve, reject) => canvas.toBlob(
          value => value ? resolve(value) : reject(new Error('PNG encoding failed')), 'image/png')), PNG_DPI);
      }
      download(blob, state.filename + '.' + format);
      dialog.close();
    } catch (error) {
      console.error('BioReport chart export failed', error);
      status.textContent = text.failed;
    } finally {
      if (canvas) { canvas.width = 0; canvas.height = 0; }
      state.busy = false;
      controls.forEach(node => { node.disabled = false; });
      dialog.removeAttribute('aria-busy');
      submit.textContent = text.download;
    }
  }

  function exportSnapshot(chart) {
    const data = structuredClone(chart.data);
    const layout = structuredClone(chart.layout);
    // GWAS uses scattergl for interaction. Its default SVG export contains a
    // screen-resolution bitmap; convert only the export copy to vector points.
    // Keep every currently displayed point, including typed-array coordinates.
    for (const trace of data) if (trace.type === 'scattergl') trace.type = 'scatter';
    layout.updatemenus = [];
    return {data, layout, config: {...chart._context}};
  }

  async function portableSvg(url) {
    const source = await (await fetch(url)).text();
    const svg = new DOMParser().parseFromString(source, 'image/svg+xml').documentElement;
    // Single-file reports already contain subset fonts as data URLs. Embed
    // those faces in the image too, so downloads do not require installed fonts.
    const faces = [];
    const usedFamilies = new Set([...svg.querySelectorAll('*'), svg].flatMap(node =>
      (node.style?.fontFamily || node.getAttribute('font-family') || '').split(',')
    ).map(family => family.trim().replace(/["']/g, '').toLowerCase()));
    for (const sheet of document.styleSheets) {
      let rules;
      try { rules = sheet.cssRules; } catch (_) { continue; }
      for (const rule of rules) {
        if (rule.type !== CSSRule.FONT_FACE_RULE) continue;
        const family = rule.style.getPropertyValue('font-family').replace(/["']/g, '').trim().toLowerCase();
        if (!usedFamilies.has(family)) continue;
        let face = rule.cssText;
        const urls = [...face.matchAll(/url\(["']?([^"')]+)["']?\)/g)];
        let available = true;
        for (const match of urls) {
          if (match[1].startsWith('data:')) continue;
          const fontUrl = new URL(match[1], sheet.href || document.baseURI);
          // Avoid any remote font request in an offline HTML report.
          if (fontUrl.origin !== location.origin || !/^https?:$/.test(fontUrl.protocol)) { available = false; break; }
          let data = fontData.get(fontUrl.href);
          if (!data) {
            const response = await fetch(fontUrl);
            if (!response.ok) throw new Error('Font download failed');
            const blob = await response.blob();
            data = await new Promise((resolve, reject) => {
              const reader = new FileReader();
              reader.onload = () => resolve(reader.result);
              reader.onerror = reject;
              reader.readAsDataURL(blob);
            });
            fontData.set(fontUrl.href, data);
          }
          face = face.replace(match[0], `url("${data}")`);
        }
        if (available) faces.push(face);
      }
    }
    if (faces.length) {
      const style = document.createElementNS('http://www.w3.org/2000/svg', 'style');
      style.textContent = faces.join('\n');
      svg.prepend(style);
    }
    return new XMLSerializer().serializeToString(svg);
  }

  async function rasterize(svg, width, height, white) {
    const url = URL.createObjectURL(new Blob([svg], {type: 'image/svg+xml;charset=utf-8'}));
    try {
      const image = new Image();
      image.src = url;
      await image.decode();
      const canvas = document.createElement('canvas');
      canvas.width = width; canvas.height = height;
      const context = canvas.getContext('2d', {willReadFrequently: white});
      if (white) { context.fillStyle = '#fff'; context.fillRect(0, 0, width, height); }
      context.drawImage(image, 0, 0, width, height);
      return canvas;
    } finally { URL.revokeObjectURL(url); }
  }

  // TrueType subsets are prepared with fontTools during report generation.
  // Keep text searchable and preserve the actual glyph outlines offline.
  async function vectorPdf(source, width, height, embeddedFonts) {
    const svg = new DOMParser().parseFromString(source, 'image/svg+xml').documentElement;
    const fonts = {Helvetica: {normal: 'Helvetica', bold: 'Helvetica-Bold',
      italics: 'Helvetica-Oblique', bolditalics: 'Helvetica-BoldOblique'}};
    const vfs = {}, families = new Map();
    for (const [family, variants] of Object.entries(embeddedFonts || {})) {
      families.set(family.toLowerCase(), family);
      fonts[family] = {};
      for (const [variant, data] of Object.entries(variants)) {
        const file = `report-font-${Object.keys(vfs).length}.ttf`;
        vfs[file] = data;
        fonts[family][variant] = file;
      }
    }
    for (const style of svg.querySelectorAll('style')) {
      style.textContent = style.textContent.replace(/@font-face\s*\{[^}]+\}/g, '');
    }
    for (const family of families.values()) {
      const variants = fonts[family];
      const normal = variants.normal || Object.values(variants)[0];
      for (const variant of ['normal', 'bold', 'italics', 'bolditalics']) variants[variant] ||= normal;
    }
    // SVG-to-PDFKit picks one font for each text element rather than doing
    // browser glyph fallback. Explicitly select the report's CJK face for Han.
    for (const node of svg.querySelectorAll('text,tspan')) {
      let stack = '';
      for (let parent = node; parent && !stack; parent = parent.parentElement)
        stack = parent.style?.fontFamily || parent.getAttribute('font-family') || '';
      const candidates = stack.split(',').map(name => families.get(name.trim().replace(/["']/g, '').toLowerCase())).filter(Boolean);
      const cjk = /[\u2e80-\u9fff\uf900-\ufaff\uff00-\uffef]/u.test(node.textContent);
      const family = (cjk && [...candidates, ...families.values()].find(name => /(?:-CN|CJK|HarmonyOS)/i.test(name))) ||
        candidates[0] || families.values().next().value;
      if (cjk && !family) throw new Error('An embedded CJK font is required for Chinese PDF text');
      node.style.fontFamily = family || 'Helvetica';
    }
    return encodeSvgPdf(new XMLSerializer().serializeToString(svg), width, height, fonts, vfs);
  }

  function encodeSvgPdf(svg, width, height, fonts, vfs) {
    const pageWidth = width * .75, pageHeight = height * .75;
    return new Promise((resolve, reject) => {
      // Synchronous getStream uses only supplied local fonts and propagates
      // conversion errors to the dialog instead of leaving it stuck exporting.
      const stream = window.BioReportPdfMake.createPdf({
        pageSize: {width: pageWidth, height: pageHeight}, pageMargins: 0,
        defaultStyle: {font: Object.keys(fonts)[0]},
        content: [{svg, width: pageWidth, height: pageHeight, absolutePosition: {x: 0, y: 0}}],
      }, {}, fonts, vfs).getStream();
      const chunks = [];
      stream.on('data', chunk => chunks.push(chunk));
      stream.on('error', reject);
      stream.on('end', () => resolve(new Blob(chunks, {type: 'application/pdf'})));
      stream.end();
    });
  }

  // PNG pHYs chunk: pixels-per-metre metadata so publishing tools render the
  // image at the fixed 1000 DPI physical resolution. Inserted right after IHDR.
  let crcTable;
  function crc32(bytes) {
    if (!crcTable) {
      crcTable = new Uint32Array(256);
      for (let n = 0; n < 256; n++) {
        let c = n;
        for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
        crcTable[n] = c;
      }
    }
    let crc = 0xffffffff;
    for (const byte of bytes) crc = crcTable[(crc ^ byte) & 0xff] ^ (crc >>> 8);
    return (crc ^ 0xffffffff) >>> 0;
  }

  async function withDpi(blob, dpi) {
    const buffer = new Uint8Array(await blob.arrayBuffer());
    const signature = [137, 80, 78, 71, 13, 10, 26, 10];
    if (buffer.length < 40 || signature.some((byte, i) => buffer[i] !== byte)) return blob;
    const ihdrLength = new DataView(buffer.buffer).getUint32(8);
    const insertAt = 8 + 12 + ihdrLength;
    const ppm = Math.round(dpi / 0.0254);
    const chunk = new Uint8Array(21);
    const view = new DataView(chunk.buffer);
    view.setUint32(0, 9);                       // chunk data length
    chunk.set([0x70, 0x48, 0x59, 0x73], 4);     // 'pHYs'
    view.setUint32(8, ppm);
    view.setUint32(12, ppm);
    chunk[16] = 1;                              // unit: metre
    view.setUint32(17, crc32(chunk.subarray(4, 17)));
    // Replace any density emitted by the browser: PNG permits only one pHYs.
    const parts = [buffer.subarray(0, insertAt), chunk];
    for (let offset = insertAt; offset < buffer.length;) {
      const length = new DataView(buffer.buffer).getUint32(offset);
      const end = offset + 12 + length;
      const isDensity = buffer[offset + 4] === 0x70 && buffer[offset + 5] === 0x48 &&
        buffer[offset + 6] === 0x59 && buffer[offset + 7] === 0x73;
      if (!isDensity) parts.push(buffer.subarray(offset, end));
      offset = end;
    }
    return new Blob(parts, {type: 'image/png'});
  }

  function download(blob, filename) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url; link.download = filename;
    document.body.append(link);
    link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
  }
  window.BioReportPlotlyExport = {attach};
})();
