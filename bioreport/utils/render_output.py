"""Format-aware display helpers shared by report modules."""

import os
import re
import json
import shutil
from pathlib import Path
from contextlib import contextmanager
from html import escape as escape_html
from loguru import logger
from bioreport.report.recording import record_block
from bioreport.i18n import translate, language

from IPython.display import HTML, Image, Markdown, display
from itables import init_notebook_mode, show as show_interactive_table
from .plotly_runtime import selected_runtime, supports_cartesian


_plotly_loaded = False
_plotly_bundle = None
_plotly_trace_types = set()
_itables_loaded = False
_figure_count = 0
_table_count = 0
_figure_group = None

# Plotly's browser exporter exposes ``scale`` rather than a DPI setting.
# Plotly renders CSS pixels at 96 DPI, so this scale produces PNG dimensions
# equivalent to 1000 DPI for the figure's configured width and height.
DEFAULT_PNG_DPI = 1000
PLOTLY_CSS_DPI = 96


def is_pdf() -> bool:
    return os.environ.get("BIOREPORT_OUTPUT_FORMAT") == "pdf"


def show_figure(figure, config=None, caption=None, *, evidence=None) -> None:
    global _plotly_loaded, _plotly_bundle, _figure_count
    if language() == "en":
        from bioreport.i18n import localize_figure
        figure = localize_figure(figure)
    if is_pdf():
        if figure is None:
            raise ValueError("Cannot export an empty figure")
        from .print_theme import export_vector, plain, print_panels, UnsupportedTrace
        directory = Path(os.environ.get("BIOREPORT_ASSET_DIR", "pdf-figures"))
        directory.mkdir(parents=True, exist_ok=True)
        text = caption or plain(figure.layout.title.text) or "分析图表"
        for panel, detail in print_panels(figure):
            _figure_count += 1
            path = directory / f"figure-{_figure_count:03}.svg"
            try:
                export_vector(panel, path)
            except UnsupportedTrace:
                # Preserve custom/third-party trace support on normal Kaleido hosts.
                path.write_bytes(panel.to_image(format='svg',scale=4))
            _emit_pdf_figure(path, text, evidence, detail)

    else:
        if not _plotly_loaded:
            _plotly_trace_types.clear()
        encountered = {trace.type for trace in figure.data}
        if encountered - _plotly_trace_types:
            _plotly_trace_types.update(encountered)
            logger.info('HTML Plotly trace inventory: {}', ', '.join(sorted(_plotly_trace_types)))
        if not _plotly_loaded or (_plotly_bundle == 'cartesian' and not supports_cartesian(figure)):
            runtime_source, _plotly_bundle, runtime_name = selected_runtime(figure, force_full=_plotly_loaded)
            # Quarto promotes the output containing plotly.js to a dependency.
            # Emit the library separately so no chart is moved before the report.
            shared = os.environ.get('BIOREPORT_SHARED_ASSET_DIR')
            if shared:
                directory = Path(shared)
                directory.mkdir(parents=True, exist_ok=True)
                runtime = directory / runtime_name
                if not runtime.exists():
                    runtime.write_text(runtime_source, encoding='utf-8')
                url = os.environ['BIOREPORT_SHARED_ASSET_URL']
                dependency = f'<script data-bioreport-dependency="plotly" src="{url}/{runtime_name}"></script>'
            else:
                dependency = f'<script data-bioreport-dependency="plotly">{runtime_source}</script>'
            # Keep export controls with the runtime dependency, so standalone
            # and website reports both work without a network connection.
            exporter = Path(__file__).resolve().parents[1] / 'assets/js/plotly-export.js'
            if shared:
                shutil.copyfile(exporter, directory / exporter.name)
                export_html = f'<script src="{escape_html(url, quote=True)}/{exporter.name}"></script>'
            else:
                export_html = '<script>' + exporter.read_text(encoding='utf-8') + '</script>'
            display(HTML(dependency + export_html))
            _plotly_loaded = True
        display(HTML(_responsive_figure_html(figure, config, caption=caption)))
        from .asset_audit import record_asset
        record_asset({'kind':'plotly','language':language(),
                      'traces':sorted(encountered),'bundle':_plotly_bundle})


