"""Create clearly synthetic layout fixtures from existing RNA example results.

Replicated samples exercise layout only; this utility does not run RNA analysis
or claim these fixtures represent an independent biological experiment.
"""
from pathlib import Path
import argparse
import copy
import json
import shutil

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def create(destination):
    destination = destination.resolve()
    destination.mkdir(parents=True,exist_ok=True)
    data = destination/'data'
    shutil.copytree(ROOT/'examples/rna-seq/data',data,dirs_exist_ok=True)
    cfg=json.loads((ROOT/'tests/report.rna.pdf.json').read_text())
    cfg['input_files']['data_dir']=str(data)
    cfg['project'].update(client='排版验证：重复样本构造数据',short_name='PDF 布局压力测试',project_id='LAYOUT-FIXTURE',report_date='测试固定日期',run_id='synthetic-layout-only')
    cfg['report']['title']='RNA-seq 布局验证（非独立生物学分析）'
    cfg['report']['pdf'].update(sample_rows=100,qc_rows=100,enrichment_top_n=10)
    original_samples=pd.read_csv(data/'index/sample.csv')
    variants=[]
    for repeat in range(6):
        frame=original_samples.copy()
        frame['sample_name']=frame['sample_name'].map(lambda name:f'sample_{name}_rep{repeat+1:02d}_long_identifier')
        frame['sample']=frame['sample_name']+'_raw'
        variants.append(frame)
    samples=pd.concat(variants,ignore_index=True)
    samples.to_csv(data/'index/sample.csv',index=False)
    aliases=[]
    for repeat,frame in enumerate(variants):
        mapping={}
        for (_,original),(_,new) in zip(original_samples.iterrows(),frame.iterrows()):
            mapping[str(original['sample'])]=str(new['sample'])
            mapping[str(original['sample_name'])]=str(new['sample_name'])
        aliases.append(mapping)
    def rename(name, alias):
        for source in sorted(alias,key=len,reverse=True):
            if str(name).startswith(source):return alias[source]+str(name)[len(source):]
        return str(name)
    tpm=pd.read_csv(data/'index/merge_rsem_tpm.tsv',sep='\t',index_col=0)
    pd.concat([tpm.rename(columns=alias) for alias in aliases],axis=1).to_csv(data/'index/merge_rsem_tpm.tsv',sep='\t')
    for relative in ['index/multiqc_qc_general_stats.txt','index/multiqc_mapping_general_stats.txt','fastp_trim_report/multiqc_general_stats.txt']:
        source=pd.read_csv(data/relative,sep='\t')
        frames=[]
        for alias in aliases:
            frame=source.copy();frame['Sample']=frame['Sample'].map(lambda v:rename(v,alias));frames.append(frame)
        pd.concat(frames,ignore_index=True).to_csv(data/relative,sep='\t',index=False)
    for path in data.rglob('multiqc_data.json'):
        source=json.loads(path.read_text())
        for plot in source.get('report_plot_data',{}).values():
            for dataset in plot.get('datasets',[]):
                if 'lines' in dataset:
                    original=dataset['lines'];lines=[]
                    for alias in aliases:
                        for line in original:
                            item=copy.deepcopy(line);item['name']=rename(item.get('name',''),alias);lines.append(item)
                    dataset['lines']=lines
                if 'samples' in dataset:
                    original=dataset['samples'];dataset['samples']=[rename(v,alias) for alias in aliases for v in original]
                    for cat in dataset.get('cats',[]):
                        for key in ['data','data_pct']:
                            if key in cat:cat[key]=cat[key]*len(aliases)
        path.write_text(json.dumps(source))
    pd.DataFrame({'Control':[1,2],'Treat':[2,1]}).to_csv(data/'index/contrasts.csv',index=False)
    deg=pd.read_csv(data/'res/DEG/2_vs_1_DEG.csv')
    deg['log2FoldChange']=-deg['log2FoldChange']
    deg.to_csv(data/'res/DEG/1_vs_2_DEG.csv',index=False)
    for direction,opposite in [('UP','DOWN'),('DOWN','UP')]:
        frame=pd.read_csv(data/f'res/Enrichments/2_vs_1_{direction}.csv')
        # Only labels change; the plotted ratio/count/P values remain the example values.
        frame['Description']=frame['Description'].map(lambda label:'长标签排版验证 '+str(label)+' involving coordinated regulation of cellular processes and multiple interacting molecular components across experimental conditions')
        frame.to_csv(data/f'res/Enrichments/2_vs_1_{direction}.csv',index=False)
        frame.to_csv(data/f'res/Enrichments/1_vs_2_{opposite}.csv',index=False)
    (destination/'many-samples.json').write_text(json.dumps(cfg,ensure_ascii=False,indent=2))
    missing=copy.deepcopy(cfg)
    missing['input_files']['enrichment_dir']=str(destination/'no-enrichment')
    (destination/'no-enrichment').mkdir(exist_ok=True)
    missing['report']['modules']=['rna.workflow','rna.results.enrichment','about']
    (destination/'missing-enrichment.json').write_text(json.dumps(missing,ensure_ascii=False,indent=2))
    missing_deg=copy.deepcopy(cfg)
    missing_deg['input_files']['deg_dir']=str(destination/'no-deg')
    (destination/'no-deg').mkdir(exist_ok=True)
    missing_deg['report']['modules']=['rna.results.deg']
    (destination/'missing-deg.json').write_text(json.dumps(missing_deg,ensure_ascii=False,indent=2))
    full=json.loads((ROOT/'tests/report.rna.pdf.json').read_text())
    full['input_files']['data_dir']=str(ROOT/'examples/rna-seq/data')
    full['report']['modules']=['rna.workflow','rna.qc.fastp','about']
    full['report']['pdf']['qc_detail']='all'
    (destination/'full-qc.json').write_text(json.dumps(full,ensure_ascii=False,indent=2))
    print(destination)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-o','--output',type=Path,default=ROOT/'output/pdf-stress')
    create(parser.parse_args().output)
