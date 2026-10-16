"""Layout policy contracts for realistic short and wrapped/oversized tables."""
from bioreport.report import FigureBlock, FigureGroup, LayoutPlanner, TableBlock
from bioreport.config import load_config
from pathlib import Path
import json


def test_small_table_kept_and_large_wrapped_table_can_split():
    planner = LayoutPlanner()
    small = TableBlock(id='samples', headers=['sample','group'], rows=[['S1','A']]*6)
    assert planner.plan(small).keep_together
    large = TableBlock(id='terms', headers=['Description','Count'],
                       rows=[['long biological description '*20,'20']]*12)
    assert planner.plan(large).allow_split
    assert not planner.plan(large).keep_together
    assert planner.plan(large).repeat_header


def test_figures_get_bounded_heights_without_mutating_content():
    original = FigureBlock(id='portrait',path='p.svg',caption='Evidence',ratio=3)
    planned = LayoutPlanner().plan(original)
    assert planned.preferred_height <= 202
    assert planned.caption == original.caption and original.preferred_height is None
    pair = FigureGroup(id='reads',figures=[original,original],columns=2)
    assert all(f.preferred_height for f in LayoutPlanner().plan(pair).figures)


def test_enrichment_canonical_count_wins_and_legacy_is_fallback(tmp_path):
    root = Path(__file__).resolve().parents[1]
    cfg = json.loads((root/'tests/report.rna.pdf.json').read_text())
    cfg['report']['pdf']['enrichment_top_n'] = 8
    path = tmp_path/'report.json';path.write_text(json.dumps(cfg))
    assert load_config(path)['analysis']['enrichment']['top_n'] == 12
    del cfg['analysis']['enrichment']['top_n']
    path.write_text(json.dumps(cfg))
    assert load_config(path)['analysis']['enrichment']['top_n'] == 8


def test_display_aggregation_preserves_per_sample_totals_and_original():
    import numpy as np
    import plotly.graph_objects as go
    from bioreport.utils.print_theme import aggregate_bar_categories
    fig = go.Figure([go.Bar(x=[100,200],y=['S1','S2'],orientation='h',name='Mouse'),
                     *[go.Bar(x=[i,i+1],y=['S1','S2'],orientation='h',name=str(i)) for i in range(10)]])
    result = aggregate_bar_categories(fig)
    assert len(result.data) <= 5 and len(fig.data) == 11
    np.testing.assert_allclose(np.sum([t.x for t in result.data],axis=0),np.sum([t.x for t in fig.data],axis=0))


def test_volcano_cap_preserves_classification_and_probabilities():
    import pandas as pd
    from omics.rna.analysis.plot_utils import plot_volcano_pvalue
    frame = pd.DataFrame({'Symbol':['A','B'],'log2FoldChange':[2,-3], 'pvalue':[0,.001]})
    before = frame.copy(deep=True)
    fig = plot_volcano_pvalue(frame,'',col_logfc='log2FoldChange',col_pval='pvalue',display_cap=50)
    assert max(v for t in fig.data for v in t.y) == 50
    assert fig.layout.yaxis.ticktext[-1] == '50+'
    pd.testing.assert_frame_equal(frame,before)


def test_metadata_update_preserves_pages_and_bookmarks(tmp_path):
    from pypdf import PdfReader, PdfWriter
    from bioreport.utils.pdf_metadata import set_pdf_metadata, metadata_fields
    path = tmp_path/'report.pdf'
    writer = PdfWriter();writer.add_blank_page(595,842);writer.add_outline_item('Cover',0)
    writer.write(path);writer.close()
    cfg = {'report':{'title':'RNA report','type':'rna-seq'},'project':{'project_id':'P1'}}
    set_pdf_metadata(path,cfg)
    reader = PdfReader(path)
    assert len(reader.pages) == 1 and reader.outline[0].title == 'Cover'
    for key,value in metadata_fields(cfg).items(): assert reader.metadata[key] == value


