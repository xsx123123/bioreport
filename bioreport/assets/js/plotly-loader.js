/* Lossless offline chart payloads. Initialize visible charts, two at a time. */
(() => {
  'use strict';
  if (window.BioReportPlotlyLoader) return;
  const states = new Map(), queue = [];
  const documentReady = document.readyState === 'loading'
    ? new Promise(resolve => document.addEventListener('DOMContentLoaded', resolve, {once:true})) : Promise.resolve();
  let active = 0;
  const observer = typeof IntersectionObserver === 'function' ? new IntersectionObserver(entries => {
    for (const entry of entries) if (entry.isIntersecting) {
      observer.unobserve(entry.target);
      entry.target._reportPlotLoader.load().catch(() => {});
    }
  }, {rootMargin: '200px'}) : null;

  const style = document.createElement('style');
  style.textContent = '.report-plot-status{position:absolute;inset:0;display:grid;place-content:center;gap:12px;'
    + 'margin:0;color:var(--br-muted,#52657d);font-size:.875rem;text-align:center;}'
    + '.report-plot-status button{padding:6px 14px;cursor:pointer;color:inherit;'
    + 'background:var(--br-surface,#fff);border:1px solid var(--br-border,#cbd5e1);border-radius:6px;}';
  document.head.append(style);

  function finish(state) {
    clearTimeout(state.timeout);
    if (state.running) { state.running = false; active--; }
    pump();
  }

  function ready(id) {
    const state = states.get(id);
    if (!state || state.done) return;
    state.done = true;
    state.root.dataset.loaded = 'true';
    delete state.payload;
    state.resolve(document.getElementById(id));
    finish(state);
  }

  function fail(state, error) {
    console.error('BioReport chart initialization failed', error);
    const notice = document.createElement('p');
    notice.className = 'report-plot-status';
    notice.setAttribute('role', 'status');
    notice.textContent = state.options.language === 'zh' ? '图表加载失败，请重试。' : 'Chart could not load. Please retry.';
    const retry = document.createElement('button');
    retry.type = 'button'; retry.textContent = state.options.language === 'zh' ? '重试' : 'Retry';
    retry.onclick = () => state.load().catch(() => {});
    notice.append(retry);
    state.root.replaceChildren(notice);
    state.root.style.minHeight = '280px';
    state.reject(error);
    state.promise = null;
    finish(state);
  }

  async function hydrate(state) {
    await documentReady;
    state.payload ||= window.BioReportHtmlPayload.text(state.root.querySelector('.report-plot-data'));
    const bytes = Uint8Array.from(atob(state.payload), c => c.charCodeAt(0));
    const markup = await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).text();
    const template = document.createElement('template');
    template.innerHTML = markup;
    const scripts = [...template.content.querySelectorAll('script')];
    state.root.replaceChildren(template.content);
    state.root.style.removeProperty('min-height');
    state.root.style.removeProperty('aspect-ratio');
    // Scripts parsed via innerHTML are inert. Execute the generated Plotly
    // initializer as an ordinary local inline script, without eval or fetch.
    for (const script of scripts) {
      const execution = document.createElement('script');
      execution.textContent = script.textContent;
      script.replaceWith(execution);
    }
  }

  function pump() {
    while (active < 2 && queue.length) {
      const state = queue.shift();
      state.running = true; active++;
      state.timeout = setTimeout(() => fail(state, new Error('Chart initialization timed out')), 120000);
      hydrate(state).catch(error => fail(state, error));
    }
  }

  function register(id, options) {
    const root = document.getElementById(id);
    const state = {root, options, promise: null, running: false, done: false};
    state.load = () => {
      if (!state.promise) {
        state.promise = new Promise((resolve, reject) => { state.resolve = resolve; state.reject = reject; });
        queue.push(state); pump();
      }
      return state.promise;
    };
    states.set(options.chartId, state);
    root._reportPlotLoader = state;
    if (options.volcano) window.BioReportVolcanoLink.attachLazyChart(root, state.load,
      {...options.volcano, language: options.language});
    if (observer) observer.observe(root);
    else state.load().catch(() => {});
  }

  async function newPlot(id, traces, layout, config) {
    const source = layout.meta.bioreport_table_source;
    const table = document.getElementById(source.tableId);
    if (!table) throw new Error('The source DEG table is unavailable');
    const payload = await window.BioReportHtmlPayload.load(table);
    const index = name => payload.columns.indexOf(name);
    const xi = index(source.xColumn), pi = index(source.pColumn);
    const ti = index(source.textColumn), gi = index(source.idColumn);
    if ([xi, pi, ti, gi].some(value => value < 0)) throw new Error('DEG table columns do not match the volcano plot');
    const groups = new Map(['NS', 'Down', 'Up'].map(name => [name, {x:[], y:[], text:[], customdata:[]}]));
    const numeric = value => typeof value === 'number' ? value
      : value === 'Infinity' ? Infinity : value === '-Infinity' ? -Infinity : NaN;
    for (const row of payload.data) {
      const x = numeric(row[xi]), p = numeric(row[pi]);
      const direction = p < source.pCutoff && x > source.fcCutoff ? 'Up'
        : p < source.pCutoff && x < -source.fcCutoff ? 'Down' : 'NS';
      const group = groups.get(direction);
      let y = -Math.log10(p + 1e-300);
      if (source.displayCap != null) y = Math.min(y, source.displayCap);
      group.x.push(Number.isFinite(x) ? x : null);
      group.y.push(Number.isFinite(y) ? y : null);
      group.text.push(row[ti]);
      group.customdata.push(String(row[gi]));
    }
    const data = traces.map(trace => groups.has(trace.name) ? {...trace, ...groups.get(trace.name)} : trace);
    return Plotly.newPlot(id, data, layout, config);
  }

  window.BioReportPlotlyLoader = {register, ready, newPlot};
})();
