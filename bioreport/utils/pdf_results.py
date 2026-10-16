"""Evidence-based result summaries and compact PDF previews."""
from pathlib import Path
import pandas as pd
from .render_output import show_print_table, typst_note


def preview(frame, path, sort_by=None, limit=10, columns=None, *, evidence=None):
    from decimal import Decimal
    from ..config import display_path
    total = len(frame)
    if sort_by in ['pvalue','padj','p.adjust','qvalue']:
        ordered = frame.sort_values(sort_by, kind='stable', na_position='last',
            key=lambda values: values.map(lambda value:Decimal('Infinity') if pd.isna(value) else Decimal(str(value))))
    else:
        ordered = frame.sort_values(sort_by, kind='stable', na_position='last') if sort_by else frame
    if columns: ordered = ordered[[c for c in columns if c in ordered]]
    show_print_table(ordered, limit=limit, evidence={"source":str(path), "indices":list(ordered.head(limit).index), **(evidence or {})})
    typst_note(f"预览 {min(limit,total)} / {total} 行；排序：{sort_by or '输入顺序'}。完整结果（数据目录内相对路径）：{display_path(path)}")


def raw_probability_columns(path, frame):
    """Preserve P-value literals for display, including values below float range."""
    columns = [c for c in ['pvalue','padj','p.adjust','qvalue'] if c in frame]
    raw = pd.read_csv(path, dtype={c:'string' for c in columns})
    result = frame.copy()
    for column in columns: result[column] = raw.loc[result.index,column]
    return result


def gene_columns(frame):
    """Do not relabel Ensembl identifiers as biological gene symbols."""
    frame = frame.copy()
    id_col = next((c for c in ['ENSEMBL','GeneID','gene_id','Gene'] if c in frame),None)
    if id_col:frame=frame.rename(columns={id_col:'Gene ID'})
    if 'Symbol' in frame:
        values = frame['Symbol'].dropna().astype(str)
        if values.empty and 'Gene ID' in frame:
            frame = frame.drop(columns=['Symbol'])
        elif not values.empty and values.str.match(r'^ENS[A-Z]*G\d+').all():
            if 'Gene ID' not in frame: frame=frame.rename(columns={'Symbol':'Gene ID'})
            else: frame=frame.drop(columns=['Symbol'])
        else:
            is_id = frame['Symbol'].astype('string').str.match(r'^ENS[A-Z]*G\d+', na=False)
            if is_id.any():
                if 'Gene ID' not in frame: frame['Gene ID'] = pd.NA
                frame.loc[is_id & frame['Gene ID'].isna(),'Gene ID'] = frame.loc[is_id,'Symbol']
                frame.loc[is_id,'Symbol'] = pd.NA
    return frame


def deg_counts(frame, fc, p):
    values = frame[['log2FoldChange','pvalue']].apply(pd.to_numeric,errors='coerce')
    return (int(((values.log2FoldChange > fc)&(values.pvalue < p)).sum()),
            int(((values.log2FoldChange < -fc)&(values.pvalue < p)).sum()))


def settings(project):
    return project.get('report',{}).get('pdf',{})


def enrichment_chunks(frame, max_rows=8, line_budget=18, wrap_width=28):
    from omics.rna.analysis.enrichment_plotly import wrap_label
    start, lines = 0, 0
    for position, label in enumerate(frame['Description']):
        needed = wrap_label(label, wrap_width).count('<br>') + 1
        if position > start and (position-start >= max_rows or lines+needed > line_budget):
            yield start, frame.iloc[start:position]
            start, lines = position, 0
        lines += needed
    if start < len(frame): yield start, frame.iloc[start:]


def ordered_samples(metadata, matrix_columns=None):
    """Use metadata group order and original within-group order, not TPM order."""
    if matrix_columns is not None:
        sample_col = max(metadata.columns, key=lambda c: metadata[c].astype(str).isin(matrix_columns).sum())
        if not metadata[sample_col].astype(str).isin(matrix_columns).any():
            raise ValueError('Sample metadata does not match expression matrix columns')
    else:
        sample_col = next((c for c in ['sample_name', 'sample', 'Sample'] if c in metadata), metadata.columns[0])
    group_col = next((c for c in metadata if c.lower() in ['group', 'condition', 'type']), None)
    ordered = metadata.assign(**{group_col: metadata[group_col].astype(str)}).sort_values(group_col, kind='stable') if group_col else metadata
    names = ordered[sample_col].astype(str).tolist()
    return [n for n in names if matrix_columns is None or n in matrix_columns]


def summary_metrics(config):
    """Actual input-derived indicators, with denominators and missing evidence."""
    files = config['input_files']
    samples = pd.read_csv(files['sample_file'])
    qc = pd.read_csv(files['qc_file'], sep='\t')
    mapping = pd.read_csv(files['mapping_file'], sep='\t')
    tpm = pd.read_csv(files['tpm_file'], sep='\t', index_col=0)
    aliases = {str(v) for c in ['sample', 'sample_name', 'Sample'] if c in samples for v in samples[c]}
    def final_rows(frame):
        if 'Sample' not in frame:
            raise ValueError('MultiQC summary must contain a Sample column')
        return frame[frame.Sample.astype(str).isin(aliases)].drop_duplicates('Sample')
    qc, mapping = final_rows(qc), final_rows(mapping)
    def mean(frame, column, label):
        values = pd.to_numeric(frame[column], errors='coerce').dropna() if column in frame else pd.Series(dtype=float)
        if values.empty: return {'项目':label, '数值':'NA', '统计口径':'未提供有效输入值，不按零处理'}
        if values.between(0, 1).all(): values = values * 100
        return {'项目':label, '数值':f'{values.mean():.2f} %', '统计口径':f'{len(values)} 个有效样本的算术均值；比例输入转换为百分比'}
    group_col = next((c for c in samples if c.lower() == 'group'), None)
    return pd.DataFrame([
        {'项目':'样本数', '数值':str(len(samples)), '统计口径':'样本表记录数'},
        {'项目':'分组数', '数值':str(samples[group_col].nunique()) if group_col else 'NA', '统计口径':'样本表中非缺失分组的唯一值数'},
        mean(qc, 'fastp-after_filtering_q30_rate', '平均 Q30'),
        mean(mapping, 'star-mapped_percent', '平均比对率'),
        {'项目':'检出基因数', '数值':str(int(tpm.apply(pd.to_numeric, errors='coerce').gt(1).any(axis=1).sum())), '统计口径':'表达矩阵中至少一个样本 TPM > 1 的基因数'},
    ])


def comparison_summaries(config):
    from bioreport.modules import selected_modules
    from bioreport.registry import get_registry
    from .report_utils import get_comparisons_from_csv, get_file_path
    selected = [get_registry().canonical(m) for m in selected_modules(config)]
    if not any(m in selected for m in ['rna.results', 'rna.results.deg']):
        return pd.DataFrame()
    files = config['input_files']
    fc = config.get('analysis', {}).get('deg', {}).get('log2fc_threshold', 1.)
    p = config.get('analysis', {}).get('deg', {}).get('pvalue_threshold', .05)
    rows = []
    for comp in get_comparisons_from_csv(files['contrasts_file']):
        path = get_file_path({'files': config.get('files', {})}, f'{comp}_DEG.csv', local_base_dir=files['deg_dir'])
        if not path or not Path(path).is_file():
            raise FileNotFoundError(f'Missing DEG result: {comp}')
        frame = pd.read_csv(path)
        up, down = deg_counts(frame, fc, p)
        rows.append({'比较组':comp, '上调':up, '下调':down, '总记录数':len(frame)})
    return pd.DataFrame(rows)