def _emit_pdf_figure(path, caption, evidence, detail=''):
    import xml.etree.ElementTree as ET
    from bioreport.report import FigureBlock, LayoutPlanner
    root = ET.parse(path).getroot()
    if root.tag.rsplit('}', 1)[-1] != 'svg':
        raise ValueError(f'Static exporter did not produce an SVG: {path}')
    viewbox = root.attrib['viewBox'].split()
    ratio = float(viewbox[3]) / float(viewbox[2])
    label = caption + (' ' + detail + '。' if detail else '')
    block = LayoutPlanner().plan(FigureBlock(id=f'figure-{_figure_count:03}',
        path=str(path), caption=label, ratio=ratio, content=evidence))
    record_block(block)
    expression = ('#report-figure(' + json.dumps(str(path), ensure_ascii=False)
                  + ', ' + json.dumps(translate(label), ensure_ascii=False)
                  + f', {ratio:.5f}, preferred-height: {block.preferred_height:.2f}mm, id: '
                  + typst_literal(block.id) + ')')
    if _figure_group is not None:
        _figure_group.append((block, expression))
    else:
        display(Markdown('```{=typst}\n' + expression + '\n```'))


def show_prepared_figure(source, caption, *, evidence=None, detail=''):
    """Number and emit a worker-produced SVG only in the owning process."""
    global _figure_count
    if not is_pdf():
        raise ValueError('Prepared SVG figures require PDF output')
    directory = Path(os.environ.get('BIOREPORT_ASSET_DIR', 'pdf-figures'))
    directory.mkdir(parents=True, exist_ok=True)
    _figure_count += 1
    path = directory / f'figure-{_figure_count:03}.svg'
    shutil.copyfile(source, path)
    _emit_pdf_figure(path, caption, evidence, detail)


@contextmanager
def figure_group(block_id, columns=1):
    """Keep related PDF figures together; HTML keeps its interactive flow."""
    global _figure_group
    if not is_pdf():
        yield
        return
    if _figure_group is not None:
        raise ValueError('Nested figure groups are not supported')
    from bioreport.report import FigureGroup, LayoutPlanner
    collected = []
    _figure_group = collected
    try:
        yield
    except BaseException:
        raise
    else:
        if collected:
            if all(block.type == 'paragraph' for block, _ in collected):
                for _, expression in collected:
                    display(Markdown('```{=typst}\n' + expression + '\n```'))
                return
            group = LayoutPlanner().plan(FigureGroup(id=block_id,
                figures=[block for block, _ in collected if block.type == "figure"],
                tables=[block for block, _ in collected if block.type == "table"], columns=columns))
            # Fixed figure heights and table cell padding give a strict lower
            # bound. Oversized groups need no additional nested Typst measure
            # pass (which otherwise also measures every contained table).
            heights = []
            for block, _ in collected:
                if block.type == 'figure':
                    heights.append(max(0., block.preferred_height - .01))
                elif block.type == 'table':
                    heights.append((len(block.rows) + 1) * 10 * 25.4 / 72)
                else:
                    heights.append(0.)
            row_heights = [max(heights[i:i + group.columns])
                           for i in range(0, len(heights), group.columns)]
            group.minimum_height = sum(row_heights) + 4 * (len(row_heights) - 1)
            record_block(group)
            expressions = ','.join('['+expression+']' for _, expression in collected)
            display(Markdown('```{=typst}\n#report-figure-group(('
                             + expressions + ',), columns: ' + str(group.columns)
                             + f', minimum-height: {group.minimum_height:.2f}mm)\n```'))
    finally:
        _figure_group = None


def _plotly_filename(figure, caption=None):
    """Derive a stable download name from the visible chart title."""
    title = getattr(getattr(figure, "layout", None), "title", None)
    value = getattr(title, "text", None) if title is not None else None
    value = value or caption or "BioReport Figure"
    value = re.sub(r"<[^>]+>", "", str(value))
    value = value.split("<br>", 1)[0].strip()
    value = re.sub(r"[\\/:*?\"<>|]+", "-", value)
    value = re.sub(r"\s+", "_", value).strip("._-")
    return value or "BioReport_Figure"


def _html_plotly_config(figure, config=None, caption=None):
    """Keep native PNG defaults and supply metadata for the export dialog."""
    normalized = dict(config or {})
    options = dict(normalized.get("toImageButtonOptions") or {})
    dpi = float(normalized.pop("png_dpi", DEFAULT_PNG_DPI))
    if dpi <= 0:
        raise ValueError("png_dpi must be greater than zero")
    options.update({
        "format": "png",
        "filename": _plotly_filename(figure, caption),
        "scale": dpi / PLOTLY_CSS_DPI,
    })
    # Keep explicit export dimensions, falling back to the figure layout.
    options.setdefault("width", figure.layout.width)
    options.setdefault("height", figure.layout.height)
    options = {key: value for key, value in options.items() if value is not None}
    normalized["toImageButtonOptions"] = options
    return normalized


