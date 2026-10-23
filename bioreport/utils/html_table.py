"""Full precision compact tables, initialized only when their container is visible."""
import hashlib
import itertools
import json
import math
import os
from html import escape
from pathlib import Path
import shutil

from IPython.display import HTML, display
from bioreport.i18n import language

_ids = itertools.count(1)
TABLE_DOM = '<"d-flex justify-content-between align-items-center mb-3"Blf>rt<"d-flex justify-content-between align-items-center mt-3"ip>'
NUMBER_RENDER_JS = '''function(data, type, row, meta) {
    const value = Array.isArray(data) && data.length === 2 ? data[1] : data;
    if (type !== 'display' || typeof value !== 'number' || !Number.isFinite(value)) return value;
    const column = meta?.settings?.aoColumns?.[meta.col];
    const name = (column?.sName || column?.name || '').toLowerCase();
    if (name === 'basemean') return value.toFixed(1);
    if (['pvalue','padj','p.adjust','qvalue','fdr'].includes(name))
        return value === 0 ? '0' : value.toExponential(2);
    if (['log2foldchange','lfcse','stat','richfactor','foldenrichment','zscore'].includes(name))
        return value.toFixed(3);
    if (Number.isInteger(value)) return String(value);
    const absolute = Math.abs(value);
    return absolute < 0.001 || absolute >= 1000000 ? value.toExponential(3)
        : new Intl.NumberFormat('en-US', {maximumFractionDigits:4, useGrouping:false}).format(value);
}'''
DESCRIPTION_RENDER_JS = '''function(data, type) {
    if (type !== 'display' || data == null) return data;
    const escaped = String(data).replace(/[&<>"']/g, character =>
        ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[character]));
    return '<span class="report-description-text" title="' + escaped + '">' + escaped + '</span>';
}'''
GENE_LIST_RENDER_JS = '''function(data, type) {
    if (type !== 'display' || data == null) return data;
    const escaped = String(data).replace(/[&<>"']/g, character =>
        ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[character]));
    return '<div class="report-gene-list" tabindex="0">' + escaped + '</div>';
}'''


def stage_table_runtime():
    import itables
    directory = Path(os.environ['BIOREPORT_SHARED_ASSET_DIR'])
    directory.mkdir(parents=True, exist_ok=True)
    bundle = Path(itables.__file__).parent / 'html'
    for name in ('dt_bundle.js', 'dt_bundle.css'):
        if not (directory / name).exists():
            shutil.copyfile(bundle / name, directory / name)
    return directory


def compact_payload(frame):
    """Preserve finite numbers exactly; only display rendering rounds values."""
    data = frame.astype(object).where(frame.notna(), None).values.tolist()
    for row in data:
        for index, value in enumerate(row):
            if isinstance(value, float) and math.isinf(value):
                row[index] = 'Infinity' if value > 0 else '-Infinity'
    return {'columns':[str(column) for column in frame.columns],
            'numeric':[i for i, dtype in enumerate(frame.dtypes) if dtype.kind in 'iuf'],
            'data':data}


def show_local_table(frame):
    """Compatibility entry point for shared website tables."""
    show_compact_table(frame)


def table_column_defs(frame, offset=0):
    """One presentation policy; preserve source columns and full numeric values.

    Only hide Symbol when the complete, nonempty column equals ENSEMBL.
    Real gene annotations always remain visible. Buttons export visible columns.
    """
    names = list(map(str, frame.columns))
    duplicate_symbol = ('ENSEMBL' in names and 'Symbol' in names and len(frame) > 0
                        and frame['ENSEMBL'].notna().any()
                        and frame['ENSEMBL'].equals(frame['Symbol']))
    definitions = []
    for index, (name, dtype) in enumerate(zip(names, frame.dtypes)):
        numeric = dtype.kind in 'iuf'
        options = {'targets': index + offset, 'name': name,
                   'className': 'dt-right report-number-column' if numeric else 'dt-left'}
        if numeric:
            options['width'] = '140px'
        if name == 'Description':
            options.update(width='40%', className='dt-left report-description-column')
        elif name == 'ID':
            options.update(width='130px', className='dt-left report-term-id-column')
        elif name in ('GeneRatio', 'BgRatio'):
            options.update(width='120px', className='dt-right report-number-column')
        elif name.lower() == 'geneid':
            options.update(width='24rem', className='dt-left report-gene-list-column')
        if duplicate_symbol and name == 'Symbol':
            options['visible'] = False
        definitions.append(options)
    return definitions


def export_button_text(kind):
    """Present existing export actions without changing their data or callbacks."""
    label = ('Copy' if language() == 'en' else '复制') if kind == 'copy' else kind.upper() if kind == 'csv' else 'Excel'
    path = '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V4H4v12h4"/>' if kind == 'copy' else '<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>'
    return '<svg viewBox="0 0 24 24" aria-hidden="true">' + path + '</svg>' + label


