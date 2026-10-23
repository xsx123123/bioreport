"""Download metadata, dependency staging and the offline PDF byte format."""
import json
from pathlib import Path
import re
import shutil
import subprocess

import plotly.graph_objects as go
import pytest
from pypdf import PdfReader

from bioreport.utils import render_output


ROOT = Path(__file__).resolve().parents[1]


def test_exporter_staged_once_with_shared_runtime(monkeypatch, tmp_path):
    shown = []
    monkeypatch.delenv('BIOREPORT_OUTPUT_FORMAT', raising=False)
    monkeypatch.setenv('BIOREPORT_SHARED_ASSET_DIR', str(tmp_path))
    monkeypatch.setenv('BIOREPORT_SHARED_ASSET_URL', '../assets')
    monkeypatch.setattr(render_output, '_plotly_loaded', False)
    monkeypatch.setattr(render_output, 'display', shown.append)
    figure = go.Figure(go.Bar(x=['A', 'B'], y=[2, 1]))
    render_output.show_figure(figure)
    render_output.show_figure(figure)
    assert len(shown) == 3
    assert '<script src="../assets/plotly-export.js"></script>' in shown[0].data
    assert (tmp_path / 'plotly-export.js').read_bytes() == (ROOT / 'bioreport/assets/js/plotly-export.js').read_bytes()
    assert all('BioReportPlotlyExport.attach' in item.data for item in shown[1:])
    assert not any('plotly-export.js' in item.data for item in shown[1:])


def test_export_settings_escape_script_text_and_keep_layout():
    figure = go.Figure(go.Scatter(x=[1], y=[2]))
    figure.update_layout(title="</script><script>alert('x')</script>", width=800, height=500)
    original = figure.to_json()
    html = render_output._responsive_figure_html(figure, {'toImageButtonOptions': {'width': 1200, 'height': 750}})
    assert '"width": 1200, "height": 750' in html
    initializer = html.split('BioReportPlotlyExport.attach', 1)[1]
    metadata = json.loads(re.search(r', (\{.*?\})\);', initializer)[1])
    assert metadata['filename'] == "alert('x')"
    assert html.count('<script') == 1
    assert figure.to_json() == original


@pytest.mark.parametrize('compressed', [False, True])
def test_pdf_is_a_valid_lossless_single_page_with_selected_dimensions(tmp_path, compressed):
    if not shutil.which('node'):
        pytest.skip('Node is required to exercise the browser PDF encoder')
    path = tmp_path / 'chart.pdf'
    # Expose the actual private encoder in an isolated test VM. The synthetic
    # canvas checks every RGB channel, image size and PDF xref without a browser.
    script = r'''
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[1], 'utf8').replace(
  'window.BioReportPlotlyExport = {attach};', 'window.BioReportPlotlyExport = {attach, imagePdf};');
const sandbox = {window: {CompressionStream: process.argv[3] === 'true' ? CompressionStream : undefined},
  Blob, Response, TextEncoder, Uint8Array, CompressionStream: process.argv[3] === 'true' ? CompressionStream : undefined};
vm.runInNewContext(source, sandbox);
const rgba = new Uint8ClampedArray(320 * 240 * 4);
for (let i = 0; i < rgba.length; i += 4) { rgba[i] = 12; rgba[i+1] = 128; rgba[i+2] = 241; rgba[i+3] = 255; }
const canvas = {width: 320, height: 240, getContext: () => ({getImageData: () => ({data: rgba})})};
sandbox.window.BioReportPlotlyExport.imagePdf(canvas).then(async blob => {
  fs.writeFileSync(process.argv[2], Buffer.from(await blob.arrayBuffer()));
}).catch(error => { console.error(error); process.exitCode = 1; });
'''
    subprocess.run(['node', '-e', script, str(ROOT / 'bioreport/assets/js/plotly-export.js'), str(path),
                    json.dumps(compressed)], check=True, capture_output=True, timeout=30)
    reader = PdfReader(path, strict=True)
    assert len(reader.pages) == 1
    page = reader.pages[0]
    assert tuple(page.mediabox) == (0, 0, 240, 180)
    image = page.images[0].image
    assert image.size == (320, 240)
    assert image.tobytes() == bytes([12, 128, 241]) * (320 * 240)
