"""Expression review must retain identifiers and raw numeric precision."""
import json
import pandas as pd
from bioreport.utils import visualize_utils, html_table


def test_expression_table_preserves_identifiers_precision_and_source(monkeypatch):
    monkeypatch.delenv('BIOREPORT_SHARED_ASSET_DIR', raising=False)
    monkeypatch.delenv('BIOREPORT_OUTPUT_FORMAT', raising=False)
    source=pd.DataFrame({'GENE_ID':['00017','00002'],
        'sample_with_long_identifier':[1.234567891234,1.2e-18],'counts':[100,2]})
    original=source.copy(deep=True)
    captured=[]
    monkeypatch.setattr(html_table,'show_compact_table',captured.append)
    visualize_utils.display_gene_expression_table(source)
    pd.testing.assert_frame_equal(captured[0],original)
    pd.testing.assert_frame_equal(source,original)
    payload=html_table.compact_payload(captured[0])
    assert payload['numeric']==[1,2]
    assert payload['data']==[['00017',1.234567891234,100],['00002',1.2e-18,2]]
    assert json.loads(json.dumps(payload))['data']==payload['data']


def test_numeric_display_does_not_round_sort_search_or_export():
    import shutil
    import subprocess
    import pytest
    if not shutil.which('node'): pytest.skip('Node.js checks number rendering')
    script='const render=('+html_table.NUMBER_RENDER_JS+');\n'+'''
const number=1.23456789e-18;
if(render(number,'display')!=='1.235e-18')throw Error('tiny p-value lost');
for(const operation of ['sort','filter','export','type']) {
 if(render(number,operation)!==number)throw Error('precision changed for '+operation);
}
if(render(100,'display')!=='100')throw Error('integer changed');
'''
    subprocess.run(['node','-e',script],check=True,capture_output=True,text=True)


def test_compact_table_escapes_script_data_and_keeps_duplicate_tables_unique(monkeypatch):
    from bs4 import BeautifulSoup
    from bioreport.utils import render_output
    monkeypatch.delenv('BIOREPORT_SHARED_ASSET_DIR',raising=False)
    monkeypatch.setattr(render_output,'ensure_table_runtime',lambda:'window.testRuntime')
    shown=[]
    monkeypatch.setattr(html_table,'display',lambda item:shown.append(item.data))
    frame=pd.DataFrame({'</script><img src=x>':['</script><script>bad()</script>']})
    html_table.show_compact_table(frame)
    html_table.show_compact_table(frame)
    first,second=[BeautifulSoup(s,'html.parser') for s in shown]
    assert first.table['id']!=second.table['id']
    assert not first.select('img')
    assert json.loads(first.select_one('.report-table-data').text)['data']==frame.values.tolist()
    assert 'IntersectionObserver' in shown[0]
    assert 'deferRender:true' in shown[0]


def test_pdf_expression_table_uses_print_path(monkeypatch):
    monkeypatch.setenv('BIOREPORT_OUTPUT_FORMAT','pdf')
    captured=[]
    monkeypatch.setattr(visualize_utils,'show',captured.append)
    source=pd.DataFrame({'id':['a'],'value':[1.23456789123]})
    visualize_utils.display_gene_expression_table(source)
    pd.testing.assert_frame_equal(captured[0],source)


def test_gene_list_display_keeps_raw_search_and_export_values():
    import shutil
    import subprocess
    import pytest
    if not shutil.which('node'): pytest.skip('Node.js checks cell rendering')
    script = 'const render=(' + html_table.GENE_LIST_RENDER_JS + ');' + '''
const genes = Array.from({length:1000}, (_,i)=>'Solyc'+i).join('/');
const rendered = render(genes,'display');
if(!rendered.includes('report-gene-list') || !rendered.includes(genes))throw Error('full list missing');
for(const type of ['sort','filter','export','type']) {
 if(render(genes,type)!==genes)throw Error('raw value modified for '+type);
}
if(render('<script>&', 'display').includes('<script>'))throw Error('unescaped gene text');
'''
    subprocess.run(['node','-e',script],check=True,capture_output=True,text=True)
