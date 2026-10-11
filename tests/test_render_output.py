import re

import IPython.display as ipython_display
import pandas as pd
import plotly.graph_objects as go

from bioreport.utils import render_output


def test_html_figures_embed_plotly_only_once(monkeypatch):
    shown = []
    monkeypatch.delenv("BIOREPORT_OUTPUT_FORMAT", raising=False)
    monkeypatch.setattr(render_output, "display", shown.append)
    monkeypatch.setattr(render_output, "_plotly_loaded", False)
    figure = go.Figure(go.Scatter(x=[1, 2], y=[2, 3]))

    render_output.show_figure(figure)
    render_output.show_figure(figure)

    assert "plotly.js" in shown[0].data
    assert "plotly.js" not in shown[1].data
    assert "<script src=" not in shown[0].data
    assert 'class="plotly-graph-div"' not in shown[0].data
    assert 'class="plotly-graph-div"' in shown[1].data
    assert 'class="plotly-graph-div"' in shown[2].data


def test_pdf_output_uses_image_and_bounded_table(monkeypatch):
    shown = []
    monkeypatch.setenv("BIOREPORT_OUTPUT_FORMAT", "pdf")
    monkeypatch.setattr(render_output, "display", shown.append)

    class Figure:
        def to_image(self, **kwargs):
            assert kwargs == {"format": "png", "scale": 2}
            return b"image bytes"

    render_output.show_figure(Figure())
    render_output.show_table(pd.DataFrame({"gene": [f"G{i}" for i in range(40)]}))

    assert shown[0].data == b"image bytes"
    assert "G29" in shown[1].data
    assert "G30" not in shown[1].data


def test_html_table_includes_offline_assets(monkeypatch):
    shown = []
    monkeypatch.delenv("BIOREPORT_OUTPUT_FORMAT", raising=False)
    monkeypatch.setattr(ipython_display, "display", shown.append)
    monkeypatch.setattr(render_output, "_itables_loaded", False)

    render_output.show_table(pd.DataFrame({"sample": ["S1"], "value": [8.2]}))

    assert len(shown) == 3
    assert len(shown[1].data) > 100_000
    assert "S1" in shown[2].data
    for item in shown:
        assert not re.search(r'<(?:script|link|img)[^>]+(?:src|href)=[\'"]https?://', item.data)