def test_manifest_covers_configured_directory_and_report_hashes(tmp_path):
    import hashlib
    from bioreport.utils.provenance import build_provenance, write_delivery_manifests
    data = tmp_path/'data';data.mkdir();(data/'deg.csv').write_text('Gene,pvalue\nA,0\n')
    cfg={'project':{'project_id':'P1'},'input_files':{'data_dir':str(data),'deg_dir':str(data)}}
    provenance=build_provenance(cfg,[])
    assert len(provenance['input_manifest']) == 1
    assert provenance['input_manifest'][0]['sha256'] == hashlib.sha256((data/'deg.csv').read_bytes()).hexdigest()
    from bioreport.config import report_artifact_name
    report_path=tmp_path/report_artifact_name(cfg,'pdf')
    report_path.write_bytes(b'pdf contents')
    write_delivery_manifests(cfg,provenance,tmp_path)
    report=json.loads((tmp_path/'report-manifest.json').read_text())
    assert report['artifacts'][0]['sha256'] == hashlib.sha256(b'pdf contents').hexdigest()


def test_physical_layout_validator_rejects_split_small_table_and_caption():
    from bioreport.report.validation import validate_observations
    def event(kind, identity, part, page):
        return {'kind':kind,'id':identity,'part':part,'page':page}
    good=[event('table','samples','small',1),event('table','samples','header',1),
          event('table','samples','row-0',1),event('figure','pca','image',2),event('figure','pca','caption',2)]
    assert validate_observations(good) == []
    broken=good+[event('table','samples','row-1',2),event('figure','pca','caption',3)]
    assert {e['check'] for e in validate_observations(broken)} == {'small_table_split','missing_header','single_row_continuation','missing_continuation_label','figure_caption'}


def test_content_gate_detects_changed_metrics(tmp_path):
    from bioreport.report.content_validation import validate_content
    from bioreport.utils.pdf_results import summary_metrics
    root=Path(__file__).resolve().parents[1]
    cfg=load_config(root/'tests/report.rna.pdf.json')
    cfg['report']['modules']=['index']
    values=[[row['项目'],row['数值']] for _,row in summary_metrics(cfg).iterrows()]
    block={'id':'executive-metrics','type':'metric_grid','content':values}
    import pandas as pd
    sample_count=len(pd.read_csv(cfg['input_files']['sample_file']))
    samples={'id':'samples','type':'table','content':{'kind':'samples','sample_count':sample_count},'rows':[['sample']]*sample_count}
    path=tmp_path/'blocks.jsonl';path.write_text(json.dumps(block)+'\n'+json.dumps(samples))
    assert validate_content(cfg,path)['status']=='PASS'
    values[0][1]='999'
    path.write_text(json.dumps(block)+'\n'+json.dumps(samples))
    assert any(e['check']=='metric:样本数' for e in validate_content(cfg,path)['errors'])


def test_provenance_gate_detects_modified_input(tmp_path):
    from bioreport.utils.provenance import build_provenance, write_delivery_manifests, validate_delivery_manifests
    data=tmp_path/'data';data.mkdir();source=data/'sample.csv';source.write_text('sample\nA\n')
    cfg={'project':{'project_id':'P1'},'input_files':{'data_dir':str(data),'sample_file':str(source)}}
    write_delivery_manifests(cfg,build_provenance(cfg,[]),tmp_path)
    assert validate_delivery_manifests(cfg,tmp_path)['status']=='PASS'
    source.write_text('sample\nB\n')
    assert validate_delivery_manifests(cfg,tmp_path)['status']=='FAIL'


def test_orphan_intro_on_next_page_is_rejected():
    from bioreport.report.validation import validate_observations
    observations=[{'id':'section','kind':'heading','part':'start','page':1,'y':700},
                  {'id':'section','kind':'intro','part':'start','page':2,'y':80}]
    assert validate_observations(observations)[0]['check']=='orphan_heading'


def test_saved_multiqc_html_keeps_qualimap_and_star(monkeypatch):
    from omics.rna.analysis import qc_vis
    monkeypatch.setenv('BIOREPORT_OUTPUT_FORMAT','html')
    seen=[]
    monkeypatch.setattr(qc_vis,'display',lambda *a:None)
    monkeypatch.setattr(qc_vis,'show_figure',lambda fig,**kw:seen.append(fig))
    root=Path(__file__).resolve().parents[1]
    directory=root/'examples/rna-seq/data/QualiMap/multiqc_data'
    qc_vis.visualize_multiqc_logs(str(directory), ['QualiMap'])
    assert len(seen)==4 and all(fig.data for fig in seen)
    seen.clear()
    qc_vis.visualize_multiqc_logs(str(directory), ['STAR'])
    assert len(seen)==1 and 'STAR' in seen[0].layout.title.text


