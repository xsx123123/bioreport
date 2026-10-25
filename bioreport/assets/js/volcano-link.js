/* BioReport offline DEG table / Plotly volcano linkage. */
(() => {
  'use strict';
  if (window.BioReportVolcanoLink) return;
  const charts = new Map();
  const attachedTables = new WeakSet();
  const highlightKey = 'bioreport_gene_highlight';
  const messages = {
    zh: {
      locate: '在火山图中定位', action: '定位', clear: '清除标记', back: '返回基因表',
      hint: '搜索目标基因后，点击基因旁的“定位”，查看它在对应火山图中的位置。',
      missing: '未找到对应比较组的火山图，请等待图表加载后重试。',
      invalid: '该基因没有可绘制的坐标（log2FC 或 P 值缺失或无效）。',
      failed: '定位失败，请重试。', cleared: '标记已清除。', matches: '个匹配点',
    },
    en: {
      locate: 'Locate in volcano plot', action: 'Locate', clear: 'Clear highlight', back: 'Back to gene table',
      hint: 'Search for a gene, then click Locate beside its ID to highlight it in the matching volcano plot.',
      missing: 'The matching volcano plot is not ready. Wait for it to load and retry.',
      invalid: 'This gene has no plottable coordinates (missing or invalid log2FC or P value).',
      failed: 'Could not locate the gene. Please retry.', cleared: 'Highlight cleared.', matches: 'matching points',
    },
  };
  const words = options => messages[options.language] || messages.en;
  const escape = value => String(value ?? '').replace(/[&<>"']/g, character =>
    ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[character]));
  const haloKey = 'bioreport_gene_highlight_halo';
  const ICONS = {
    target: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="7"/><path d="M12 2.5V6M12 18v3.5M2.5 12H6M18 12h3.5"/><circle cx="12" cy="12" r="1.5" fill="currentColor" stroke="none"/></svg>',
    info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="8.5"/><path d="M12 11v5"/><path d="M12 7.8h.01"/></svg>',
  };
  const style = document.createElement('style');
  style.textContent = `
    .report-gene-locate {display:inline-flex;align-items:center;gap:.45em;max-width:100%;
      border:0;background:transparent;padding:2px 0;color:inherit;
      font:inherit;text-align:left;cursor:pointer;white-space:nowrap;}
    .report-locate-chip {display:inline-flex;align-items:center;gap:.32em;padding:.08em .6em .12em;
      border:1px solid transparent;border-radius:999px;font-size:.76em;font-weight:600;line-height:1.6;
      color:var(--br-primary,#2563eb);background:var(--br-surface-hover,#eff6ff);
      transition:border-color .15s ease,background .15s ease,color .15s ease;}
    .report-locate-chip svg {width:1em;height:1em;flex:none;}
    .report-gene-locate:hover .report-locate-chip,.report-gene-locate:focus-visible .report-locate-chip {
      border-color:var(--br-primary,#2563eb);}
    .report-gene-locate:focus-visible,.report-volcano-tools button:focus-visible {
      outline:2px solid var(--br-primary,#2563eb);outline-offset:3px;}
    .report-gene-locate:disabled {opacity:.6;cursor:wait;}
    .report-volcano-hint {display:flex;align-items:flex-start;gap:.5rem;margin:.5rem 0;padding:.5rem .8rem;
      font-size:.85rem;line-height:1.55;color:var(--br-muted,#52657d);
      border:1px solid var(--br-border,#e2e8f0);border-left:3px solid var(--br-primary,#2563eb);
      border-radius:8px;background:var(--br-surface-soft,#f8fafc);}
    .report-hint-icon {flex:none;display:inline-flex;margin-top:.15em;color:var(--br-primary,#2563eb);}
    .report-hint-icon svg {width:1em;height:1em;}
    .report-hint-text {flex:1;min-width:0;}
    .report-volcano-tools {position:relative;z-index:1;display:flex;align-items:center;flex-wrap:wrap;
      gap:.45rem .6rem;margin:.5rem 0;padding:.5rem .75rem;
      border:1px solid var(--br-border,#e2e8f0);border-radius:10px;
      background:var(--br-surface,#fff);box-shadow:0 1px 3px rgba(15,23,42,.07);
      scroll-margin-top:calc(var(--report-navbar-height,80px) + 16px);}
    .report-volcano-tools[hidden] {display:none;}
    .report-volcano-badge {flex:none;display:inline-flex;align-items:center;justify-content:center;
      width:30px;height:30px;border-radius:8px;
      color:var(--br-primary,#2563eb);background:var(--br-surface-hover,#eff6ff);}
    .report-volcano-badge svg {width:16px;height:16px;}
    .report-volcano-info {flex:1 1 280px;display:flex;align-items:center;flex-wrap:wrap;
      gap:.3rem .6rem;min-width:0;font-size:.88rem;}
    .report-volcano-comparison {padding:.08em .6em;border-radius:999px;font-size:.8em;font-weight:600;
      color:var(--br-primary,#2563eb);background:var(--br-surface-hover,#eff6ff);}
    .report-volcano-gene {font-weight:600;overflow-wrap:anywhere;}
    .report-volcano-stat {white-space:nowrap;}
    .report-volcano-stat i {font-style:normal;color:var(--br-muted,#52657d);}
    .report-volcano-stat b {font-weight:600;}
    .report-volcano-tools button {padding:.38rem .8rem;border-radius:7px;font:inherit;font-size:.85rem;
      font-weight:500;cursor:pointer;transition:background .15s ease,border-color .15s ease,color .15s ease;
      scroll-margin-top:calc(var(--report-navbar-height,80px) + 16px);}
    .report-volcano-tools .report-btn-ghost {border:1px solid var(--br-border,#cbd5e1);
      background:var(--br-surface,#fff);color:inherit;}
    .report-volcano-tools .report-btn-ghost:hover {border-color:var(--br-primary,#2563eb);
      color:var(--br-primary,#2563eb);}
    .report-volcano-tools .report-btn-primary {border:1px solid var(--br-primary,#2563eb);
      background:var(--br-primary,#2563eb);color:#fff;}
    :root[data-report-theme="dark"] .report-volcano-tools .report-btn-primary {color:#0b1526;}
    @media print {.report-volcano-tools,.report-volcano-hint,.report-gene-locate .report-locate-chip {display:none;}}
  `;
  document.head.append(style);

  function decorateColumns(columns, names, options) {
    const text = words(options);
    const index = names.indexOf(options.idColumn);
    const render = (value, type) => {
      if (type !== 'display') return value;
      if (index >= 0 && (value == null || String(value).trim() === '')) return '';
      return `<button type="button" class="report-gene-locate" title="${escape(text.locate)}" ` +
        `aria-label="${escape(text.locate + (index >= 0 ? ': ' + value : ''))}">` +
        `${index >= 0 ? escape(value) : ''}` +
        `<span class="report-locate-chip">${ICONS.target}${escape(text.action)}</span></button>`;
    };
    if (index >= 0) columns[index].render = render;
    else columns.push({title: text.action, data: null, orderable: false, searchable: false,
      className: 'report-volcano-action', render: (_, type) => type === 'display' ? render('', type) : ''});
  }

  function attachTable(table, options) {
    if (attachedTables.has(table)) return;
    attachedTables.add(table);
    const text = words(options);
    const hint = document.createElement('p');
    hint.className = 'report-volcano-hint';
    hint.setAttribute('role', 'status');
    const icon = document.createElement('span');
    icon.className = 'report-hint-icon';
    icon.setAttribute('aria-hidden', 'true');
    icon.innerHTML = ICONS.info;
    const message = document.createElement('span');
    message.className = 'report-hint-text';
    message.textContent = text.hint;
    hint.append(icon, message);
    const setHint = value => { message.textContent = value; };
    table.closest('.report-data-table').prepend(hint);
    table.addEventListener('click', async event => {
      const button = event.target.closest('.report-gene-locate');
      if (!button || button.disabled) return;
      const api = table._reportTable;
      const row = api.row(button.closest('tr'));
      if (!row.data()) return;
      let state = charts.get(options.comparison);
      if (!state) { setHint(text.missing); return; }
      const names = api.settings()[0].aoColumns.map(column => column.sName);
      const column = names.indexOf(options.idColumn);
      const identity = column >= 0 ? row.data()[column] : row.index();
      button.disabled = true;
      try {
        if (state.load) {
          await reveal(state.root);
          await state.load();
          state = charts.get(options.comparison);
        }
        if (!state?.chart?.isConnected) { setHint(text.missing); return; }
        state.pending = state.pending.catch(() => {}).then(() => locate(state, identity, {
          table, button, names, data: row.data(),
        }));
        const found = await state.pending;
        setHint(found ? text.hint : text.invalid);
      } catch (error) {
        console.error('BioReport volcano gene location failed', error);
        setHint(text.failed);
      } finally { button.disabled = false; }
    });
  }

  async function reveal(element) {
    const page = element.closest('.report-page');
    if (page?.hidden && page.id) {
      location.hash = '#' + encodeURIComponent(page.id);
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    }
    for (let parent = element.parentElement; parent; parent = parent.parentElement) {
      if (parent.tagName === 'DETAILS') parent.open = true;
    }
    const panes = [];
    for (let pane = element.closest('.tab-pane'); pane; pane = pane.parentElement?.closest('.tab-pane'))
      panes.unshift(pane);
    for (const pane of panes) {
      if (pane.classList.contains('active')) continue;
      const trigger = [...document.querySelectorAll('[data-bs-toggle="tab"],[data-toggle="tab"]')].find(node =>
        (node.getAttribute('data-bs-target') || node.getAttribute('data-target') || node.getAttribute('href')) === '#' + pane.id ||
        node.getAttribute('aria-controls') === pane.id);
      if (!trigger) continue;
      await new Promise(resolve => {
        const finish = () => { clearTimeout(timer); trigger.removeEventListener('shown.bs.tab', finish); resolve(); };
        const timer = setTimeout(finish, 400);
        trigger.addEventListener('shown.bs.tab', finish, {once: true});
        if (window.bootstrap?.Tab) window.bootstrap.Tab.getOrCreateInstance(trigger).show();
        else trigger.click();
      });
    }
    await new Promise(resolve => requestAnimationFrame(resolve));
  }

  function attachChart(chart, options) {
    if (chart._reportVolcanoLink) return;
    const text = words(options);
    const toolbar = document.createElement('div');
    toolbar.className = 'report-volcano-tools';
    toolbar.hidden = true;
    const badge = document.createElement('span');
    badge.className = 'report-volcano-badge';
    badge.setAttribute('aria-hidden', 'true');
    badge.innerHTML = ICONS.target;
    const status = document.createElement('div');
    status.className = 'report-volcano-info';
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    const clear = document.createElement('button');
    clear.type = 'button'; clear.className = 'report-btn-ghost'; clear.textContent = text.clear;
    const back = document.createElement('button');
    back.type = 'button'; back.className = 'report-btn-primary'; back.textContent = text.back;
    toolbar.append(badge, status, clear, back);
    const wrapper = chart.closest('.report-plot') || chart;
    wrapper.before(toolbar);
    const state = {chart, options, toolbar, status, clear, back, source: null, pending: Promise.resolve()};
    chart._reportVolcanoLink = state;
    charts.set(options.comparison, state);
    clear.onclick = async () => {
      clear.disabled = true;
      try {
        state.pending = state.pending.catch(() => {}).then(() => removeHighlight(chart));
        await state.pending;
        status.textContent = text.cleared;
      } catch (error) { console.error('BioReport volcano clear failed', error); status.textContent = text.failed; }
      finally { clear.disabled = false; }
    };
    back.onclick = async () => {
      if (!state.source) return;
      await reveal(state.source.table);
      state.source.table._reportTable.columns.adjust();
      state.source.table.closest('.report-data-table').scrollIntoView({block: 'start', behavior: 'instant'});
      if (state.source.button.isConnected) state.source.button.focus({preventScroll: true});
    };
  }

  async function removeHighlight(chart) {
    const indices = chart.data.flatMap((trace, index) =>
      (trace.meta?.[highlightKey] || trace.meta?.[haloKey]) ? [index] : []);
    if (indices.length) await Plotly.deleteTraces(chart, indices);
  }

  async function locate(state, identity, source) {
    const {chart, options} = state;
    const matches = [];
    for (const trace of chart._fullData || chart.data) {
      if (trace.meta?.[highlightKey]) continue;
      const ids = trace.customdata || [];
      for (let i = 0; i < ids.length; i++) {
        if (String(ids[i]) !== String(identity)) continue;
        const x = trace.x?.[i], y = trace.y?.[i];
        if (typeof x !== 'number' || typeof y !== 'number' || !Number.isFinite(x) || !Number.isFinite(y)) continue;
        const symbol = typeof trace.text === 'string' ? trace.text : trace.text?.[i];
        matches.push({x, y, label: symbol && String(symbol).length <= 40 && String(symbol) !== String(identity)
          ? `${symbol} (${identity})` : String(identity)});
      }
    }
    if (!matches.length) return false;
    await reveal(chart);
    await removeHighlight(chart);
    const theme = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    const accent = theme('--br-primary') || '#2563eb';
    const labelColor = theme('--br-primary-dark') || '#203a5f';
    const xs = matches.map(point => point.x), ys = matches.map(point => point.y);
    await Plotly.addTraces(chart, [
      {type: 'scatter', mode: 'markers', x: xs, y: ys, hoverinfo: 'skip', showlegend: false,
        marker: {symbol: 'circle', size: 30, color: accent, opacity: .16},
        meta: {[haloKey]: true}},
      {type: 'scatter', mode: 'markers+text', x: xs, y: ys,
        text: matches.map(point => escape(point.label)), textposition: 'top center', cliponaxis: false,
        marker: {symbol: 'circle-open-dot', size: 16, color: accent, line: {width: 2.5, color: accent}},
        textfont: {color: labelColor, size: 12.5}, hoverinfo: 'skip', showlegend: false,
        meta: {[highlightKey]: true}},
    ]);
    // Restore the plot extent when a previous zoom would hide the target gene.
    const visible = matches.every(point => ['x', 'y'].every(axis => {
      const range = chart._fullLayout[axis + 'axis'].range;
      return point[axis] >= Math.min(...range) && point[axis] <= Math.max(...range);
    }));
    if (!visible) {
      const restore = {'yaxis.autorange': true};
      // Keep the x axis centered on zero when the figure declares a symmetric limit.
      if (Number.isFinite(options.xLimit)) {
        restore['xaxis.autorange'] = false;
        restore['xaxis.range'] = [-options.xLimit, options.xLimit];
      } else restore['xaxis.autorange'] = true;
      await Plotly.relayout(chart, restore);
    }
    await Plotly.Plots.resize(chart);
    const point = matches[0];
    const pIndex = source.names.findIndex(name => ['pvalue', 'p_value'].includes(name.toLowerCase()));
    const p = pIndex >= 0 ? source.data[pIndex] : null;
    const number = value => String(Number(Number(value).toPrecision(5)));
    const stat = (label, value) => {
      const item = document.createElement('span');
      item.className = 'report-volcano-stat';
      const tag = document.createElement('i');
      tag.textContent = label;
      const strong = document.createElement('b');
      strong.textContent = value;
      item.append(tag, document.createTextNode(' = '), strong);
      return item;
    };
    const chip = document.createElement('span');
    chip.className = 'report-volcano-comparison';
    chip.textContent = options.comparison;
    const gene = document.createElement('strong');
    gene.className = 'report-volcano-gene';
    gene.textContent = point.label;
    const info = [chip, gene, stat('log2FC', number(point.x)),
      p != null ? stat('P', number(p)) : stat('−log10(P)', number(point.y))];
    if (matches.length > 1) {
      const extra = document.createElement('span');
      extra.className = 'report-volcano-stat';
      extra.textContent = `${matches.length} ${words(options).matches}`;
      info.push(extra);
    }
    state.status.replaceChildren(...info);
    state.source = source;
    state.toolbar.hidden = false;
    state.toolbar.scrollIntoView({block: 'start', behavior: 'instant'});
    state.clear.focus({preventScroll: true});
    return true;
  }

  function attachLazyChart(root, load, options) {
    charts.set(options.comparison, {root, load});
  }

  window.BioReportVolcanoLink = {decorateColumns, attachTable, attachChart, attachLazyChart};
})();
