import re

import IPython.display as ipython_display
import pandas as pd
import plotly.graph_objects as go
import pytest

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


def test_html_png_download_uses_1000_dpi_equivalent_and_chart_name(monkeypatch):
    captured = {}
    monkeypatch.delenv("BIOREPORT_OUTPUT_FORMAT", raising=False)

    figure = go.Figure(go.Scatter(x=[1, 2], y=[2, 3]))
    figure.update_layout(title="样本 PCA / PC1 vs PC2", width=900, height=600)

    def fake_to_html(*, full_html, include_plotlyjs, config, post_script):
        captured["config"] = config
        captured["post_script"] = post_script
        return '<div id="chart" class="plotly-graph-div" style="height:600px; width:900px;"></div>'

    monkeypatch.setattr(figure, "to_html", fake_to_html)
    monkeypatch.setattr(render_output, "display", lambda item: None)
    render_output.show_figure(figure)

    options = captured["config"]["toImageButtonOptions"]
    assert options["format"] == "png"
    assert options["filename"] == "样本_PCA_-_PC1_vs_PC2"
    assert options["scale"] == pytest.approx(1000 / 96)
    assert 'BioReportPlotlyExport.attach' in captured['post_script'][0]
    assert '"width": 900, "height": 600' in captured['post_script'][0]
    assert figure.layout.width == 900 and figure.layout.height == 600


def test_pdf_output_uses_image_and_bounded_table(monkeypatch, tmp_path):
    shown = []
    monkeypatch.setenv("BIOREPORT_OUTPUT_FORMAT", "pdf")
    monkeypatch.setattr(render_output, "display", shown.append)

    monkeypatch.setenv("BIOREPORT_ASSET_DIR", str(tmp_path))
    render_output.show_figure(go.Figure(go.Scatter(x=[1, 2], y=[2, 3])), caption="测试图")
    render_output.show_table(pd.DataFrame({"gene": [f"G{i}" for i in range(40)]}))

    assert "#report-figure" in shown[0].data
    assert "测试图" in shown[0].data
    assert list(tmp_path.glob("*.svg"))
    assert "G29" in shown[1].data
    assert "G30" not in shown[1].data


def test_html_table_includes_offline_assets(monkeypatch):
    shown = []
    monkeypatch.delenv("BIOREPORT_OUTPUT_FORMAT", raising=False)
    monkeypatch.setattr(ipython_display, "display", shown.append)
    monkeypatch.setattr(render_output, "_itables_loaded", False)

    render_output.show_table(pd.DataFrame({"sample": ["S1"], "value": [8.2]}))

    assert len(shown) == 4
    assert len(shown[1].data) > 100_000
    assert "BioReportHtmlPayload" in shown[2].data
    assert "S1" in shown[3].data
    for item in shown:
        assert not re.search(r'<(?:script|link|img)[^>]+(?:src|href)=[\'"]https?://', item.data)


def test_export_button_presentation_preserves_existing_actions(monkeypatch):
    monkeypatch.delenv('BIOREPORT_OUTPUT_FORMAT', raising=False)
    monkeypatch.delenv('BIOREPORT_SHARED_ASSET_DIR', raising=False)
    monkeypatch.setenv('BIOREPORT_LANGUAGE', 'zh')
    monkeypatch.setattr(render_output, 'ensure_table_runtime', lambda: None)
    captured = {}
    monkeypatch.setattr(render_output, 'show_interactive_table', lambda table, **kwargs: captured.update(kwargs))
    export = {'extend': 'excelHtml5', 'text': '📊 Excel', 'exportOptions': {'columns': [0]}, 'filename': 'original'}
    render_output.show_table(pd.DataFrame({'sample': ['S1']}), buttons=['copy', 'csv', export])
    assert [b['extend'] for b in captured['buttons']] == ['copy', 'csv', 'excelHtml5']
    assert all('<svg ' in b['text'] for b in captured['buttons'])
    assert '复制' in captured['buttons'][0]['text']
    assert captured['buttons'][2]['exportOptions'] == export['exportOptions']
    assert captured['buttons'][2]['filename'] == 'original'
    assert export['text'] == '📊 Excel'
    assert 'report-scroll-more' in str(captured['drawCallback'])