def test_fastq_screen_reports_missing_samples_instead_of_dropping_bars(tmp_path,monkeypatch):
    """缺样必须显性化：缺失样本写入正文提示，绘图样本集合不被静默裁剪。"""
    import json as _json
    from omics.rna.analysis import qc_vis
    from bioreport.utils import render_output
    root=Path(__file__).resolve().parents[1]
    source=root/'examples/rna-seq/data/fastq_screen_report/fastq_screen_multiqc_r1/multiqc_r1_fastq_screen_report_data'
    directory=tmp_path/'screen';directory.mkdir()
    data=_json.loads((source/'multiqc_data.json').read_text())
    # 人为去掉一个样本，模拟上游只汇总 5/6 个样本。
    dataset=data['report_plot_data']['fastq_screen_plot']['datasets'][0]
    dropped=dataset['samples'].pop(0)
    for cat in dataset['cats']: cat['data'] = cat['data'][1:]
    (directory/'multiqc_data.json').write_text(_json.dumps(data))
    cfg=_json.loads((root/'tests/report.rna.pdf.json').read_text())
    cfg['input_files']['data_dir']=str(root/'examples/rna-seq/data')
    path=tmp_path/'report.json';path.write_text(_json.dumps(cfg))
    monkeypatch.setenv('REPORT_CONFIG',str(path))
    monkeypatch.setenv('BIOREPORT_OUTPUT_FORMAT','pdf')
    notes=[];seen=[]
    monkeypatch.setattr(render_output,'typst_note',notes.append)
    monkeypatch.setattr(qc_vis,'_show_print_qc',lambda fig,identifier,title:seen.append(fig))
    monkeypatch.setattr(qc_vis,'typst_note',notes.append,raising=False)
    qc_vis.visualize_multiqc_logs(str(directory),['fastq_screen'])
    assert seen and len(seen[0].data[0].x) == 5
    assert any('5 / 12' in note or '缺失' in note for note in notes), notes


def test_fastq_screen_coverage_error_mode_raises(tmp_path,monkeypatch):
    import json as _json, pytest
    from omics.rna.analysis import qc_vis
    root=Path(__file__).resolve().parents[1]
    cfg=_json.loads((root/'tests/report.rna.pdf.json').read_text())
    cfg['input_files']['data_dir']=str(root/'examples/rna-seq/data')
    cfg['report']['pdf']['qc_sample_coverage']='error'
    path=tmp_path/'report.json';path.write_text(_json.dumps(cfg))
    monkeypatch.setenv('REPORT_CONFIG',str(path))
    with pytest.raises(ValueError, match='缺失'):
        qc_vis._assert_sample_coverage('FastQ Screen: Mapped Reads',['1-1_raw_R1_screen'],'demo')


def test_fastq_screen_percent_axis_reports_normalized_shares(tmp_path,monkeypatch):
    import json as _json
    from omics.rna.analysis import qc_vis
    import pandas as pd
    root=Path(__file__).resolve().parents[1]
    cfg=_json.loads((root/'tests/report.rna.pdf.json').read_text())
    cfg['input_files']['data_dir']=str(root/'examples/rna-seq/data')
    cfg['analysis']={'fastq_screen':{'axis':'percent'}}
    path=tmp_path/'report.json';path.write_text(_json.dumps(cfg))
    monkeypatch.setenv('REPORT_CONFIG',str(path))
    monkeypatch.setenv('BIOREPORT_OUTPUT_FORMAT','pdf')
    directory=root/'examples/rna-seq/data/fastq_screen_report/fastq_screen_multiqc_r1/multiqc_r1_fastq_screen_report_data'
    data=_json.loads((directory/'multiqc_data.json').read_text())
    plot=data['report_plot_data']['fastq_screen_plot'];dataset=plot['datasets'][0]
    fig,title=qc_vis._dataset_figure('fastq_screen_plot',plot,dataset)
    totals=[sum(float(t.x[i]) for t in fig.data) for i in range(len(dataset['samples']))]
    assert all(abs(total-100)<1e-6 for total in totals), totals
    assert tuple(fig.layout.xaxis.range)==(0,100)


