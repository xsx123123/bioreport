"""Scientific and dynamic contracts, beyond template-string checks."""
import json
from pathlib import Path
import warnings

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

from bioreport.config import load_config
from bioreport.utils.pdf_results import apply_gene_annotation, comparison_summaries, deg_counts, enrichment_chunks, gene_columns, ordered_samples, raw_probability_columns, summary_metrics
from bioreport.utils.print_theme import export_vector, group_palette, print_panels
from bioreport.utils import render_output
from omics.rna.analysis.enrichment_plotly import draw_fancy_dotplot, parse_gene_ratios
from omics.rna.analysis.plot_utils import plot_volcano_pvalue

ROOT = Path(__file__).resolve().parents[1]


def test_counts_use_raw_p_thresholds_and_never_mutate_input():
    frame = pd.DataFrame({'Symbol':['A','B','C','D','E'], 'log2FoldChange':[2,-2,1,2,np.nan],
                          'pvalue':[0,.01,.01,.08,.01], 'padj':[.9,.9,.9,0,0]})
    original = frame.copy(deep=True)
    assert deg_counts(frame,1,.05) == (1,1)
    fig = plot_volcano_pvalue(frame,'',col_logfc='log2FoldChange',col_pval='pvalue',fc_cutoff=1,pval_cutoff=.05)
    assert len(next(t for t in fig.data if t.name=='Up').x) == 1
    assert next(t for t in fig.data if t.name=='Up').y[0] == 300
    pd.testing.assert_frame_equal(frame,original)


def test_numeric_format_distinguishes_zero_small_p_and_missing(monkeypatch):
    outputs=[]
    monkeypatch.setattr(render_output,'display',outputs.append)
    frame=pd.DataFrame({'pvalue':[0.,1e-250,np.nan],'padj':[1e-20,.12,np.nan], 'log2FoldChange':[1.234,-2.345,np.nan]})
    render_output.show_print_table(frame)
    text=outputs[0].data
    assert '0 (输入)' in text and '1.00e-250' in text and '1.00e-20' in text
    assert 'NA' in text and '1.23' in text and '-2.35' in text
    assert 'null' not in text and 'nan' not in text


def test_gene_id_semantics_preserve_real_symbols():
    assert list(gene_columns(pd.DataFrame({'Symbol':['ENSMUSG000001']}))) == ['Gene ID']
    mapped=gene_columns(pd.DataFrame({'gene_id':['ENSMUSG000001'],'Symbol':['Trp53']}))
    assert list(mapped)==['Gene ID','Symbol'] and mapped.Symbol.iloc[0]=='Trp53'
    mixed=gene_columns(pd.DataFrame({'Symbol':['ENSMUSG000001','Trp53']}))
    assert mixed['Gene ID'].iloc[0]=='ENSMUSG000001' and pd.isna(mixed.Symbol.iloc[0])
    assert mixed.Symbol.iloc[1]=='Trp53'


def test_optional_gene_annotation_maps_ids_without_relabeling_unknowns(tmp_path):
    annotation = tmp_path / 'genes.tsv'
    annotation.write_text('gene_id\tgene_name\nENSMUSG1\tGnai3\n', encoding='utf-8')
    cfg = {'input_files': {'gene_annotation_file': str(annotation)}}
    mapped = apply_gene_annotation(pd.DataFrame({'ENSEMBL': ['ENSMUSG1', 'ENSMUSG2']}), cfg)
    assert mapped['Symbol'].iloc[0] == 'Gnai3' and pd.isna(mapped['Symbol'].iloc[1])


def test_probability_preview_preserves_literals_below_float_range(tmp_path,monkeypatch):
    path=tmp_path/'tiny.csv'
    path.write_text('GeneID,pvalue,padj\nA,1e-400,1e-380\nB,0,0\nC,,\n')
    frame=pd.read_csv(path)
    assert frame.pvalue.iloc[0]==0  # ordinary float parsing underflows
    precise=raw_probability_columns(path,frame)
    outputs=[];monkeypatch.setattr(render_output,'display',outputs.append)
    render_output.show_print_table(precise)
    assert '1.00e-400' in outputs[0].data and '1.00e-380' in outputs[0].data
    assert outputs[0].data.count('0 (输入)')==2 and 'NA' in outputs[0].data


