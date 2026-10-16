"""Format-aware display helpers shared by report modules."""

import os
import re
import json
from pathlib import Path

from IPython.display import HTML, Image, Markdown, display
from itables import init_notebook_mode, show as show_interactive_table
from plotly.offline import get_plotlyjs


_plotly_loaded = False
_itables_loaded = False
_figure_count = 0


def is_pdf() -> bool:
    return os.environ.get("BIOREPORT_OUTPUT_FORMAT") == "pdf"


def show_figure(figure, config=None, caption=None) -> None:
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
            # Typst owns the complete image/caption block and figure numbering.
            display(Markdown("```{=typst}\n#report-figure(" + json.dumps(str(path), ensure_ascii=False)
                             + ", " + json.dumps(label, ensure_ascii=False) + f", {ratio:.5f})\n```"))
    else:
        if not _plotly_loaded:
            # Quarto promotes the output containing plotly.js to a dependency.
            # Emit the library separately so no chart is moved before the report.
            display(HTML(f'<script data-bioreport-dependency="plotly">{get_plotlyjs()}</script>'))
            _plotly_loaded = True
        display(HTML(_responsive_figure_html(figure, config)))


def _responsive_figure_html(figure, config):
    """Render a plotly figure inside an aspect-ratio box.

    Plotly pins the graph div and its drawing size to the layout's pixel
    height while the width follows the (narrower) report column, which
    stretches every chart. The wrapper keeps the figure's designed
    width/height ratio; the design size comes from the layout or, when only
    the height is set there, from the download options the chart functions
    already carry. The pixel sizes are then removed from the serialized
    layout so plotly.js fills the box instead of forcing its own height.
    """
    export_options = (config or {}).get("toImageButtonOptions") or {}
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
    display(Markdown('```{=typst}\n#text(size: 9pt, fill: rgb("#53636a"), '
                     + json.dumps(str(text), ensure_ascii=False) + ")\n```"))


def _breakable(text: str) -> str:
    """Make long tokens wrap in Typst tables: insert zero-width spaces into
    SHA256-length hex runs and any path/hex token longer than a table cell."""
    from .fonts import breakable_hash
    value = str(text)
    return re.sub(r"[0-9A-Fa-f]{16,}", lambda m: breakable_hash(m.group()), value)


def show_print_table(frame, limit=10):
    """Splittable Typst table with repeated headers; no HTML or numeric coercion."""
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
            cells.append(_breakable(text))
        rows.append(cells)
    numeric = [bool(pd.api.types.is_numeric_dtype(frame[c]) or str(c) == '数值' or str(c).lower() in ['pvalue','padj','p.adjust','qvalue']) for c in frame.columns]
    display(Markdown("```{=typst}\n#report-table(" + typst_literal(headers)
                     + ", " + typst_literal(rows) + ", "
                     + typst_literal(numeric) + ")\n```"))


def typst_literal(value):
    if isinstance(value, (list, tuple)):
        return "(" + "".join(typst_literal(item) + "," for item in value) + ")"
    if isinstance(value, bool): return "true" if value else "false"
    return json.dumps(value, ensure_ascii=False)
