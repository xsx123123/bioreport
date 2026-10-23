"""Preserve scientific marks and layout evidence while bounding print costs."""
import base64
from io import BytesIO
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd
from PIL import Image
import pytest

from bioreport.report.validation import query_layout, validate_observations
from bioreport.utils.print_theme import export_vector
from bioreport.utils.render_recovery import preserve_failed_render
from omics.rna.analysis.plot_utils import plot_volcano_pvalue

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('count,rasterized', [(12, False), (1600, True)])
def test_scatter_export_keeps_every_point_and_vector_annotations(tmp_path, monkeypatch, count, rasterized):
    import matplotlib.figure
    from matplotlib.collections import PathCollection
    saved = []
    original = matplotlib.figure.Figure.savefig

    def save(figure, *args, **kwargs):
        saved.append(figure)
        return original(figure, *args, **kwargs)

    monkeypatch.setattr(matplotlib.figure.Figure, 'savefig', save)
    frame = pd.DataFrame({'Symbol': [f'Gene_{i}' for i in range(count)],
                          'log2FoldChange': np.linspace(-5, 5, count),
                          'pvalue': np.logspace(-20, -1, count)})
    figure = plot_volcano_pvalue(frame, '', col_logfc='log2FoldChange', col_pval='pvalue',
                                fc_cutoff=1, pval_cutoff=.05, annotate_top=5)
    before = figure.to_json()
    path = tmp_path / 'volcano.svg'
    export_vector(figure, path)
    axis = saved[0].axes[0]
    marks = [item for item in axis.collections if isinstance(item, PathCollection)]
    traces = [trace for trace in figure.data if trace.type == 'scatter' and 'lines' not in trace.mode]
    assert sum(len(item.get_offsets()) for item in marks) == count
    for mark, trace in zip(marks, traces):
        np.testing.assert_allclose(mark.get_offsets(), np.column_stack((trace.x, trace.y)))
        assert mark.get_rasterized() is rasterized
    assert axis.texts and all(not item.get_rasterized() for item in axis.texts)
    assert axis.lines and all(not item.get_rasterized() for item in axis.lines)
    assert figure.to_json() == before
    svg = ET.parse(path).getroot()
    images = list(svg.iter('{http://www.w3.org/2000/svg}image'))
    assert bool(images) is rasterized
    if rasterized:
        png = base64.b64decode(images[0].get('{http://www.w3.org/1999/xlink}href').split(',', 1)[1])
        assert Image.open(BytesIO(png)).width > 1500
        assert len(list(svg.iter())) < 2000


def test_failed_project_preserves_assets_and_can_compile_without_python(tmp_path):
    staging = tmp_path / 'temporary' / 'templates'
    (staging / 'qmd/pdf-figures').mkdir(parents=True)
    (staging / 'qmd/pdf-figures/plot.svg').write_text('svg')
    (staging / 'qmd/report_pdf.typ').write_text('A completed document')
    output = tmp_path / 'output with spaces'
    saved = preserve_failed_render(staging, output, RuntimeError('compile failed'))
    assert not staging.exists()
    assert (saved / 'templates/qmd/pdf-figures/plot.svg').read_text() == 'svg'
    details = json.loads((saved / 'recovery.json').read_text())
    assert details['error'] == 'compile failed'
    assert details['compile_command'][:3] == ['quarto', 'typst', 'compile']
    assert 'python' not in details['compile_command']
    subprocess.run(['sh', '-n', str(saved / 'templates/compile-pdf.sh')], check=True)
    if shutil.which('quarto'):
        subprocess.run(['sh', str(saved / 'templates/compile-pdf.sh')], check=True,
                       capture_output=True, text=True, timeout=30)
        assert (saved / details['compile_output']).is_file()


def test_pre_execution_failure_does_not_offer_typesetting_recovery(tmp_path):
    staging = tmp_path / 'temporary/templates'
    staging.mkdir(parents=True)
    saved = preserve_failed_render(staging, tmp_path / 'output', 'cell failed')
    assert 'compile_command' not in json.loads((saved / 'recovery.json').read_text())
    assert not (saved / 'templates/compile-pdf.sh').exists()