def test_summary_excludes_extra_read_and_mapping_stages_and_missing_is_na(tmp_path):
    pd.DataFrame({'sample':['S1_raw','S2_raw'], 'sample_name':['S1','S2'],'group':['A','B']}).to_csv(tmp_path/'samples.csv',index=False)
    pd.DataFrame({'Sample':['S1_raw','S2_raw','S1_R1'], 'fastp-after_filtering_q30_rate':[.9,.98,0]}).to_csv(tmp_path/'qc.tsv',sep='\t',index=False)
    pd.DataFrame({'Sample':['S1_raw','S2_raw','S1_raw_STARpass1'], 'star-mapped_percent':[90.,98.,0.]}).to_csv(tmp_path/'map.tsv',sep='\t',index=False)
    pd.DataFrame({'S1':[0,1,2],'S2':[0,2,1]}).to_csv(tmp_path/'tpm.tsv',sep='\t')
    cfg={'input_files':{'sample_file':str(tmp_path/'samples.csv'),'qc_file':str(tmp_path/'qc.tsv'),'mapping_file':str(tmp_path/'map.tsv'),'tpm_file':str(tmp_path/'tpm.tsv')}}
    metrics=summary_metrics(cfg).set_index('项目')
    assert metrics.loc['平均 Q30','数值']=='94.00%'
    assert metrics.loc['平均比对率','数值']=='94.00%'
    assert metrics.loc['检出基因数','数值']=='2'
    pd.DataFrame({'Sample':['S1_raw','S2_raw']}).to_csv(tmp_path/'qc.tsv',sep='\t',index=False)
    assert summary_metrics(cfg).set_index('项目').loc['平均 Q30','数值']=='NA'


def test_display_path_reports_delivery_relative_paths_only():
    from bioreport.config import display_path
    cfg = load_config(ROOT / 'tests/report.rna.pdf.json')
    resolved = cfg['input_files']['data_dir']
    # 交付目录内文件显示为相对路径，不暴露运行环境的绝对目录。
    assert display_path(cfg['input_files']['sample_file'], cfg) == 'index/sample.csv'
    assert resolved not in display_path(cfg['input_files']['sample_file'], cfg)
    # 目录之外的路径保持原样，保证可核验。
    assert display_path('/etc/hostname', cfg) == '/etc/hostname'
    assert display_path('', cfg) == ''
    # 没有配置时降级为原路径，不在展示环节抛错。
    assert display_path(str(Path('/opt')/'x.txt'), {'input_files': {}}) == str(Path('/opt')/'x.txt')


def test_each_comparison_is_counted_separately_and_disabled_modules_do_not_read_deg(tmp_path):
    cfg=load_config(ROOT/'tests/report.rna.pdf.json')
    cfg['input_files']['contrasts_file']=str(tmp_path/'contrasts.csv')
    cfg['input_files']['deg_dir']=str(tmp_path)
    pd.DataFrame({'Control':['A','B'],'Treat':['B','C']}).to_csv(tmp_path/'contrasts.csv',index=False)
    pd.DataFrame({'log2FoldChange':[2,-2],'pvalue':[.01,.8]}).to_csv(tmp_path/'B_vs_A_DEG.csv',index=False)
    pd.DataFrame({'log2FoldChange':[2,-2],'pvalue':[.01,.01]}).to_csv(tmp_path/'C_vs_B_DEG.csv',index=False)
    summary=comparison_summaries(cfg)
    assert summary['比较组'].tolist()==['B_vs_A','C_vs_B']
    assert summary['上调'].tolist()==[1,1] and summary['下调'].tolist()==[0,1]
    (tmp_path/'C_vs_B_DEG.csv').unlink()
    with pytest.raises(FileNotFoundError,match='C_vs_B'): comparison_summaries(cfg)
    cfg['report']['modules']=['rna.results.samples']
    assert comparison_summaries(cfg).empty


def test_display_order_uses_metadata_and_keeps_within_group_order():
    metadata=pd.DataFrame({'sample':['b_raw','a_raw','c_raw'],'sample_name':['b','a','c'],'group':['B','A','A']})
    assert ordered_samples(metadata,['c','b','a'])==['a','c','b']
    with pytest.raises(ValueError,match='does not match'): ordered_samples(metadata,['unmatched'])