def _responsive_figure_html(figure, config, caption=None):
    """Render a plotly figure inside an aspect-ratio box.

    Plotly pins the graph div and its drawing size to the layout's pixel
    height while the width follows the (narrower) report column, which
    stretches every chart. The wrapper keeps the figure's designed
    width/height ratio; the design size comes from the layout or, when only
    the height is set there, from the download options the chart functions
    already carry. The pixel sizes are then removed from the serialized
    layout so plotly.js fills the box instead of forcing its own height.
    """
    config = _html_plotly_config(figure, config, caption=caption)
    export_options = config.get("toImageButtonOptions") or {}
    width = figure.layout.width or export_options.get("width") or 700
    height = figure.layout.height or export_options.get("height") or 450
    saved_width, saved_height = figure.layout.width, figure.layout.height
    figure.layout.width = None
    figure.layout.height = None
    try:
        options = dict(full_html=False, include_plotlyjs=False, config=config)
        export_settings = json.dumps({
            'width': export_options.get('width') or width,
            'height': export_options.get('height') or height,
            'filename': export_options['filename'],
            'language': language(),
        }, ensure_ascii=True).replace('<', '\\u003c')
        scripts = ["window.BioReportPlotlyExport.attach(document.getElementById('{plot_id}'), "
                   + export_settings + ');']
        if isinstance(figure.layout.meta, dict) and figure.layout.meta.get('bioreport_responsive_pca'):
            scripts.append(_responsive_pca_script(width, height))
            config['responsive'] = False
        elif isinstance(figure.layout.meta, dict) and figure.layout.meta.get('enrichment'):
            scripts.append("""(() => {
              const chart = document.getElementById('{plot_id}');
              const region = chart.closest('.report-chart-scroll');
              if (!region) return;
              const hint = region.querySelector('.report-chart-scroll-hint');
              new ResizeObserver(() => {hint.hidden = region.scrollWidth <= region.clientWidth + 1;}).observe(region);
            })();""")
        options['post_script'] = scripts
        html = figure.to_html(**options)
    finally:
        figure.layout.width = saved_width
        figure.layout.height = saved_height
    html = re.sub(
        r'(<div id="[^"]*" class="plotly-graph-div" style=")height:[^;]+; width:[^;]+;',
        r"\1position:absolute; top:0; left:0; height:100%; width:100%;",
        html,
        count=1,
    )
    top = figure.layout.margin.t if figure.layout.margin.t is not None else 100
    bottom = figure.layout.margin.b if figure.layout.margin.b is not None else 80
    minimum_height = max(280, int(top + bottom + 160))
    enrichment = isinstance(figure.layout.meta, dict) and figure.layout.meta.get('enrichment')
    minimum_width = f'min-width: {width}px; ' if enrichment else ''
    result = (f'<div class="report-plot" style="position:relative; width:100%; '
              f'{minimum_width}min-height: {minimum_height}px; aspect-ratio: {width} / {height};">{html}</div>')
    if enrichment:
        title = re.sub(r'<[^>]*>', ' ', str(figure.layout.title.text or 'Enrichment chart')).strip()
        hint = '横向滚动查看完整图表' if language() == 'zh' else 'Scroll horizontally to view the complete chart'
        return (f'<div class="report-chart-scroll" tabindex="0" role="region" aria-label="{escape_html(title, quote=True)}">'
                f'<p class="report-chart-scroll-hint" hidden>{hint}</p>{result}</div>')
    return result


