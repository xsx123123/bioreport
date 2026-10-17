"""Evidence-based result summaries and compact PDF previews."""
from pathlib import Path
import pandas as pd
from .render_output import show_print_table, typst_note


def preview(frame, path, sort_by=None, limit=10, columns=None, *, evidence=None, caption=None):
    from decimal import Decimal
    from ..config import display_path
    total = len(frame)
    if sort_by in ['pvalue','padj','p.adjust','qvalue']:
        ordered = frame.copy()
        ordered['_sort_probability'] = ordered[sort_by].map(
            lambda value: Decimal('Infinity') if pd.isna(value) else Decimal(str(value)))
        if 'log2FoldChange' in ordered:
            ordered['_sort_abs_log2fc'] = pd.to_numeric(
                ordered['log2FoldChange'], errors='coerce').abs().fillna(-float('inf'))
            ordered = ordered.sort_values(
                ['_sort_probability', '_sort_abs_log2fc'], ascending=[True, False],
                kind='stable', na_position='last').drop(columns=['_sort_probability', '_sort_abs_log2fc'])
        else:
            ordered = ordered.sort_values('_sort_probability', kind='stable', na_position='last').drop(columns='_sort_probability')
    else:
        ordered = frame.sort_values(sort_by, kind='stable', na_position='last') if sort_by else frame
    if columns: ordered = ordered[[c for c in columns if c in ordered]]
    show_print_table(ordered, limit=limit, caption=caption, evidence={"source":str(path), "indices":list(ordered.head(limit).index), **(evidence or {})})
    order_note = (f'{sort_by} 升序、同值按 |log2FC| 降序' if sort_by in ['pvalue','padj','p.adjust','qvalue']
                  else sort_by or '输入顺序')
    typst_note(f"预览 {min(limit,total)} / {total} 行；排序：{order_note}。完整结果（数据目录内相对路径）：{display_path(path)}")


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


def apply_gene_annotation(frame, config, id_columns=None):
    """Optionally add symbols from a declared two-column annotation file."""
    from bioreport.config import resolve_path
    annotation = config.get('input_files', {}).get('gene_annotation_file')
    if not annotation:
        return frame
    path = resolve_path(config, annotation)
    if path is None or not path.is_file():
        raise FileNotFoundError(f'Gene annotation file not found: {annotation}')
    mapping = pd.read_csv(path, sep=None, engine='python')
    id_col = next((c for c in ('gene_id', 'Gene ID', 'ENSEMBL', 'gene') if c in mapping), None)
    name_col = next((c for c in ('gene_name', 'gene_symbol', 'Symbol', 'symbol', 'MGI Symbol') if c in mapping), None)
    if not id_col or not name_col:
        raise ValueError('gene_annotation_file must contain gene_id and gene_name columns')
    ids = id_columns or ('Gene ID', 'ENSEMBL', 'gene_id', 'Gene')
    source = next((c for c in ids if c in frame), None)
    if source is None:
        return frame
    result = frame.copy()
    lookup = mapping.dropna(subset=[id_col, name_col]).drop_duplicates(id_col).set_index(id_col)[name_col]
    result['Symbol'] = result[source].map(lookup)
    return result


def deg_counts(frame, fc, p):
    values = frame[['log2FoldChange','pvalue']].apply(pd.to_numeric,errors='coerce')
    return (int(((values.log2FoldChange > fc)&(values.pvalue < p)).sum()),
            int(((values.log2FoldChange < -fc)&(values.pvalue < p)).sum()))


def deg_padj_count(frame, padj_cutoff=.05):
    """Count adjusted P values below the cutoff, or return None if unavailable."""
    if 'padj' not in frame:
        return None
    values = pd.to_numeric(frame['padj'], errors='coerce')
    if not values.notna().any():
        return None
    return int(values.lt(padj_cutoff).sum())


def settings(project):
    return project.get('report',{}).get('pdf',{})


def enrichment_chunks(frame, max_rows=15, line_budget=40, wrap_width=28):
    """Top 12/15 常规情况合并为单张气泡图；仅极端长标签密度时分图。"""
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
        return {'项目':label, '数值':f'{values.mean():.2f}%', '统计口径':f'{len(values)} 个有效样本的算术均值；比例输入转换为百分比'}
    group_col = next((c for c in samples if c.lower() == 'group'), None)
    return pd.DataFrame([
        {'项目':'样本数', '数值':str(len(samples)), '统计口径':'样本表记录数'},
        {'项目':'分组数', '数值':str(samples[group_col].nunique()) if group_col else 'NA', '统计口径':'样本表中非缺失分组的唯一值数'},
        mean(qc, 'fastp-after_filtering_q30_rate', '平均 Q30'),
        mean(mapping, 'star-mapped_percent', '平均比对率'),
        {'项目':'检出基因数', '数值':str(int(tpm.apply(pd.to_numeric, errors='coerce').gt(1).any(axis=1).sum())), '统计口径':'表达矩阵中至少一个样本 TPM > 1 的基因数'},
    ])


