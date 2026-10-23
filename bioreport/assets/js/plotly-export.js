/* BioReport offline chart downloads. No server or third-party PDF runtime. */
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
      hint: '宽高为导出图像的实际像素尺寸；PNG 固定按 1000 DPI 写入元数据（物理尺寸 = 像素 ÷ 1000 英寸）。SVG 保留矢量图形；PDF 内嵌无损图像。',
      invalid: '宽度和高度须为 100–16000 之间的整数。',
      large: 'PNG 和 PDF 最多支持 1600 万像素，请减小宽度或高度。',
      failed: '导出失败，请重试或减小尺寸。',
      tipPalette: '切换分组配色方案', tipScale: '切换连续色带',
    },
    en: {
      open: 'Download chart', title: 'Download chart', format: 'File format',
      width: 'Width (px)', height: 'Height (px)', lock: 'Lock aspect ratio',
      reset: 'Reset', cancel: 'Cancel', download: 'Download', busy: 'Exporting…',
      hint: 'Width and height are the exported image dimensions; PNG metadata is fixed at 1000 DPI (physical size = pixels ÷ 1000 inches). SVG retains vectors; PDF embeds a lossless image.',
      invalid: 'Width and height must be integers between 100 and 16000.',
      large: 'PNG and PDF support up to 16 million pixels. Reduce the width or height.',
      failed: 'Export failed. Please retry or reduce the dimensions.',
      tipPalette: 'Switch group color palette', tipScale: 'Switch color scale',
    },
  };
  // PNG resolution is not a user choice: every download carries 1000 DPI metadata.
  const PNG_DPI = 1000;
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
      <p data-label="hint"></p><p class="report-export-status" role="status" aria-live="polite"></p>
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
      });
    }
    dialog.querySelector('[name=lock]').addEventListener('change', () => {
      const fields = dialog.querySelector('form').elements;
      if (Number(fields.width.value) > 0 && Number(fields.height.value) > 0)
        active.ratio = Number(fields.width.value) / Number(fields.height.value);
    });
    dialog.querySelector('form').addEventListener('submit', exportChart);
  }

  function fill(value) {
    const fields = dialog.querySelector('form').elements;
    for (const name of ['format', 'width', 'height']) fields[name].value = value[name];
    fields.lock.checked = value.lock;
    active.ratio = value.width / value.height;
    dialog.querySelector('.report-export-status').textContent = '';
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
    if (![width, height].every(value => Number.isInteger(value) && value >= 100 && value <= 16000)) {
      status.textContent = text.invalid;
      return;
    }
    if (format !== 'svg' && width * height > 16000000) {
      status.textContent = text.large;
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
    // Interactive color-switch dropdowns are part of the on-screen chart, not
    // of the exported image: hide them for the snapshot, then put them back.
    const menus = state.chart.layout?.updatemenus;
    if (menus?.length) await Plotly.relayout(state.chart, {updatemenus: []});
    try {
      await document.fonts.ready;
      const url = await Plotly.toImage(state.chart, {format: 'svg', width, height, scale: 1});
      const svg = await portableSvg(url);
      let blob;
      if (format === 'svg') blob = new Blob([svg], {type: 'image/svg+xml;charset=utf-8'});
      else {
        canvas = await rasterize(svg, width, height, format === 'pdf');
        if (format === 'pdf') blob = await imagePdf(canvas);
        else blob = await withDpi(await new Promise((resolve, reject) => canvas.toBlob(
          value => value ? resolve(value) : reject(new Error('PNG encoding failed')), 'image/png')), PNG_DPI);
      }
      download(blob, state.filename + '.' + format);
      dialog.close();
    } catch (error) {
      console.error('BioReport chart export failed', error);
      status.textContent = text.failed;
    } finally {
      if (menus?.length) await Plotly.relayout(state.chart, {updatemenus: menus});
      if (canvas) { canvas.width = 0; canvas.height = 0; }
      state.busy = false;
      controls.forEach(node => { node.disabled = false; });
      dialog.removeAttribute('aria-busy');
      submit.textContent = text.download;
    }
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

  // A single-page PDF with a lossless RGB image. PDF points use 72/inch,
  // whereas the dialog dimensions are CSS pixels (96/inch). No print dialog.
  async function imagePdf(canvas) {
    const width = canvas.width, height = canvas.height;
    const rgba = canvas.getContext('2d').getImageData(0, 0, width, height).data;
    let rgb = new Uint8Array(width * height * 3);
    for (let i = 0, j = 0; i < rgba.length; i += 4) {
      rgb[j++] = rgba[i]; rgb[j++] = rgba[i + 1]; rgb[j++] = rgba[i + 2];
    }
    let filter = '';
    if (window.CompressionStream) {
      const stream = new Blob([rgb]).stream().pipeThrough(new CompressionStream('deflate'));
      rgb = new Uint8Array(await new Response(stream).arrayBuffer());
      filter = '/Filter /FlateDecode ';
    }
    const encode = value => new TextEncoder().encode(value);
    const pageWidth = width * .75, pageHeight = height * .75;
    const contents = `q ${pageWidth} 0 0 ${pageHeight} 0 0 cm /Chart Do Q\n`;
    const objects = [
      ['<< /Type /Catalog /Pages 2 0 R >>'],
      ['<< /Type /Pages /Kids [3 0 R] /Count 1 >>'],
      [`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${pageWidth} ${pageHeight}] /Resources << /XObject << /Chart 5 0 R >> >> /Contents 4 0 R >>`],
      [`<< /Length ${encode(contents).length} >>\nstream\n${contents}endstream`],
      [`<< /Type /XObject /Subtype /Image /Width ${width} /Height ${height} /ColorSpace /DeviceRGB /BitsPerComponent 8 ${filter}/Length ${rgb.length} >>\nstream\n`, rgb, '\nendstream'],
    ];
    const parts = [encode('%PDF-1.4\n%BioReport\n')], offsets = [0];
    let size = parts[0].length;
    const append = value => { const bytes = typeof value === 'string' ? encode(value) : value; parts.push(bytes); size += bytes.length; };
    objects.forEach((object, index) => {
      offsets.push(size);
      append(`${index + 1} 0 obj\n`);
      object.forEach(append);
      append('\nendobj\n');
    });
    const xref = size;
    append(`xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`);
    offsets.slice(1).forEach(offset => append(`${String(offset).padStart(10, '0')} 00000 n \n`));
    append(`trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`);
    return new Blob(parts, {type: 'application/pdf'});
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
    const out = new Uint8Array(buffer.length + chunk.length);
    out.set(buffer.subarray(0, insertAt));
    out.set(chunk, insertAt);
    out.set(buffer.subarray(insertAt), insertAt + chunk.length);
    return new Blob([out], {type: 'image/png'});
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
