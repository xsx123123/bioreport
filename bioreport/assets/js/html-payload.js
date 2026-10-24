/* Shared lossless table data for DataTables and linked Plotly charts. */
(() => {
  'use strict';
  if (window.BioReportHtmlPayload) return;
  const loaded = new WeakMap();
  function text(source) {
    if (!source.dataset.payloadRef) return source.textContent.trim();
    const shared = document.getElementById(source.dataset.payloadRef) ||
      window.parent.document.getElementById(source.dataset.payloadRef);
    if (!shared) throw new Error('The embedded report data is unavailable');
    return shared.textContent.trim();
  }
  async function decode(table) {
    if (table.dataset.source) {
      const response = await fetch(table.dataset.source);
      if (!response.ok) throw new Error('HTTP ' + response.status);
      return response.json();
    }
    const source = table.closest('.report-data-table').querySelector('.report-table-data');
    if (source.dataset.encoding !== 'columnar-gzip-base64') return JSON.parse(source.textContent);
    const bytes = Uint8Array.from(atob(text(source)), c => c.charCodeAt(0));
    const payload = await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).json();
    const columns = [];
    for (const column of payload.columnData) {
      let values;
      if (column.kind === 'alias') values = columns[column.column];
      else if (column.kind === 'f64') {
        const bytes = Uint8Array.from(atob(column.values), c => c.charCodeAt(0));
        const view = new DataView(bytes.buffer);
        values = Array.from({length: bytes.length / 8}, (_, i) => view.getFloat64(i * 8, true));
        for (const [i, value] of column.extras) values[i] = value;
      } else values = column.values;
      columns.push(values);
    }
    payload.data = Array.from({length: payload.rowCount}, (_, i) => columns.map(column => column[i]));
    delete payload.columnData;
    return payload;
  }
  function load(table) {
    if (!loaded.has(table)) {
      const promise = decode(table).catch(error => { loaded.delete(table); throw error; });
      loaded.set(table, promise);
    }
    return loaded.get(table);
  }
  window.BioReportHtmlPayload = {load, text};
})();