def deg_metric_label(comparison):
    """KPI 卡片中差异基因数的统一标签；摘要章与内容校验共用，避免标签漂移。"""
    return f'{comparison} 差异基因数'


def comparison_summaries(config, *, detailed=True):
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
        row = {'比较组':comp, '上调':up, '下调':down}
        if detailed:
            padj_count = deg_padj_count(frame)
            row.update({'满足阈值差异基因':up + down,
                        'padj<0.05 基因数':padj_count if padj_count is not None else 'NA',
                        '参与检验的基因总数':len(frame)})
        else:
            row['参与检验的基因总数'] = len(frame)
        rows.append(row)
    return pd.DataFrame(rows)


def qc_reference_summaries(config):
    """Build the PDF QC reference comparison from final sample-level MultiQC rows."""
    files = config['input_files']
    samples = pd.read_csv(files['sample_file'])
    aliases = {str(v) for col in ('sample', 'sample_name', 'Sample')
               if col in samples for v in samples[col].dropna()}

    def values(path_key, column, *, scale=1):
        path = files.get(path_key)
        if not path or not Path(path).is_file():
            return pd.Series(dtype=float)
        frame = pd.read_csv(path, sep='\t')
        if 'Sample' in frame:
            frame = frame[frame['Sample'].astype(str).isin(aliases)].drop_duplicates('Sample')
        return pd.to_numeric(frame[column], errors='coerce').dropna() * scale if column in frame else pd.Series(dtype=float)

    def span(series, suffix='%'):
        return 'NA' if series.empty else f'{series.min():.1f}–{series.max():.1f}{suffix}'

    def avg(series):
        return 'NA' if series.empty else f'{series.mean():.2f}%'

    qc = config.get('analysis', {}).get('qc_reference', {})
    q30 = values('qc_file', 'fastp-after_filtering_q30_rate')
    if not q30.empty and q30.max() <= 1:
        q30 *= 100
    mapping = values('mapping_file', 'star-mapped_percent')
    unique = values('mapping_file', 'star-uniquely_mapped_percent')
    depth = values('mapping_file', 'star-total_reads')
    duplication = values('fastp_stats_file', 'fastp-pct_duplication')
    gc = values('fastp_stats_file', 'fastp-after_filtering_gc_content')
    retained = values('fastp_stats_file', 'fastp-pct_surviving')
    ratio = depth.max() / depth.min() if len(depth) >= 2 and depth.min() > 0 else None
    rows = []
    def add(label, reference, value, ok):
        rows.append({'指标':label, '常见参考范围':reference, '本次值':value,
                     '是否在常见范围':ok if value != 'NA' else '无法判断'})
    add('平均 Q30', f"≥ {qc.get('q30_min', 85):g}%", avg(q30), '是' if not q30.empty and q30.mean() >= qc.get('q30_min', 85) else '否')
    add('平均比对率', f"≥ {qc.get('mapping_min', 80):g}%", avg(mapping), '是' if not mapping.empty and mapping.mean() >= qc.get('mapping_min', 80) else '否')
    add('重复率 Dup', f"< {qc.get('duplication_max', 20):g}%（视文库类型）", span(duplication), '是' if not duplication.empty and duplication.max() < qc.get('duplication_max', 20) else '部分偏高' if not duplication.empty else '无法判断')
    add('GC 含量', '与物种预期一致', span(gc), '需结合物种判断' if not gc.empty else '无法判断')
    add('过滤保留率 Retained', f"≥ {qc.get('retained_min', 90):g}%", span(retained), '是' if not retained.empty and retained.min() >= qc.get('retained_min', 90) else '否')
    add('Unique 比对率', f"≥ {qc.get('unique_min', 80):g}%", span(unique), '是' if not unique.empty and unique.min() >= qc.get('unique_min', 80) else '否')
    depth_cutoff = config.get('analysis', {}).get('depth', {}).get('ratio_cutoff', 1.5)
    add('测序深度均衡 max/min', f"< {depth_cutoff:g}", 'NA' if ratio is None else f'{ratio:.1f}', '是' if ratio is not None and ratio < depth_cutoff else '否' if ratio is not None else '无法判断')
    return pd.DataFrame(rows)
