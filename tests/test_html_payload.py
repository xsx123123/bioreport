"""Large offline reports must preserve records while staying below Quarto's string limit."""
import base64
import gzip
import json
import re
import struct

import numpy as np
import pandas as pd
from bs4 import BeautifulSoup

from bioreport.i18n import combine_language_editions
from bioreport.utils import html_table, render_output
from bioreport.utils.html_fonts import report_codepoints
from bioreport.utils.html_payload import columnar_table, packed_text, restored_table, unpacked_text
from omics.rna.analysis.plot_utils import plot_volcano_pvalue


def plot_html(markup):
    return unpacked_text(re.search(r'class="report-plot-data"[^>]*>(.*?)</script>', markup, re.S)[1])


def test_columnar_payload_preserves_float_bits_identifiers_and_missing_values():
    ids = ['00017', '中文基因', '</script><img src=x>', 'G4', 'G5', 'G6', 'G7']
    frame = pd.DataFrame({'ENSEMBL':ids, 'Symbol':ids,
                         'pvalue':[-0., np.nextafter(1., 2.), 1e-300, np.nan, np.inf, -np.inf, 0.],
                         'Count':[2 ** 54 + 1] * 7})
    raw = html_table.compact_payload(frame)
    columnar = columnar_table(raw)
    assert columnar['columnData'][1] == {'kind':'alias', 'column':0}
    restored = restored_table(json.loads(unpacked_text(packed_text(json.dumps(columnar, ensure_ascii=False)))))
    assert restored == raw
    for before, after in zip(raw['data'], restored['data']):
        if isinstance(before[2], float):
            assert struct.pack('<d', before[2]) == struct.pack('<d', after[2])
    assert packed_text('相同数据') == packed_text('相同数据')


def test_large_table_is_packed_before_notebook_output(monkeypatch):
    monkeypatch.delenv('BIOREPORT_SHARED_ASSET_DIR', raising=False)
    monkeypatch.setattr(render_output, 'ensure_table_runtime', lambda:'window.testRuntime')
    shown = []
    monkeypatch.setattr(html_table, 'display', lambda item:shown.append(item.data))
    frame = pd.DataFrame({'ENSEMBL':[f'Gene{i:06}' for i in range(4000)],
                         'pvalue':np.linspace(1e-250, .05, 4000)})
    html_table.show_compact_table(frame)
    soup = BeautifulSoup(shown[0], 'html.parser')
    source = soup.select_one('.report-table-data')
    assert source['data-encoding'] == 'columnar-gzip-base64'
    assert restored_table(json.loads(unpacked_text(source.text))) == html_table.compact_payload(frame)
    assert len(source.text) < len(json.dumps(html_table.compact_payload(frame)))


def test_font_scan_preserves_packed_labels_and_ui_but_excludes_vendor_cmaps():
    html = ('<script data-bioreport-runtime="pdfmake-0.2.7.min.js">龘</script>'
            '<script data-bioreport-runtime="plotly-export.js">锁定</script>'
            '<script data-encoding="gzip-base64">' + packed_text('<p>紫玉参薯</p>') + '</script>')
    points = report_codepoints([html])
    assert set(map(ord, '锁定紫玉参薯')) <= points
    assert ord('龘') not in points


def test_bilingual_payloads_are_shared_once_without_changing_either_record_set(tmp_path):
    payload = packed_text(json.dumps({'gene':'紫玉', 'pvalue':1e-250}))
    paths = []
    for language in ['zh', 'en']:
        path = tmp_path / f'{language}.html'
        path.write_text(f'<html lang="{language}"><script type="application/octet-stream" '
                        f'class="report-table-data" data-encoding="columnar-gzip-base64">{payload}</script></html>')
        paths.append(path)
    output = tmp_path / 'combined.html'
    metrics = combine_language_editions(*paths, output)
    soup = BeautifulSoup(output.read_text(), 'html.parser')
    assert metrics['unique_payloads'] == 1
    shared = soup.select_one('.report-shared-payload')
    assert shared.text == payload
    for language in ['zh','en']:
        edition = gzip.decompress(base64.b64decode(soup.select_one('#edition-' + language).text)).decode()
        reference = BeautifulSoup(edition, 'html.parser').select_one('.report-table-data')
        assert reference['data-payload-ref'] == shared['id']
        assert not reference.text
        assert json.loads(unpacked_text(shared.text)) == {'gene':'紫玉', 'pvalue':1e-250}


