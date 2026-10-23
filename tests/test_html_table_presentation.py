"""Shared DataTables display rules must not change the analysis or export values."""
import json
from pathlib import Path
import shutil
import subprocess

import pandas as pd
import pytest

from bioreport.utils import html_table, render_output


def test_duplicate_symbol_removed_only_after_comparing_entire_column():
    frame = pd.DataFrame({'ENSEMBL': ['G1', 'G2'] * 10, 'baseMean': [1.2345] * 20,
                          'Symbol': ['G1', 'G2'] * 10})
    original = frame.copy(deep=True)
    definitions = html_table.table_column_defs(frame)
    assert definitions[-1]['visible'] is False
    assert definitions[1]['className'].startswith('dt-right')
    pd.testing.assert_frame_equal(frame, original)
    # Identical first-page values are insufficient to hide real annotations.
    frame.loc[19, 'Symbol'] = 'ActualGeneSymbol'
    assert 'visible' not in html_table.table_column_defs(frame)[-1]
    assert all('visible' not in item for item in html_table.table_column_defs(frame.iloc[:0]))


def test_go_widths_and_numeric_alignment_use_common_definitions():
    frame = pd.DataFrame({'ID': ['GO:001'], 'Description': ['long pathway ' * 30],
                          'FoldEnrichment': [2.1234], 'GeneRatio': ['1/2'], 'Count': [12]})
    definitions = {item['name']: item for item in html_table.table_column_defs(frame, offset=1)}
    assert definitions['Description']['width'] == '40%'
    for name in ('FoldEnrichment', 'GeneRatio', 'Count'):
        assert definitions[name]['className'].startswith('dt-right')
        assert definitions[name]['width'].endswith('px')
    assert definitions['ID']['targets'] == 1


def test_display_formatting_keeps_full_values_for_sort_search_and_export():
    if not shutil.which('node'):
        pytest.skip('Node is required to execute DataTables rendering callbacks')
    cases = [
        ('baseMean', 12.3456789, '12.3'), ('baseMean', 12, '12.0'),
        ('pvalue', 1.23456789e-18, '1.23e-18'), ('padj', .0212345678, '2.12e-2'),
        ('p.adjust', .0000012345, '1.23e-6'), ('pvalue', 0, '0'),
        ('log2FoldChange', -2.123456, '-2.123'), ('lfcSE', .1234567, '0.123'),
        ('stat', 4.987654, '4.988'), ('Count', 123, '123'),
    ]
    script = 'const render = (' + html_table.NUMBER_RENDER_JS + ');const cases=' + json.dumps(cases) + ';' + '''
for (const [name,value,expected] of cases) {
  const meta={col:0,settings:{aoColumns:[{sName:name}]}};
  if(render(value,'display',null,meta)!==expected)throw Error(name+' formatted incorrectly');
  for(const type of ['sort','type','filter','export']) {
    if(render(value,type,null,meta)!==value)throw Error(name+' raw precision changed for '+type);
  }
}
'''
    subprocess.run(['node', '-e', script], check=True, capture_output=True, timeout=15)


def test_all_table_entry_points_use_same_options_and_hide_duplicate_exports(monkeypatch):
    monkeypatch.delenv('BIOREPORT_OUTPUT_FORMAT', raising=False)
    monkeypatch.delenv('BIOREPORT_SHARED_ASSET_DIR', raising=False)
    monkeypatch.setattr(render_output, 'ensure_table_runtime', lambda: 'window.testRuntime')
    frame = pd.DataFrame({'ENSEMBL': ['G1'], 'baseMean': [1.2345678], 'Symbol': ['G1']})
    captured = {}
    monkeypatch.setattr(render_output, 'show_interactive_table', lambda table, **kwargs: captured.update(kwargs))
    render_output.show_table(frame)
    assert captured['autoWidth'] is False and captured['pageLength'] == 10
    assert captured['dom'] == html_table.TABLE_DOM
    assert all(button['exportOptions']['columns'] == ':visible' for button in captured['buttons'])
    output = []
    monkeypatch.setattr(html_table, 'display', lambda html: output.append(html.data))
    html_table.show_compact_table(frame)
    assert 'autoWidth:false, pageLength:10' in output[0]
    assert "orthogonal:'export', columns:':visible'" in output[0]
    # The payload still contains the original full-precision data.
    assert html_table.compact_payload(frame)['data'] == [['G1', 1.2345678, 'G1']]


def test_description_is_escaped_without_changing_copy_and_search():
    if not shutil.which('node'):
        pytest.skip('Node is required to execute the cell renderer')
    script = 'const render=(' + html_table.DESCRIPTION_RENDER_JS + ');' + '''
const value='A <pathway> "label" & genes';
const display=render(value,'display');
if(display.includes('<pathway>') || !display.includes('&lt;pathway&gt;'))throw Error('HTML not escaped');
if(!display.includes('title="'))throw Error('full description not available');
for(const type of ['sort','type','filter','export']) {
  if(render(value,type)!==value)throw Error('description changed for '+type);
}
'''
    subprocess.run(['node', '-e', script], check=True, capture_output=True, timeout=15)
