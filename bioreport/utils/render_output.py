"""Format-aware display helpers shared by report modules."""

import os
import re
import json
from pathlib import Path
from contextlib import contextmanager
from bioreport.report.recording import record_block

from IPython.display import HTML, Image, Markdown, display
from itables import init_notebook_mode, show as show_interactive_table
from plotly.offline import get_plotlyjs


_plotly_loaded = False
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
    global _plotly_loaded, _figure_count
    if is_pdf():
        if figure is None:
            raise ValueError("Cannot export an empty figure")
        from .print_theme import export_vector, plain, print_panels, UnsupportedTrace
        directory = Path(os.environ.get("BIOREPORT_ASSET_DIR", "pdf-figures"))
        directory.mkdir(parents=True, exist_ok=True)
        import xml.etree.ElementTree as ET
        text = caption or plain(figure.layout.title.text) or "分析图表"
        for panel, detail in print_panels(figure):
            _figure_count += 1
            path = directory / f"figure-{_figure_count:03}.svg"
            try:
                export_vector(panel, path)
            except UnsupportedTrace:
                # Preserve custom/third-party trace support on normal Kaleido hosts.
                path.write_bytes(panel.to_image(format='svg',scale=4))
            root = ET.parse(path).getroot()
            if root.tag.rsplit('}',1)[-1] != 'svg':
                raise ValueError(f'Static exporter did not produce an SVG: {path}')
            viewbox = root.attrib["viewBox"].split()
            ratio = float(viewbox[3]) / float(viewbox[2])
            label = text + (' '+detail+'。' if detail else '')
            from bioreport.report import FigureBlock, LayoutPlanner
            block = LayoutPlanner().plan(FigureBlock(id=f"figure-{_figure_count:03}",
                path=str(path), caption=label, ratio=ratio, content=evidence))
            record_block(block)
            # Typst owns the complete image/caption block and figure numbering.
            expression = ("#report-figure(" + json.dumps(str(path), ensure_ascii=False)
                          + ", " + json.dumps(label, ensure_ascii=False)
                          + f", {ratio:.5f}, preferred-height: {block.preferred_height:.2f}mm, id: " + typst_literal(block.id) + ")")
            if _figure_group is not None:
                _figure_group.append((block, expression))
            else:
                display(Markdown("```{=typst}\n" + expression + "\n```"))

    else:
        if not _plotly_loaded:
            # Quarto promotes the output containing plotly.js to a dependency.
            # Emit the library separately so no chart is moved before the report.
            display(HTML(f'<script data-bioreport-dependency="plotly">{get_plotlyjs()}</script>'))
            _plotly_loaded = True
        display(HTML(_responsive_figure_html(figure, config, caption=caption)))


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
            record_block(group)
            expressions = ','.join('['+expression+']' for _, expression in collected)
            display(Markdown('```{=typst}\n#report-figure-group(('
                             + expressions + ',), columns: ' + str(group.columns) + ')\n```'))
    finally:
        _figure_group = None


def _plotly_filename(figure, caption=None):
    """Derive a stable PNG name from the visible chart title."""
    title = getattr(getattr(figure, "layout", None), "title", None)
    value = getattr(title, "text", None) if title is not None else None
    value = value or caption or "BioReport Figure"
    value = re.sub(r"<[^>]+>", "", str(value))
    value = value.split("<br>", 1)[0].strip()
    value = re.sub(r"[\\/:*?\"<>|]+", "-", value)
    value = re.sub(r"\s+", "_", value).strip("._-")
    return value or "BioReport_Figure"


def _html_plotly_config(figure, config=None, caption=None):
    """Apply one PNG download policy to every HTML Plotly chart."""
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
    width = figure.layout.width or export_options.get("width")
    height = figure.layout.height or export_options.get("height")
    saved_width, saved_height = figure.layout.width, figure.layout.height
    figure.layout.width = None
    figure.layout.height = None
    try:
        html = figure.to_html(full_html=False, include_plotlyjs=False, config=config)
    finally:
        figure.layout.width = saved_width
        figure.layout.height = saved_height
    if not (width and height):
        return html
    html = re.sub(
        r'(<div id="[^"]*" class="plotly-graph-div" style=")height:[^;]+; width:[^;]+;',
        r"\1position:absolute; top:0; left:0; height:100%; width:100%;",
        html,
        count=1,
    )
    return (f'<div class="report-plot" style="position:relative; width:100%; '
            f'aspect-ratio: {width} / {height};">{html}</div>')


def show_table(table, **kwargs) -> None:
    global _itables_loaded
    if is_pdf():
        frame = table.data if hasattr(table, "data") else table
        show_print_table(frame, limit=kwargs.pop("limit", 30))
    else:
        if not _itables_loaded:
            init_notebook_mode(all_interactive=False, connected=False)
            _itables_loaded = True
        show_interactive_table(table, connected=False, **kwargs)


def typst_note(text):
    expression = ('#text(size: 9pt, fill: rgb("#53636a"), '
                  + json.dumps(str(text), ensure_ascii=False) + ')')
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
    table_function = "report-sha256-table" if (evidence or {}).get('kind') == 'sha256' else "report-table"
    expression = ("#" + table_function + "(" + typst_literal(headers)
                  + ", " + typst_literal(rows) + ", " + typst_literal(numeric)
                  + ", caption: " + typst_literal(caption or "数据概览")
                  + ", keep-together: " + typst_literal(block.keep_together)
                  + (", note: " + typst_literal(note) if note else "")
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
                         + typst_literal(block.content) + ')\n```'))
    else:
        import html
        display(HTML('<dl class="report-metrics">' + ''.join(
            f'<div><dt>{html.escape(str(label))}</dt><dd>{html.escape(str(value))}</dd></div>'
            for label, value in block.content) + '</dl>'))