def test_volcano_uses_table_source_only_when_all_rows_match(monkeypatch):
    monkeypatch.delenv('BIOREPORT_OUTPUT_FORMAT', raising=False)
    monkeypatch.delenv('BIOREPORT_SHARED_ASSET_DIR', raising=False)
    monkeypatch.setattr(render_output, '_plotly_loaded', False)
    monkeypatch.setattr(render_output, 'ensure_table_runtime', lambda:'window.testRuntime')
    shown, tables = [], []
    monkeypatch.setattr(render_output, 'display', lambda item:shown.append(item.data))
    monkeypatch.setattr(html_table, 'display', lambda item:tables.append(item.data))
    frame = pd.DataFrame({'ENSEMBL':['G1','G2'], 'Symbol':['DUP','DUP'],
                          'log2FoldChange':[2.,-3.], 'pvalue':[1e-200,.0001]})
    html_table.show_compact_table(frame, volcano_comparison='A')
    figure = plot_volcano_pvalue(frame, '', col_logfc='log2FoldChange', col_pval='pvalue', comparison='A')
    original = figure.to_json()
    render_output.show_figure(figure)
    assert 'window.BioReportPlotlyLoader.newPlot(' in plot_html(shown[-1])
    assert figure.to_json() == original
    # A preview/subset table must never replace a complete volcano dataset.
    html_table.show_compact_table(frame.head(1), volcano_comparison='B')
    figure = plot_volcano_pvalue(frame, '', col_logfc='log2FoldChange', col_pval='pvalue', comparison='B')
    render_output.show_figure(figure)
    assert 'window.BioReportPlotlyLoader.newPlot(' not in plot_html(shown[-1])
    # Font data is registered on the page; subsequent plots only carry a key.
    assert 'BioReportPlotlyFonts[' not in shown[-1]


def test_staged_payload_stays_out_of_notebook_and_is_embedded_losslessly(tmp_path, monkeypatch):
    from bioreport.utils.html_payload import payload_markup, embed_payloads
    directory = tmp_path / 'payloads'
    monkeypatch.setenv('BIOREPORT_HTML_PAYLOAD_DIR', str(directory))
    data = packed_text(json.dumps({'label':'参薯基因', 'value':1.234567891e-200, 'rows':list(range(100000))}))
    markup = payload_markup(data, 'report-table-data', 'columnar-gzip-base64')
    assert len(markup) < 300 and data not in markup
    assert set(map(ord,'参薯基因')) <= report_codepoints([markup], payload_directory=directory)
    standalone = tmp_path / 'single.html'
    standalone.write_text('<html><body>' + markup + '</body></html>')
    embed_payloads(standalone, directory)
    soup = BeautifulSoup(standalone.read_text(), 'html.parser')
    reference = soup.select_one('.report-table-data')['data-payload-ref']
    assert soup.select_one('#' + reference).text == data
    # The same staged dataset is shared between two language documents.
    for language in ['zh','en']:
        (tmp_path / f'{language}.html').write_text('<html><body>' + markup + '</body></html>')
    combined = tmp_path / 'combined.html'
    metrics = combine_language_editions(tmp_path / 'zh.html', tmp_path / 'en.html', combined,
                                       payload_directory=directory)
    assert metrics['unique_payloads'] == 1
    assert metrics['shared_payload_bytes'] == len(data)
    assert combined.read_text().count(data) == 1
