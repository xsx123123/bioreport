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
  const style = document.createElement('style');
  style.textContent = `
    .report-gene-locate {display:inline-flex;align-items:center;gap:.5em;max-width:100%;
      border:0;background:transparent;padding:3px 0;color:var(--br-primary,#2563eb);
      font:inherit;text-align:left;cursor:pointer;white-space:nowrap;}
    .report-gene-locate span {font-size:.8em;text-decoration:underline;}
    .report-gene-locate:focus-visible,.report-volcano-tools button:focus-visible {
      outline:2px solid var(--br-primary,#2563eb);outline-offset:3px;}
    .report-gene-locate:disabled {opacity:.6;cursor:wait;}
    .report-volcano-hint {font-size:.875rem;color:var(--br-muted,#52657d);margin:.5rem 0;}
    .report-volcano-tools {position:relative;z-index:1;display:flex;align-items:center;flex-wrap:wrap;gap:.5rem;
      margin:.5rem 0;padding:.75rem;border:1px solid var(--br-border,#cbd5e1);
      border-radius:8px;background:var(--br-surface,#fff);
      scroll-margin-top:calc(var(--report-navbar-height,80px) + 16px);}
    .report-volcano-tools[hidden] {display:none;}
    .report-volcano-tools [role=status] {flex:1 1 260px;overflow-wrap:anywhere;}
    .report-volcano-tools button {padding:.35rem .65rem;border:1px solid var(--br-border,#cbd5e1);
      border-radius:6px;background:var(--br-surface,#fff);color:inherit;font:inherit;cursor:pointer;
      scroll-margin-top:calc(var(--report-navbar-height,80px) + 16px);}
    @media print {.report-volcano-tools,.report-volcano-hint,.report-gene-locate span {display:none;}}
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
        `${index >= 0 ? escape(value) : ''}<span>${escape(text.action)}</span></button>`;
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
    hint.textContent = text.hint;
    table.closest('.report-data-table').prepend(hint);
    table.addEventListener('click', async event => {
      const button = event.target.closest('.report-gene-locate');
      if (!button || button.disabled) return;
      const api = table._reportTable;
      const row = api.row(button.closest('tr'));
      if (!row.data()) return;
      let state = charts.get(options.comparison);
      if (!state) { hint.textContent = text.missing; return; }
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
        if (!state?.chart?.isConnected) { hint.textContent = text.missing; return; }
        state.pending = state.pending.catch(() => {}).then(() => locate(state, identity, {
          table, button, names, data: row.data(),
        }));
        const found = await state.pending;
        hint.textContent = found ? text.hint : text.invalid;
      } catch (error) {
        console.error('BioReport volcano gene location failed', error);
        hint.textContent = text.failed;
      } finally { button.disabled = false; }
    });
  }

  async function reveal(element) {
    const page = element.closest('.report-page');
    if (page?.hidden && page.id) {
      location.hash = '#' + encodeURIComponent(page.id);
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    }
    for (let parent = element.parentElement; parent; parent = parent.parentElement)
      if (parent.tagName === 'DETAILS') parent.open = true;
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
    const status = document.createElement('span');
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    const clear = document.createElement('button');
    clear.type = 'button'; clear.textContent = text.clear;
    const back = document.createElement('button');
    back.type = 'button'; back.textContent = text.back;
    toolbar.append(status, clear, back);
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
    const indices = chart.data.flatMap((trace, index) => trace.meta?.[highlightKey] ? [index] : []);
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
    await Plotly.addTraces(chart, {
      type: 'scatter', mode: 'markers+text', x: matches.map(point => point.x), y: matches.map(point => point.y),
      text: matches.map(point => escape(point.label)), textposition: 'top center', cliponaxis: false,
      marker: {symbol: 'circle-open', size: 22, color: '#d97706', line: {width: 3}},
      textfont: {color: '#b45309', size: 13}, hoverinfo: 'skip', showlegend: false,
      meta: {[highlightKey]: true},
    });
    // Restore the plot extent when a previous zoom would hide the target gene.
    const visible = matches.every(point => ['x', 'y'].every(axis => {
      const range = chart._fullLayout[axis + 'axis'].range;
      return point[axis] >= Math.min(...range) && point[axis] <= Math.max(...range);
    }));
    if (!visible) await Plotly.relayout(chart, {'xaxis.autorange': true, 'yaxis.autorange': true});
    await Plotly.Plots.resize(chart);
    const point = matches[0];
    const pIndex = source.names.findIndex(name => ['pvalue', 'p_value'].includes(name.toLowerCase()));
    const p = pIndex >= 0 ? source.data[pIndex] : null;
    const number = value => String(Number(Number(value).toPrecision(5)));
    state.status.textContent = `${options.comparison} · ${point.label} · log2FC = ${number(point.x)}` +
      (p != null ? ` · P = ${number(p)}` : ` · −log10(P) = ${number(point.y)}`) +
      (matches.length > 1 ? ` · ${matches.length} ${words(options).matches}` : '');
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
