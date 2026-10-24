"""Download metadata, dependency staging and the offline PDF byte format."""
import json
from io import BytesIO
from pathlib import Path
import re
import shutil
import subprocess
import struct

import plotly.graph_objects as go
import pytest
from pypdf import PdfReader
from PIL import Image

from bioreport.utils import render_output


ROOT = Path(__file__).resolve().parents[1]


def test_pdf_runtime_exposes_private_global_with_requirejs():
    if not shutil.which('node'):
        pytest.skip('Node is required to exercise browser runtime loading')
    script = r'''
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
let registrations = 0;
const define = () => { registrations++; };
define.amd = {};
const existingPdfMake = {host: true};
const sandbox = {define, pdfMake: existingPdfMake, console, setTimeout, clearTimeout,
  TextEncoder, TextDecoder, Uint8Array, ArrayBuffer, navigator: {userAgent: 'Node'}};
sandbox.window = sandbox;
sandbox.self = sandbox;
vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), sandbox);
assert.equal(typeof sandbox.BioReportPdfMake?.createPdf, 'function');
assert.equal(registrations, 0, 'The report runtime must not register an anonymous AMD module');
assert.equal(sandbox.define, define);
assert.equal(sandbox.pdfMake, existingPdfMake);
'''
    subprocess.run(['node', '-e', script, str(ROOT / 'bioreport/assets/js/pdfmake-0.2.7.min.js')],
                   check=True, capture_output=True, timeout=30)


@pytest.mark.parametrize('initial_dpi', [None, 96, 300])
def test_png_density_is_1000_dpi_without_duplicate_chunks_or_pixel_changes(tmp_path, initial_dpi):
    if not shutil.which('node'):
        pytest.skip('Node is required to exercise PNG density encoding')
    path = tmp_path / 'density.png'
    original = Image.new('RGB', (32, 24), (12, 128, 241))
    original.save(path, **({'dpi': (initial_dpi, initial_dpi)} if initial_dpi else {}))
    script = r'''
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[1], 'utf8').replace(
  'window.BioReportPlotlyExport = {attach};', 'window.BioReportPlotlyExport = {withDpi};');
const sandbox = {window: {}, Blob, Uint8Array, Uint32Array, DataView};
vm.runInNewContext(source, sandbox);
sandbox.window.BioReportPlotlyExport.withDpi(new Blob([fs.readFileSync(process.argv[2])]), 1000)
  .then(async blob => fs.writeFileSync(process.argv[2], Buffer.from(await blob.arrayBuffer())))
  .catch(error => { console.error(error); process.exitCode = 1; });
'''
    subprocess.run(['node', '-e', script, str(ROOT / 'bioreport/assets/js/plotly-export.js'), str(path)],
                   check=True, capture_output=True, timeout=30)
    data = path.read_bytes()
    offset, density_chunks = 8, 0
    while offset < len(data):
        length = struct.unpack_from('>I', data, offset)[0]
        density_chunks += data[offset + 4:offset + 8] == b'pHYs'
        offset += length + 12
    assert density_chunks == 1
    with Image.open(BytesIO(data)) as result:
        assert result.info['dpi'] == pytest.approx((1000, 1000), abs=.02)
        result.verify()
    with Image.open(BytesIO(data)) as result:
        assert result.size == original.size
        assert result.tobytes() == original.tobytes()


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
    assert (tmp_path / 'pdfmake-0.2.7.min.js').read_bytes() == (ROOT / 'bioreport/assets/js/pdfmake-0.2.7.min.js').read_bytes()
    assert shown[0].data.index('pdfmake-0.2.7.min.js') < shown[0].data.index('plotly-export.js')
    from bioreport.utils.html_payload import unpacked_text
    for item in shown[1:]:
        packed = re.search(r'class="report-plot-data"[^>]*>(.*?)</script>', item.data, re.S)[1]
        assert 'BioReportPlotlyExport.attach' in unpacked_text(packed)
    assert not any('plotly-export.js' in item.data for item in shown[1:])
    assert not any('pdfmake-0.2.7.min.js' in item.data for item in shown[1:])


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


@pytest.mark.parametrize('subset', [False, True])
def test_pdf_preserves_vectors_and_embeds_searchable_chinese(tmp_path, subset):
    if not shutil.which('node'):
        pytest.skip('Node is required to exercise the browser PDF encoder')
    from bioreport.utils.fonts import font_dir
    font = (font_dir() / 'HarmonyOS_Sans_SC/HarmonyOS_Sans_SC_Regular.ttf').read_bytes()
    if subset:
        from bioreport.utils.pdf_export_fonts import _font_data
        import base64
        font = base64.b64decode(_font_data('HarmonyOS_Sans_SC/HarmonyOS_Sans_SC_Regular.ttf', '样本图表 ABC123'))
    font_path = tmp_path / 'font.ttf'
    font_path.write_bytes(font)
    path = tmp_path / 'chart.pdf'
    script = r'''
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[1], 'utf8').replace(
  'window.BioReportPlotlyExport = {attach};', 'window.BioReportPlotlyExport = {encodeSvgPdf};');
const sandbox = {window: {BioReportPdfMake: require(process.argv[2])}, Blob};
vm.runInNewContext(source, sandbox);
const font = fs.readFileSync(process.argv[3]).toString('base64');
const fonts = {Report: {normal: 'font', bold: 'font', italics: 'font', bolditalics: 'font'}};
const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="240">' +
  '<path d="M10 180 L150 40 L300 100" fill="none" stroke="blue" stroke-width="2"/>' +
  '<text x="20" y="30" font-family="Report" font-size="18">样本图表 ABC123</text></svg>';
sandbox.window.BioReportPlotlyExport.encodeSvgPdf(svg, 320, 240, fonts, {font})
  .then(async blob => fs.writeFileSync(process.argv[4], Buffer.from(await blob.arrayBuffer())))
  .catch(error => { console.error(error); process.exitCode = 1; });
'''
    subprocess.run(['node', '-e', script, str(ROOT / 'bioreport/assets/js/plotly-export.js'),
                    str(ROOT / 'bioreport/assets/js/pdfmake-0.2.7.min.js'), str(font_path), str(path)],
                   check=True, capture_output=True, timeout=30)
    reader = PdfReader(path, strict=True)
    assert len(reader.pages) == 1
    page = reader.pages[0]
    assert tuple(page.mediabox) == (0, 0, 240, 180)
    assert not list(page.images), 'A vector chart must not become a page-sized bitmap'
    assert '样本图表 ABC123' in page.extract_text()
    assert b'150 40 l' in page.get_contents().get_data()
    for font_ref in page['/Resources']['/Font'].values():
        font = font_ref.get_object()['/DescendantFonts'][0].get_object()
        assert '/FontFile2' in font['/FontDescriptor'], 'PDF fonts must be embedded'
    # A searchable text layer alone is insufficient: glyph outlines must draw.
    import pypdfium2 as pdfium
    import numpy as np
    with pdfium.PdfDocument(path) as pdf:
        image = pdf[0].render(scale=96 / 72).to_pil().convert('L')
        assert (np.asarray(image.crop((10, 5, 280, 35))) < 200).sum() > 100