def _responsive_pca_script(width, height):
    """Reflow both PCA views without recalculating or duplicating their data."""
    return r'''(() => {
      const chart = document.getElementById('{plot_id}');
      const wrapper = chart.closest('.report-plot');
      if (!wrapper) return;
      const original = JSON.parse(JSON.stringify(chart.layout));
      let lastKey, running = false, pending = false;
      const update = () => {
        if (running) { pending = true; return; }
        const initial = wrapper.getBoundingClientRect();
        if (initial.width < 100 || initial.height < 100) return;
        const compact = initial.width < 640;
        wrapper.style.aspectRatio = compact ? '1 / 1.9' : 'WIDTH / HEIGHT';
        const box = wrapper.getBoundingClientRect();
        const width = Math.round(box.width), height = Math.round(box.height);
        const key = width + ':' + height + ':' + compact;
        if (key === lastKey) return;
        lastKey = key;
        // Fixed positive drawing dimensions keep queued relayouts valid even
        // if routing hides this page while Plotly is completing its work.
        const patch = {width, height, autosize:false};
        for (const axis of ['xaxis','xaxis2','yaxis','yaxis2']) {
          patch[axis + '.domain'] = original[axis].domain;
        }
        patch.annotations = JSON.parse(JSON.stringify(original.annotations || []));
        patch['legend.y'] = original.legend.y;
        if (compact) {
          patch['xaxis.domain'] = [0,1];
          patch['xaxis2.domain'] = [0,1];
          patch['yaxis.domain'] = [.60,1];
          patch['yaxis2.domain'] = [0,.40];
          patch.annotations.forEach((label, index) => {
            label.x = .5; label.y = index === 0 ? 1.04 : .44;
            label.font = Object.assign({}, label.font, {size:13});
          });
          patch['legend.y'] = 1.13;
        }
        running = true;
        Plotly.relayout(chart, patch).finally(() => {
          running = false;
          if (pending) { pending = false; requestAnimationFrame(update); }
        });
      };
      new ResizeObserver(update).observe(wrapper);
      update();
    })();'''.replace('WIDTH',str(width or 1000)).replace('HEIGHT',str(height or 500))


def show_table(table, **kwargs) -> None:
    global _itables_loaded
    if is_pdf():
        frame = table.data if hasattr(table, "data") else table
        show_print_table(frame, limit=kwargs.pop("limit", 30))
    else:
        # Use DataTables' native scrolling rather than clipping wide matrices.
        kwargs.setdefault('scrollX', True)
        kwargs['autoWidth'] = False
        kwargs.setdefault('pageLength', 10)
        from .html_table import export_button_text, table_column_defs, NUMBER_RENDER_JS, TABLE_DOM
        from itables import JavascriptFunction
        from itables.javascript import _evaluate_show_index
        frame = table.data if hasattr(table, 'data') else table
        offset = len(frame.index.names) if _evaluate_show_index(table, kwargs.get('showIndex', 'auto')) else 0
        definitions = table_column_defs(frame, offset)
        kwargs['dom'] = TABLE_DOM
        if not hasattr(table, 'data'):
            for definition, dtype in zip(definitions, frame.dtypes):
                if dtype.kind in 'iuf':
                    definition['render'] = JavascriptFunction(NUMBER_RENDER_JS)
        kwargs['columnDefs'] = definitions + list(kwargs.get('columnDefs') or [])
        buttons = []
        for button in kwargs.get('buttons', ['copy', 'csv']):
            action = {'extend': button} if isinstance(button, str) else dict(button)
            kind = action.get('extend', '').removesuffix('Html5')
            if kind in {'copy', 'csv', 'excel'}:
                action['text'] = export_button_text(kind)
                if any(definition.get('visible') is False for definition in definitions):
                    action['exportOptions'] = {**action.get('exportOptions', {}), 'columns': ':visible'}
            buttons.append(action)
        kwargs['buttons'] = buttons
        kwargs.setdefault('drawCallback', JavascriptFunction("""function() {
            const api = this.api();
            api.table().node()._reportTable = api;
            const scroll = api.table().container().querySelector('.dt-scroll-body, .dataTables_scrollBody');
            if (scroll) {
                if (!scroll._reportScrollHint) {
                    const hint = () => scroll.parentElement.classList.toggle('report-scroll-more', scroll.scrollWidth - scroll.clientWidth - scroll.scrollLeft > 2);
                    scroll.addEventListener('scroll', hint, {passive:true});
                    if (window.ResizeObserver) new ResizeObserver(hint).observe(scroll);
                    scroll._reportScrollHint = hint;
                }
                requestAnimationFrame(scroll._reportScrollHint);
                scroll.tabIndex = 0;
                scroll.setAttribute('role', 'region');
                scroll.setAttribute('aria-label', 'Scrollable report data table');
            }
        }"""))
        shared = os.environ.get('BIOREPORT_SHARED_ASSET_DIR')
        if shared:
            from .html_table import stage_table_runtime
            stage_table_runtime()
            show_interactive_table(table, connected=True,
                dt_url=os.environ['BIOREPORT_SHARED_ASSET_URL'] + '/dt_bundle.js', **kwargs)
            return
        ensure_table_runtime()
        show_interactive_table(table, connected=False, **kwargs)


def ensure_table_runtime():
    """Share ITables' existing offline module with native lazy DataTables."""
    global _itables_loaded
    if not _itables_loaded:
        init_notebook_mode(all_interactive=False, connected=False)
        _itables_loaded = True
    from itables.javascript import _ITABLES_UNDERSCORE_VERSION
    return 'window.' + _ITABLES_UNDERSCORE_VERSION


