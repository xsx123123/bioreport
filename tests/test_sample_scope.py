import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

from bioreport.utils.print_theme import print_panels
from bioreport.utils.sample_scope import expression_sample_scope, expression_sample_scope_note


@pytest.mark.parametrize('lang', ['zh', 'en'])
def test_scope_reports_matrix_extras_and_missing_metadata_without_changing_inputs(tmp_path, lang):
    matrix = tmp_path / 'tpm.tsv'
    metadata = tmp_path / 'samples.csv'
    pd.DataFrame({'A':[2.], 'B':[3.], 'C':[4.], 'D':[5.]}).to_csv(matrix, sep='\t')
    pd.DataFrame({'sample':['A_raw','B_raw','absent_raw'],
                  'sample_name':['A','B','absent'], 'group':['X','X','Y']}).to_csv(metadata,index=False)
    original = metadata.read_bytes(), matrix.read_bytes()
    scope = expression_sample_scope(matrix, metadata)
    assert scope['metadata_column'] == 'sample_name'
    assert scope['included_samples'] == ['A','B']
    assert scope['matrix_only'] == ['C','D']
    assert scope['metadata_only'] == ['absent']
    note = expression_sample_scope_note({'report':{'language':lang},
                                        'input_files':{'sample_file':str(metadata),'tpm_file':str(matrix)}})
    assert all(value in note for value in ['3','4','2','C','D','absent'])
    assert ('not randomly subsampled' if lang == 'en' else '不随机抽取样本') in note
    assert original == (metadata.read_bytes(), matrix.read_bytes())


@pytest.mark.parametrize('lang', ['zh', 'en'])
def test_every_sample_is_retained_across_all_panels_and_caption_states_total(monkeypatch, lang):
    monkeypatch.setenv('BIOREPORT_LANGUAGE',lang)
    names = [f'S{i}' for i in range(66)]
    fig = go.Figure([go.Scatter(x=[1,2],y=[i,i+1],mode='lines',name=name) for i,name in enumerate(names)])
    fig.update_layout(meta={'sample_groups': {name:str(i//3) for i,name in enumerate(names)}})
    panels = print_panels(fig)
    displayed = [trace.name for panel,_ in panels for trace in panel.data]
    assert displayed == names
    assert len(displayed) == len(set(displayed)) == 66
    assert [len(panel.data) for panel,_ in panels] == [18,18,18,12]
    for panel, caption in panels:
        assert f'{len(panel.data)} / 66' in caption
        assert ('no random subsampling' if lang=='en' else '未随机抽样') in caption


def test_heatmap_panels_preserve_all_54_samples_and_their_values(monkeypatch):
    monkeypatch.setenv('BIOREPORT_LANGUAGE','zh')
    names = [f'S{i}' for i in range(54)]
    values = np.arange(4*54).reshape(4,54)
    fig = go.Figure(go.Heatmap(x=names,y=['A','B','C','D'],z=values))
    panels = print_panels(fig)
    assert [len(panel.data[0].x) for panel,_ in panels] == [27,27]
    assert [sample for panel,_ in panels for sample in panel.data[0].x] == names
    np.testing.assert_array_equal(np.concatenate([p.data[0].z for p,_ in panels],axis=1),values)
    assert all('27 / 54' in note and '未随机抽样' in note for _,note in panels)


def test_coverage_counts_source_samples_separately_from_group_curves(tmp_path, monkeypatch):
    from omics.rna.analysis import qc_vis
    metadata = tmp_path / 'samples.csv'
    pd.DataFrame({'sample':['a','b'],'sample_name':['a','b'],'group':['A','A']}).to_csv(metadata,index=False)
    monkeypatch.setenv('BIOREPORT_LANGUAGE','zh')
    monkeypatch.setattr(qc_vis, '_qc_config', lambda: {'report':{'pdf':{'qc_detail':'key'}},
                                                     'input_files':{'sample_file':str(metadata)}})
    figure = go.Figure([go.Scatter(x=[0,1,2],y=values,mode='lines',name=name)
                       for name,values in [('a',[0,2,4]),('b',[0,4,8]),('extra',[0,7,9])]])
    prepared, caption = qc_vis._prepare_print_qc(figure,'qualimap-coverage-histogram','Coverage histogram')
    assert prepared.layout.meta['coverage_members'] == {'A':['a','b'],'extra':['extra']}
    assert '3 个输入样本' in caption and '2 条曲线' in caption
    assert '1 个未在样本表获得分组注释' in caption
    assert '未随机抽样' in caption