def test_qualimap_coverage_drops_zero_bin_and_supports_log_scale(tmp_path,monkeypatch):
    """0X bin 计数 1e9 量级会把 1X–100X 曲线压死；默认剔除并支持对数纵轴。"""
    import json as _json
    from omics.rna.analysis import qc_vis
    root=Path(__file__).resolve().parents[1]
    cfg=_json.loads((root/'tests/report.rna.pdf.json').read_text())
    cfg['input_files']['data_dir']=str(root/'examples/rna-seq/data')
    path=tmp_path/'report.json';path.write_text(_json.dumps(cfg))
    monkeypatch.setenv('REPORT_CONFIG',str(path))
    monkeypatch.setenv('BIOREPORT_OUTPUT_FORMAT','pdf')
    directory=root/'examples/rna-seq/data/QualiMap/multiqc_data'
    data=_json.loads((directory/'multiqc_data.json').read_text())
    plot=data['report_plot_data']['qualimap_coverage_histogram']
    fig,_=qc_vis._dataset_figure('qualimap_coverage_histogram',plot,plot['datasets'][0])
    fig,note=qc_vis._apply_coverage_options('qualimap_coverage_histogram',fig)
    assert min(float(x) for t in fig.data for x in t.x)>=1 and '0X' in note
    cfg['analysis']={'qualimap':{'coverage':{'yscale':'log'}}}
    path.write_text(_json.dumps(cfg))
    fig2=qc_vis._dataset_figure('qualimap_coverage_histogram',plot,plot['datasets'][0])[0]
    fig2,note2=qc_vis._apply_coverage_options('qualimap_coverage_histogram',fig2)
    assert fig2.layout.yaxis.type=='log' and '对数刻度' in note2


def test_visual_comparison_rejects_changed_figure_region(tmp_path,monkeypatch):
    import importlib.util
    import pytest
    pytest.importorskip('pypdfium2')
    from PIL import Image, ImageDraw
    script=Path(__file__).with_name('pdf_visual_regression.py')
    spec=importlib.util.spec_from_file_location('visual_regression',script)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    golden=tmp_path/'golden';golden.mkdir()
    (golden/'baseline.json').write_text(json.dumps({'page_count':1}))
    Image.new('RGB',(100,100),'white').save(golden/'cover.png')
    def changed_snapshot(pdf,directory):
        directory.mkdir(parents=True)
        image=Image.new('RGB',(100,100),'white')
        ImageDraw.Draw(image).rectangle((20,20,70,70),fill='red')
        image.save(directory/'cover.png')
        return {'page_count':1,'pages':{'cover':1}}
    monkeypatch.setattr(module,'snapshots',changed_snapshot)
    assert module.compare(tmp_path/'unused.pdf',golden,tmp_path/'review')['status']=='FAIL'


def test_real_pdf_toc_destinations_and_broken_target(tmp_path):
    import pytest
    pytest.importorskip('pypdfium2')
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import ArrayObject, NameObject, FloatObject
    from bioreport.report.validation import validate_navigation
    golden=Path(__file__).parent/'golden/rna/PRJ-RNA-PDF-001_report.pdf'
    result=validate_navigation(golden)
    assert result['errors']==[] and result['toc_status']=='PASS' and result['bookmarks']>20
    reader=PdfReader(golden);writer=PdfWriter(clone_from=reader)
    annotation=writer.pages[1]['/Annots'][0].get_object()
    annotation['/A'][NameObject('/D')]=ArrayObject([writer.pages[0].indirect_reference,NameObject('/XYZ'),FloatObject(0),FloatObject(800),FloatObject(0)])
    broken=tmp_path/'broken-toc.pdf';writer.write(broken);writer.close();reader.close()
    assert any(e['check']=='toc_page_number' for e in validate_navigation(broken)['errors'])


def test_table_caption_stays_above_first_row():
    from bioreport.report.validation import validate_observations
    rows = [dict(kind='table', id='t', part='header', page=2, y=30),
            dict(kind='table', id='t', part='row-0', page=2, y=40)]
    caption = dict(kind='table', id='t', part='caption', page=2, y=20)
    assert validate_observations([caption, *rows]) == []
    assert validate_observations([{**caption, 'page':1}, *rows]) == [dict(check='table_caption', id='t')]
    assert validate_observations([{**caption, 'y':50}, *rows]) == [dict(check='table_caption', id='t')]