def test_panel_splitting_preserves_cluster_order_values_and_color_scale():
    z=np.arange(5*43).reshape(5,43)
    fig=go.Figure(go.Heatmap(z=z,x=[f'S{i}' for i in range(43)],y=[f'G{i}' for i in range(5)],zmin=-2,zmax=2))
    panels=print_panels(fig)
    assert [len(p.data[0].x) for p,_ in panels]==[12,12,12,7]
    np.testing.assert_array_equal(np.concatenate([p.data[0].z for p,_ in panels],axis=1),z)
    assert all(p.data[0].zmin==-2 and p.data[0].zmax==2 for p,_ in panels)
    assert list(fig.data[0].x)==[f'S{i}' for i in range(43)]


def test_static_export_retains_volcano_threshold_lines_and_heatmap_orientation(tmp_path,monkeypatch):
    import matplotlib.figure
    captured=[]
    original=matplotlib.figure.Figure.savefig
    def save(figure,*args,**kwargs):
        captured.append(figure)
        return original(figure,*args,**kwargs)
    monkeypatch.setattr(matplotlib.figure.Figure,'savefig',save)
    frame=pd.DataFrame({'Symbol':['A','B'],'log2FoldChange':[2,-2],'pvalue':[.01,.02]})
    fig=plot_volcano_pvalue(frame,'',col_logfc='log2FoldChange',col_pval='pvalue',fc_cutoff=1,pval_cutoff=.05)
    export_vector(fig,tmp_path/'volcano.svg')
    lines=captured[-1].axes[0].lines
    assert any(np.all(np.asarray(line.get_xdata())==1) for line in lines)
    assert any(np.allclose(line.get_ydata(),-np.log10(.05)) for line in lines)
    heatmap=go.Figure(go.Heatmap(z=[[1,2],[3,4]],x=['S1','S2'],y=['G1','G2'],zmin=-2,zmax=2))
    heatmap.update_layout(yaxis_autorange='reversed')
    heatmap.data[0].zmin = heatmap.data[0].zmax = None
    heatmap.update_layout(coloraxis_cmin=-2,coloraxis_cmax=2)
    export_vector(heatmap,tmp_path/'heatmap.svg')
    axis=captured[-1].axes[0]
    np.testing.assert_array_equal(axis.images[0].get_array(),[[1,2],[3,4]])
    assert axis.get_ylim()[0] > axis.get_ylim()[1]
    assert axis.images[0].get_clim()==(-2,2)


def test_long_enrichment_labels_split_by_line_budget_and_cjk_fonts_are_embedded_as_paths(tmp_path):
    frame=pd.DataFrame({'ID':[f'GO:{i}' for i in range(14)],
                        'Description':['regulation of '+('extremely long biological pathway description '*4)+str(i) for i in range(14)],
                        'GeneRatio':['2/10']*14,'Count':range(1,15),'p.adjust':np.linspace(.001,.014,14)})
    pieces=list(enrichment_chunks(frame))
    assert len(pieces)>2 and sum(len(piece) for _,piece in pieces)==14
    fig,_=draw_fancy_dotplot(frame.iloc[:2],p_cutoff=None,wrap_width=28)
    assert fig.layout.xaxis.title.text=='<b>Gene ratio</b>'
    assert 'Adjusted P value' in fig.layout.coloraxis.colorbar.title.text
    assert any(t.name.startswith('Count:') for t in fig.data if t.name)
    cjk=go.Figure(go.Scatter(x=[1,2],y=[2,3],mode='lines',name='处理组'))
    cjk.update_layout(xaxis_title='样本位置',yaxis_title='表达量')
    with warnings.catch_warnings(record=True) as logged:
        export_vector(cjk,tmp_path/'cjk.svg')
    assert not any('Glyph' in str(w.message) and 'missing' in str(w.message) for w in logged)
    assert '<path' in (tmp_path/'cjk.svg').read_text()


def test_missing_ratios_are_not_replaced_by_zero():
    values=parse_gene_ratios(pd.Series(['2/10',None,'NA','3/0','0.5',0]))
    assert values.iloc[0]==.2 and values.iloc[4]==.5 and values.iloc[5]==0
    assert values.iloc[1:4].isna().all()