def typst_note(text):
    expression = ('#text(size: 9pt, fill: rgb("#53636a"), '
                  + json.dumps(translate(str(text)), ensure_ascii=False) + ')')
    if _figure_group is not None:
        from bioreport.report import Paragraph
        _figure_group.append((Paragraph(id='group-note', content=str(text)), expression))
    else:
        display(Markdown('```{=typst}\n' + expression + '\n```'))


def _breakable(text: str) -> str:
    """Make long tokens wrap in Typst tables: insert zero-width spaces into
    SHA256-length hex runs and any path/hex token longer than a table cell."""
    from .fonts import breakable_hash
    value = str(text)
    return re.sub(r"[0-9A-Fa-f]{16,}", lambda m: breakable_hash(m.group()), value)


def show_print_table(frame, limit=10, *, block_id="table", allow_split=False, evidence=None, note=None, caption=None):
    """Render a planned semantic table without changing input numeric values."""
    global _table_count
    _table_count += 1
    block_id = f"{block_id}-{_table_count}"
    import pandas as pd
    import numpy as np
    from decimal import Decimal
    if limit is not None: frame = frame.head(limit)
    headers = list(map(str, frame.columns))
    rows = []
    for _, row in frame.iterrows():
        cells = []
        for column, value in row.items():
            key = str(column).lower()
            if pd.isna(value): text = "NA"
            elif key in ["pvalue", "padj", "p.adjust", "qvalue"]:
                probability = Decimal(str(value))
                text = "0 (输入)" if probability == 0 else f"{probability:.2e}"
            elif isinstance(value, (int, float, np.number)):
                if isinstance(value, (int, np.integer)): text = str(value)
                else: text = f"{value:.2f}"
            else: text = str(value)
            if (evidence or {}).get('kind') == 'sha256' and key == 'sha256':
                from .fonts import breakable_hash
                cells.append(breakable_hash(text))
            else:
                cells.append(_breakable(text))
        rows.append(cells)
    numeric = [bool(pd.api.types.is_numeric_dtype(frame[c]) or str(c) == '数值' or str(c).lower() in ['pvalue','padj','p.adjust','qvalue']) for c in frame.columns]
    from bioreport.report import TableBlock, LayoutPlanner
    block = LayoutPlanner().plan(TableBlock(id=block_id, caption=caption or "数据概览", headers=headers, rows=rows,
                                            numeric=numeric, allow_split=allow_split, content=evidence))
    record_block(block)
    visible_headers = [translate(h) for h in headers]
    visible_rows = [list(row) for row in rows]
    # Only generated description/status columns are localized; identifiers,
    # expression values, source paths and hashes remain verbatim.
    for i, header in enumerate(headers):
        if header in ('项目', '指标', '统计口径', '是否在常见范围', '常见参考范围', 'Function'):
            for row in visible_rows:
                row[i] = translate(row[i])
    table_function = "report-sha256-table" if (evidence or {}).get('kind') == 'sha256' else "report-table"
    expression = ("#" + table_function + "(" + typst_literal(visible_headers)
                  + ", " + typst_literal(visible_rows) + ", " + typst_literal(numeric)
                  + ", caption: " + typst_literal(translate(caption or "数据概览"))
                  + ", keep-together: " + typst_literal(block.keep_together)
                  + (", note: " + typst_literal(translate(note)) if note else "")
                  + ", id: " + typst_literal(block.id) + ")")
    if _figure_group is not None:
        _figure_group.append((block, expression))
    else:
        display(Markdown("```{=typst}\n" + expression + "\n```"))


def typst_literal(value):
    if isinstance(value, (list, tuple)):
        return "(" + "".join(typst_literal(item) + "," for item in value) + ")"
    if isinstance(value, bool): return "true" if value else "false"
    return json.dumps(value, ensure_ascii=False)


def show_metric_grid(metrics, *, block_id='metrics'):
    from bioreport.report import MetricGrid, LayoutPlanner
    block = LayoutPlanner().plan(MetricGrid(id=block_id, content=list(metrics)))
    record_block(block)
    if is_pdf():
        display(Markdown('```{=typst}\n#report-metrics('
                         + typst_literal([(translate(label), value) for label, value in block.content]) + ')\n```'))
    else:
        import html
        display(HTML('<dl class="report-metrics">' + ''.join(
            f'<div><dt>{html.escape(str(label))}</dt><dd>{html.escape(str(value))}</dd></div>'
            for label, value in block.content) + '</dl>'))
