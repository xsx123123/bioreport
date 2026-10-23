"""Describe the sample intersection already used by expression plots."""
import pandas as pd

from bioreport.i18n import language


def expression_sample_scope(matrix_path, metadata_path):
    """Read IDs only; never modify the metadata or choose a different cohort."""
    matrix = pd.read_csv(matrix_path, sep=None, engine='python', index_col=0, nrows=0)
    metadata = pd.read_csv(metadata_path, sep=None, engine='python')
    matrix_ids = list(map(str, matrix.columns))
    available = set(matrix_ids)
    # Match the existing PCA/distribution alignment, including sample aliases.
    column = max(metadata.columns, key=lambda name: len(set(metadata[name].astype(str)) & available))
    declared = list(dict.fromkeys(metadata[column].astype(str)))
    declared_set = set(declared)
    included = [name for name in declared if name in available]
    return {'metadata_column': str(column), 'metadata_samples': declared,
            'matrix_samples': matrix_ids, 'included_samples': included,
            'matrix_only': [name for name in matrix_ids if name not in declared_set],
            'metadata_only': [name for name in declared if name not in available]}


def expression_sample_scope_note(config, *, lang=None):
    files = config['input_files']
    scope = expression_sample_scope(files['tpm_file'], files['sample_file'])
    declared, matrix, included = (len(scope[key]) for key in
                                  ('metadata_samples', 'matrix_samples', 'included_samples'))
    if (lang or language(config)) == 'en':
        note = (f'Sample scope: the sample sheet lists {declared} samples; the TPM matrix contains {matrix}; '
                f'{included} matched samples enter PCA, expression distributions, and HVG heatmaps. '
                'Samples are not randomly subsampled. PDF panels collectively show every included sample.')
        note += ' QC plots retain the samples present in their own upstream summaries; see each figure caption for its scope.'
        if scope['matrix_only']:
            note += (f" Matrix samples absent from the sample sheet ({len(scope['matrix_only'])}) are not included "
                     'in these expression plots: ' + ', '.join(scope['matrix_only']) + '.')
        if scope['metadata_only']:
            note += ' Sample-sheet entries absent from the matrix: ' + ', '.join(scope['metadata_only']) + '.'
    else:
        note = (f'样本范围核对：样本表列出 {declared} 个样本，TPM 矩阵包含 {matrix} 个，'
                f'本节 PCA、表达分布及高变异基因热图使用其中匹配的 {included} 个样本。'
                '不随机抽取样本；PDF 多面板合计展示全部纳入样本。')
        note += '质控图保留各自上游汇总文件中的样本，具体范围见对应图注。'
        if scope['matrix_only']:
            note += (f"矩阵中未列入样本表的 {len(scope['matrix_only'])} 个样本未参与这些表达图："
                     + '、'.join(scope['matrix_only']) + '。')
        if scope['metadata_only']:
            note += '样本表中未在矩阵找到的样本：' + '、'.join(scope['metadata_only']) + '。'
    return note
