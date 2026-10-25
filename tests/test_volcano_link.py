"""Cross-view gene identity must survive trace grouping and duplicate symbols."""
import json

import numpy as np
import pandas as pd
import pytest

from bioreport.utils import html_table, render_output, visualize_utils
from omics.rna.analysis.plot_utils import plot_volcano_pvalue


def frame():
    return pd.DataFrame({'ENSEMBL': ['G1', 'G2', 'G3', 'G4'], 'Symbol': ['DUP', 'DUP', 'Other', 'Missing'],
                         'log2FoldChange': [2.5, -3., .2, np.nan], 'pvalue': [.001, .0001, .5, .01]},
                        index=[21, 17, 9, 8])


def test_link_identity_uses_gene_ids_and_preserves_original_data_and_plot():
    source = frame()
    original = source.copy(deep=True)
    figure = plot_volcano_pvalue(source, '', col_logfc='log2FoldChange', col_pval='pvalue',
                                 comparison='Treat_vs_Control', display_cap=20)
    lookup = {identity: (trace.name, x, y, symbol)
              for trace in figure.data
              for identity, x, y, symbol in zip(trace.customdata, trace.x, trace.y, trace.text)}
    assert lookup['G1'] == ('Up', 2.5, 3., 'DUP')
    assert lookup['G2'] == ('Down', -3., 4., 'DUP')
    assert lookup['G3'][0] == 'NS'
    assert figure.layout.meta['bioreport_volcano']['comparison'] == 'Treat_vs_Control'
    assert figure.layout.meta['bioreport_volcano']['idColumn'] == 'ENSEMBL'
    assert figure.layout.meta['display_cap'] == 20
    pd.testing.assert_frame_equal(source, original)
    unlinked = plot_volcano_pvalue(source, '', col_logfc='log2FoldChange', col_pval='pvalue')
    assert all(trace.customdata is None for trace in unlinked.data)


def test_link_without_identifier_uses_source_row_positions():
    source = frame().drop(columns=['ENSEMBL', 'Symbol'])
    figure = plot_volcano_pvalue(source, '', col_logfc='log2FoldChange', col_pval='pvalue', comparison='A')
    assert figure.layout.meta['bioreport_volcano']['idColumn'] is None
    assert sorted(key for trace in figure.data for key in trace.customdata) == ['0', '1', '2', '3']


def test_volcano_x_axis_is_symmetric_and_palette_matches_publication_style():
    figure = plot_volcano_pvalue(frame(), '', col_logfc='log2FoldChange', col_pval='pvalue',
                                 comparison='Treat_vs_Control')
    # max |log2FC| in frame() is 3.0 -> limit 3.6, centered on zero.
    x_range = tuple(figure.layout.xaxis.range)
    assert x_range[0] == pytest.approx(-3.6)
    assert x_range[1] == pytest.approx(3.6)
    assert figure.layout.meta['bioreport_volcano']['xLimit'] == pytest.approx(3.6)
    markers = {trace.name: trace.marker for trace in figure.data}
    assert markers['Up'].color == '#e41749' and markers['Up'].line.color == '#e41749'
    assert markers['Down'].color == '#41b6e6' and markers['Down'].line.color == '#41b6e6'
    assert markers['NS'].color == '#c7c7c7'
    assert figure.layout.yaxis.rangemode == 'tozero'


def test_volcano_x_limit_keeps_threshold_lines_visible_for_tiny_effects():
    tiny = frame().assign(log2FoldChange=[0.1, -0.2, 0.05, 0.3])
    figure = plot_volcano_pvalue(tiny, '', col_logfc='log2FoldChange', col_pval='pvalue')
    x_range = tuple(figure.layout.xaxis.range)
    assert x_range[0] == pytest.approx(-1.5)  # fc_cutoff * 1.5
    assert x_range[1] == pytest.approx(1.5)
    capped = plot_volcano_pvalue(frame(), '', col_logfc='log2FoldChange', col_pval='pvalue', display_cap=20)
    assert tuple(capped.layout.yaxis.range)[0] == 0


@pytest.mark.parametrize('language', ['zh', 'en'])
def test_link_metadata_is_escaped_and_runtime_is_staged_once(monkeypatch, tmp_path, language):
    monkeypatch.setenv('BIOREPORT_LANGUAGE', language)
    monkeypatch.delenv('BIOREPORT_OUTPUT_FORMAT', raising=False)
    monkeypatch.setenv('BIOREPORT_SHARED_ASSET_DIR', str(tmp_path))
    monkeypatch.setenv('BIOREPORT_SHARED_ASSET_URL', '../assets')
    monkeypatch.setattr(render_output, '_plotly_loaded', False)
    monkeypatch.setattr(render_output, 'ensure_table_runtime', lambda: 'window.testRuntime')
    tables, figures = [], []
    monkeypatch.setattr(html_table, 'display', lambda item: tables.append(item.data))
    monkeypatch.setattr(render_output, 'display', lambda item: figures.append(item.data))
    comparison = 'Treat </script><script>alert(1)</script> & "Control"'
    visualize_utils.display_gene_expression_table(frame(), volcano_comparison=comparison)
    figure = plot_volcano_pvalue(frame(), '', col_logfc='log2FoldChange', col_pval='pvalue', comparison=comparison)
    render_output.show_figure(figure)
    render_output.show_figure(figure)
    assert '<script src="../assets/volcano-link.js"></script>' in figures[0]
    assert (tmp_path / 'volcano-link.js').is_file()
    assert all('volcano-link.js' not in item for item in figures[1:])
    from bioreport.utils.html_payload import unpacked_text
    import re
    for item in figures[1:]:
        packed = re.search(r'class="report-plot-data"[^>]*>(.*?)</script>', item, re.S)[1]
        assert 'BioReportVolcanoLink.attachChart' in unpacked_text(packed)
    assert 'BioReportVolcanoLink.attachTable' in tables[0]
    assert comparison not in tables[0]
    assert json.dumps(comparison, ensure_ascii=True).replace('<', '\\u003c') in tables[0]