@pytest.mark.skipif(not shutil.which('quarto'), reason='requires bundled Typst')
def test_targeted_table_query_keeps_continuation_labels_and_all_evidence(tmp_path):
    # Exercise both table implementations, repeated headers, and unrelated
    # markers with the real compiler. Every row remains available to validation.
    style = (ROOT / 'templates/pdf/print-style.typ').read_text()
    source = tmp_path / 'document.typ'
    source.write_text('#let report-fonts = ("DejaVu Sans",)\n'
                      '#let report-mono-fonts = report-fonts\n'
                      '#let report-language = "en"\n#let report-project = "Test"\n'
                      + style + '\n= Tables\n'
                      '#report-table(("Gene", "Value"), '
                      'range(160).map(i => ("Gene " + str(i), str(i))), '
                      '(false, true), id: "long", keep-together: false)\n'
                      '#report-sha256-table(("File", "Path", "SHA256"), '
                      'range(120).map(i => (str(i), "path", "abcd")), '
                      '(false, false, false), id: "hash", keep-together: false)\n', encoding='utf-8')
    observed = query_layout(source)
    assert validate_observations(observed) == []
    for identity, rows in [('long', 160), ('hash', 120)]:
        items = [item for item in observed if item['id'] == identity]
        assert sum(item['part'].startswith('row-') for item in items) == rows
        pages = {item['page'] for item in items if item['part'].startswith('row-')}
        continuations = {item['page'] for item in items if item['part'] == 'continuation'}
        assert len(pages) > 1
        assert continuations == pages - {min(pages)}


@pytest.mark.skipif(not shutil.which('quarto'), reason='requires bundled Typst')
def test_skipping_oversized_group_measurement_preserves_physical_layout(tmp_path):
    style = (ROOT / 'templates/pdf/print-style.typ').read_text()
    (tmp_path / 'plot.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" '
                                     'viewBox="0 0 10 10"><path d="M0 0L10 10"/></svg>')
    header = ('#let report-fonts = ("DejaVu Sans",)\n#let report-mono-fonts = report-fonts\n'
              '#let report-language = "en"\n#let report-project = "Test"\n')
    layouts = []
    for bound in [0, 160]:
        source = tmp_path / f'group-{bound}.typ'
        source.write_text(header + style + '\n= Results\n'
                          '#report-figure-group(([#report-figure("plot.svg", "Caption", 1, '
                          'preferred-height: 120mm, id: "figure")], '
                          '[#report-table(("Gene", "P"), range(12).map(i => (str(i), "1e-20")), '
                          '(false, true), id: "preview")]), '
                          f'minimum-height: {bound}mm)\n')
        layouts.append(query_layout(source))
    assert layouts[0] == layouts[1]
    assert validate_observations(layouts[1]) == []


@pytest.mark.parametrize('columns,oversized', [(1, True), (2, False)])
def test_parent_emits_conservative_group_height_bound(tmp_path, monkeypatch, columns, oversized):
    from bioreport.report import FigureBlock
    from bioreport.utils import render_output
    monkeypatch.setenv('BIOREPORT_OUTPUT_FORMAT', 'pdf')
    monkeypatch.setattr(render_output, '_figure_group', None)
    output = []
    monkeypatch.setattr(render_output, 'display', lambda value: output.append(value.data))
    with render_output.figure_group('test', columns=columns):
        render_output._figure_group.append((FigureBlock(id='f', path='plot.svg', caption='C',
                                                        ratio=1, preferred_height=100), '#image("plot.svg")'))
        render_output.show_print_table(pd.DataFrame({'Gene': list(range(12))}))
    import re
    bound = float(re.search(r'minimum-height: ([\d.]+)mm', output[0])[1])
    assert (bound > 110) is oversized


def test_navigation_reuses_extracted_pages_and_keeps_caller_reader_open(monkeypatch):
    from pypdf import PdfReader
    from pypdf._page import PageObject
    from bioreport.report.validation import validate_navigation
    golden = ROOT / 'tests/golden/rna/PRJ-RNA-PDF-001_report.pdf'
    expected = validate_navigation(golden)
    reader = PdfReader(golden)
    texts = [page.extract_text() or '' for page in reader.pages]

    def unexpected_extraction(*args, **kwargs):
        raise AssertionError('Page text was already extracted')

    monkeypatch.setattr(PageObject, 'extract_text', unexpected_extraction)
    actual = validate_navigation(golden, reader=reader, texts=texts)
    assert actual == expected
    assert not reader.stream.closed
    reader.close()
