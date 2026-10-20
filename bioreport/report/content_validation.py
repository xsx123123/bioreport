"""Compare emitted semantic evidence with freshly read analysis inputs."""
from collections import defaultdict
import json
from pathlib import Path
import pandas as pd


def validate_content(config, manifest):
    from bioreport.utils.pdf_results import summary_metrics, comparison_summaries, deg_counts, deg_metric_label
    from omics.rna.analysis.enrichment_plotly import parse_gene_ratios
    blocks = [json.loads(line) for line in Path(manifest).read_text().splitlines() if line.strip()]
    errors = []
    checks = []
    files = config['input_files']
    def check(name, actual, expected):
        checks.append({'check':name,'actual':actual,'expected':expected})
        if actual != expected: errors.append(checks[-1])
    metrics = next((b for b in blocks if b['id']=='executive-metrics'), None)
    if metrics is not None:
        expected = {r['项目']:r['数值'] for _,r in summary_metrics(config).iterrows()}
        actual = dict(metrics['content'])
        for label,value in expected.items(): check('metric:'+label,actual.get(label),value)
        for _,row in comparison_summaries(config).iterrows():
            check('metric:DEG:'+row['比较组'],actual.get(deg_metric_label(row['比较组'])),str(row['上调']+row['下调']))
    deg = config.get('analysis',{}).get('deg',{})
    enriched = defaultdict(lambda: {'figures':[], 'tables':[]})
    for block in blocks:
        evidence = block.get('content')
        if not isinstance(evidence,dict): continue
        if evidence.get('kind')=='software_versions':
            from bioreport.software import software_records
            source=software_records(config)
            versions=dict(zip(source.Software.astype(str),source.Version.astype(str)))
            index=block['headers'].index('Version')
            for row in block['rows']:
                check('software_version:'+row[0],row[index],versions.get(row[0]))
        if evidence.get('kind')=='input_paths':
            from bioreport.config import display_path
            check('input_paths',block['rows'],[[key,display_path(value,config)] for key,value in files.items() if key!='data_dir'])
        if evidence.get('kind')=='sha256':
            from bioreport.utils.provenance import input_checksums
            from bioreport.config import display_path
            check('sha256_table',[[cell.replace('\u200b','') for cell in row] for row in block['rows']],
                  [[key,display_path(files[key],config),digest] for key,digest in input_checksums(config).items()])
        if evidence.get('kind')=='samples':
            source = pd.read_csv(files['sample_file'])
            check('sample_count',evidence['sample_count'],len(source))
            check('sample_preview_count',len(block['rows']),min(len(source),config.get('report',{}).get('pdf',{}).get('sample_rows',30)))
        if evidence.get('kind')=='pca':
            source = pd.read_csv(files['sample_file'])
            name = 'sample_name' if 'sample_name' in source else source.columns[0]
            check('pca_samples',sorted(evidence['samples']),sorted(source[name].astype(str)))
        if evidence.get('kind')=='deg' and block['type']=='figure':
            from bioreport.utils.report_utils import get_file_path
            source = get_file_path({'files':config.get('files',{})},evidence['comparison']+'_DEG.csv',local_base_dir=files['deg_dir'])
            up,down = deg_counts(pd.read_csv(source),deg.get('log2fc_threshold',1),deg.get('pvalue_threshold',.05))
            check('deg_counts:'+evidence['comparison'],[evidence['up'],evidence['down']],[up,down])
            from bioreport.i18n import language
            expected_caption = f'Upregulated {up}, downregulated {down}' if language(config) == 'en' else f'上调 {up}、下调 {down}'
            check('deg_caption:'+evidence['comparison'], expected_caption in block['caption'], True)
        if evidence.get('kind')=='enrichment':
            identity = (evidence['comparison'],evidence.get('database',''),evidence['direction'])
            enriched[identity]['figures' if block['type']=='figure' else 'tables'].append(block)
    from bioreport.modules import selected_modules
    from bioreport.registry import get_registry
    modules = [get_registry().canonical(m) for m in selected_modules(config)]
    from bioreport.enrichment import enrichment_results
    sources = {r.identity:r for r in enrichment_results(config)} if any(
        m in modules for m in ('rna.results','rna.results.enrichment')) else {}
    for identity, result in sources.items():
        if result.status == 'available':
            frame = result.frame()
            if (frame['p.adjust'] < result.cutoff).any():
                enriched[identity]
    for identity, group in enriched.items():
        comp,database,direction=identity
        result = sources.get(identity)
        if result is None:
            check('enrichment_unknown_source:'+str(identity), False, True)
            continue
        frame = result.frame()
        cfg = config['analysis']['enrichment']
        selected = frame[frame['p.adjust'] < result.cutoff].sort_values('p.adjust',kind='stable')
        valid = parse_gene_ratios(selected.GeneRatio).notna() & pd.to_numeric(selected.Count,errors='coerce').ge(0)
        expected = selected[valid].head(cfg['top_n'])
        actual = [i for b in group['figures'] for i in b['content']['indices']]
        check(f'enrichment_figure_indices:{comp}:{direction}',actual,list(expected.index))
        tables = group['tables']
        check(f'enrichment_table_count:{comp}:{direction}',len(tables),1 if len(expected) else 0)
        if tables:
            table = tables[0]
            check(f'enrichment_table_indices:{comp}:{direction}',table['content']['indices'],list(expected.index))
            check(f'enrichment_table_terms:{comp}:{direction}',[r[0] for r in table['rows']],list(expected.Description.astype(str)))
        for block in group['figures']+tables:
            check(f'top_n:{block["id"]}',block['content']['top_n'],cfg['top_n'])
    # Require evidence for enabled output modules; absence is a failure, not a pass.
    from bioreport.registry import get_registry
    from bioreport.modules import selected_modules
    selected = [get_registry().canonical(m) for m in selected_modules(config)]
    if 'rna.index' in selected:
        check('executive_summary_present',metrics is not None,True)
        check('sample_table_present',any((b.get('content') or {}).get('kind')=='samples' for b in blocks if isinstance(b.get('content'),dict)),True)
    if any(m in selected for m in ('rna.results','rna.results.deg')):
        from bioreport.utils.report_utils import get_comparisons_from_csv
        expected=get_comparisons_from_csv(files['contrasts_file'])
        actual=[b['content']['comparison'] for b in blocks if b['type']=='figure' and isinstance(b.get('content'),dict) and b['content'].get('kind')=='deg']
        check('deg_figure_comparisons',sorted(actual),sorted(expected))
    if any(m in selected for m in ('rna.results','rna.results.samples')):
        check('pca_evidence_present',any((b.get('content') or {}).get('kind')=='pca' for b in blocks if isinstance(b.get('content'),dict)),True)
    return {'status':'FAIL' if errors else 'PASS','checks':checks,'errors':errors}