def show_compact_table(frame):
    payload = json.dumps(compact_payload(frame), ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    digest = hashlib.sha256(payload.encode()).hexdigest()[:20]
    table_id = f'report-table-{digest}-{next(_ids)}'
    shared = os.environ.get('BIOREPORT_SHARED_ASSET_DIR')
    if shared:
        directory = stage_table_runtime()
        filename = f'table-{digest}.json'
        (directory / filename).write_text(payload, encoding='utf-8')
        root = os.environ['BIOREPORT_SHARED_ASSET_URL']
        css = f'<link rel="stylesheet" href="{escape(root, quote=True)}/dt_bundle.css">'
        runtime = 'import(' + json.dumps(root + '/dt_bundle.js') + ')'
        dataset = ' data-source=' + json.dumps(root + '/' + filename)
        embedded = ''
    else:
        from .render_output import ensure_table_runtime
        runtime = ensure_table_runtime()
        css, dataset = '', ''
        # Script raw-text elements must not be closable by data or column names.
        safe = payload.replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
        embedded = f'<script type="application/json" class="report-table-data">{safe}</script>'
    english = language() == 'en'
    waiting = 'Table loads when visible' if english else '表格将在进入视野时加载'
    loading = 'Loading table…' if english else '正在加载表格…'
    ready = 'Ready' if english else '已加载'
    retry = 'Retry' if english else '重试'
    failed = 'Table could not load' if english else '表格加载失败'
    locale = {} if english else {'search':'搜索:', 'lengthMenu':'每页 _MENU_ 行',
        'info':'显示 _START_ 至 _END_ 行，共 _TOTAL_ 行', 'infoEmpty':'没有记录',
        'infoFiltered':'（从 _MAX_ 行中筛选）', 'zeroRecords':'没有匹配的记录',
        'emptyTable':'暂无数据', 'paginate':{'first':'首页','previous':'上一页','next':'下一页','last':'末页'}}
    enrichment = {'Description', 'GeneRatio', 'p.adjust'} <= set(frame.columns)
    table_class = ' report-enrichment-table' if enrichment else ''
    column_definitions = json.dumps(table_column_defs(frame), ensure_ascii=True).replace('<', '\\u003c')
    markup = f'''{css}
<div class="report-data-table report-table-pending{table_class}" data-row-count="{len(frame)}">
<p class="report-table-status" role="status">{len(frame):,} {'rows' if english else '行'} · <span>{waiting}</span></p>
<table id="{table_id}" style="width:100%"{dataset}></table>{embedded}
<script type="module">
(() => {{
 const table = document.getElementById('{table_id}');
 const region = table.parentElement;
 const status = region.querySelector('.report-table-status span');
 let busy = false;
 async function initialize() {{
   if (busy || table.dataset.ready) return;
   busy = true;
   status.textContent = {json.dumps(loading)};
   try {{
     const module = await {runtime};
     const DataTable = module.default;
     let payload;
     if (table.dataset.source) {{
       const response = await fetch(table.dataset.source);
       if (!response.ok) throw new Error('HTTP ' + response.status);
       payload = await response.json();
     }} else payload = JSON.parse(region.querySelector('.report-table-data').textContent);
     const numeric = new Set(payload.numeric);
     const numberRender = {NUMBER_RENDER_JS};
     const geneListRender = {GENE_LIST_RENDER_JS};
     const descriptionRender = {DESCRIPTION_RENDER_JS};
     const text = DataTable.render.text();
     const escapeTitle = value => {{const node=document.createElement('span');node.textContent=value;return node.innerHTML;}};
     const columns = payload.columns.map((title,index) => ({{title:escapeTitle(title),name:title,
       type:numeric.has(index)?'num':'string',
       render:numeric.has(index)?numberRender:text}}));
     payload.columns.forEach((title,index) => {{
       if (title === 'Description') columns[index].render = descriptionRender;
       if (title.toLowerCase() === 'geneid') columns[index].render = geneListRender;
     }});
     const rawExport = {{orthogonal:'export', columns:':visible'}};
     table._reportTable = new DataTable(table, {{data:payload.data,columns,
       columnDefs:{column_definitions},
       deferRender:true, scrollX:true, autoWidth:false, pageLength:10, order:[],
       dom:{json.dumps(TABLE_DOM)},
       buttons:[{{extend:'copy',text:{json.dumps(export_button_text('copy'))},footer:false,exportOptions:rawExport}},
                {{extend:'csv',text:{json.dumps(export_button_text('csv'))},footer:false,exportOptions:rawExport}}],
       language:{json.dumps(locale, ensure_ascii=False)},
       drawCallback:function() {{
         const api=this.api();api.table().node()._reportTable=api;
         const scroll=api.table().container().querySelector('.dt-scroll-body');
         if(scroll) {{
           const hint=()=>scroll.parentElement.classList.toggle('report-scroll-more',scroll.scrollWidth-scroll.clientWidth-scroll.scrollLeft>2);
           if(!scroll._reportScrollHint) {{
             scroll.addEventListener('scroll',hint,{{passive:true}});
             if(window.ResizeObserver) new ResizeObserver(hint).observe(scroll);
             scroll._reportScrollHint=hint;
           }}
           requestAnimationFrame(hint);
           scroll.tabIndex=0;scroll.setAttribute('role','region');
           scroll.setAttribute('aria-label',{json.dumps('Scrollable report data table' if english else '可横向滚动的数据表格')});}}
       }}
     }});
     table.dataset.ready='true';
     region.classList.remove('report-table-pending');
     status.textContent={json.dumps(ready)};
   }} catch(error) {{
     status.textContent={json.dumps(failed)} + ': ' + error.message + ' ';
     const retry=document.createElement('button');retry.type='button';retry.textContent={json.dumps(retry)};
     retry.onclick=initialize;status.append(retry);
   }} finally {{busy=false;}}
 }}
 if ('IntersectionObserver' in window) {{
   const observer=new IntersectionObserver(entries=>{{
     if(entries.some(entry=>entry.isIntersecting)) {{observer.disconnect();initialize();}}
   }},{{rootMargin:'200px'}});
   observer.observe(region);
 }} else initialize();
}})();
</script></div>'''
    from loguru import logger
    logger.info('Compact table: {} rows, {} columns, {} bytes; lazy initialization',
                len(frame), len(frame.columns), len(payload.encode()))
    display(HTML(markup))