def test_multiqc_print_keeps_read_stages_separate_and_has_full_detail_mode(tmp_path,monkeypatch):
    from omics.rna.analysis import qc_vis
    cfg=json.loads((ROOT/'tests/report.rna.pdf.json').read_text())
    cfg['input_files']['data_dir']=str(ROOT/'examples/rna-seq/data')
    path=tmp_path/'report.json';path.write_text(json.dumps(cfg))
    monkeypatch.setenv('REPORT_CONFIG',str(path))
    monkeypatch.setenv('BIOREPORT_OUTPUT_FORMAT','pdf')
    seen=[]
    monkeypatch.setattr(qc_vis,'show_figure',lambda figure,config=None,caption=None:seen.append((figure,caption)))
    monkeypatch.setattr(render_output,'display',lambda *args:None)
    directory=ROOT/'examples/rna-seq/data/fastp_trim_report/multiqc_short_read_trim_report_data'
    qc_vis.visualize_multiqc_logs(str(directory),['fastp'])
    quality=[(f,c) for f,c in seen if 'Sequence Quality' in c]
    assert len(quality)==2 and all('After filtering' in c for _,c in quality)
    assert all(len(f.data)==6 for f,_ in quality)
    palette=group_palette(['1','2'])
    assert {t.line.color for f,_ in quality for t in f.data}==set(palette.values())
    cfg['report']['pdf']['qc_detail']='all';path.write_text(json.dumps(cfg));seen.clear()
    qc_vis.visualize_multiqc_logs(str(directory),['fastp'])
    assert sum('Sequence Quality' in c for _,c in seen)==4
    assert any('Insert' in c for _,c in seen)


def test_pdf_options_are_validated(tmp_path):
    cfg=json.loads((ROOT/'tests/report.rna.pdf.json').read_text())
    cfg['report']['pdf']['matrix_rows']=0
    path=tmp_path/'bad.json';path.write_text(json.dumps(cfg))
    with pytest.raises(ValueError,match='matrix_rows'):load_config(path)


def test_custom_trace_retains_plotly_svg_compatibility(tmp_path,monkeypatch):
    monkeypatch.setenv('BIOREPORT_OUTPUT_FORMAT','pdf')
    monkeypatch.setenv('BIOREPORT_ASSET_DIR',str(tmp_path))
    shown=[];monkeypatch.setattr(render_output,'display',shown.append)
    calls=[]
    def image(figure,**kwargs):
        calls.append(kwargs)
        return b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 480"><path d="M0 0L10 10"/></svg>'
    monkeypatch.setattr(go.Figure,'to_image',image)
    render_output.show_figure(go.Figure(go.Pie(labels=['A','B'],values=[2,3])),caption='Custom pie')
    assert calls==[{'format':'svg','scale':4}]
    assert '#report-figure' in shown[0].data and 'Custom pie' in shown[0].data


def test_multiqc_serialized_object_supports_all_datasets(monkeypatch,tmp_path):
    from omics.rna.analysis import qc_vis
    multiqc=pytest.importorskip('multiqc')
    from multiqc.interactive import _load_plot
    source=ROOT/'examples/rna-seq/data/fastp_trim_report/multiqc_short_read_trim_report_data/multiqc_data.json'
    dump=json.loads(source.read_text())['report_plot_data']['fastp-seq-quality-plot']
    model=_load_plot(dump)
    cfg=json.loads((ROOT/'tests/report.rna.pdf.json').read_text())
    cfg['input_files']['data_dir']=str(ROOT/'examples/rna-seq/data')
    cfg['report']['pdf']['qc_detail']='all'
    path=tmp_path/'report.json';path.write_text(json.dumps(cfg))
    monkeypatch.setenv('REPORT_CONFIG',str(path));monkeypatch.setenv('BIOREPORT_OUTPUT_FORMAT','pdf')
    monkeypatch.setattr(multiqc,'parse_logs',lambda *args,**kwargs:None)
    monkeypatch.setattr(multiqc,'list_modules',lambda:['fastp'])
    monkeypatch.setattr(multiqc,'list_plots',lambda:{'fastp':['Sequence Quality']})
    monkeypatch.setattr(multiqc,'get_plot',lambda *args:model)
    seen=[];monkeypatch.setattr(qc_vis,'show_figure',lambda fig,config=None,caption=None:seen.append((fig,caption)))
    monkeypatch.setattr(render_output,'display',lambda *args:None)
    qc_vis.visualize_multiqc_logs(str(tmp_path),['fastp'])
    assert len(seen)==4 and sum('Before filtering' in caption for _,caption in seen)==2
