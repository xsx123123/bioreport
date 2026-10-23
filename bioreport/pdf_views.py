"""Emit prepared PDF results in their original scientific and display order."""
from contextlib import nullcontext
from dataclasses import asdict

from .pdf_parallel import prepared_results, worker_count


def _emit_panels(panels, caption, evidence):
    from .utils.render_output import show_prepared_figure
    for panel in panels:
        show_prepared_figure(panel['path'], caption, evidence=evidence, detail=panel['detail'])


def _emit_preview(table, path, *, sort_by, caption, evidence):
    import pandas as pd
    from .utils.pdf_results import preview
    frame = pd.DataFrame(table['data'], columns=table['columns'], index=table['index'])
    preview(frame, path, sort_by=sort_by, limit=table['limit'], total_rows=table['total'],
            caption=caption, evidence=evidence)


def _progress(label, index, total, name):
    from .result_progress import report_result_progress
    report_result_progress(label, 'render', index, total, name)
    if index == 1 or index == total or index % 10 == 0:
        from loguru import logger
        logger.info('PDF {} [{}/{}]: {}', label, index, total, name)


def render_pdf_deg(config, comparisons, display_ai, *, english=False):
    from IPython.display import display, Markdown
    from .utils.render_output import typst_note
    from .utils.report_utils import get_file_path
    if not comparisons:
        typst_note('No valid comparisons; differential expression plots are omitted.' if english
                   else '比较组表没有有效记录；不生成差异表达图表。')
        return
    # Workers need plotting settings and the optional gene annotation, not all
    # enrichment records or expression matrices in the project configuration.
    parameters = {
        'analysis': {key: config.get('analysis', {}).get(key, {}) for key in ('deg', 'volcano')},
        'report': {'pdf': config.get('report', {}).get('pdf', {})},
        'input_files': {key: value for key, value in config.get('input_files', {}).items()
                        if key in ('gene_annotation_file', 'data_dir')},
        '_path_base': config.get('_path_base', '.'),
        '_config_path': config.get('_config_path', ''),
    }
    jobs = []
    for comp in comparisons:
        path = get_file_path({'files': config.get('files', {})}, f'{comp}_DEG.csv',
                            local_base_dir=config['input_files'].get('deg_dir'))
        jobs.append({'kind': 'deg', 'label': comp, 'comparison': comp, 'path': path,
                     'config': parameters, 'english': english})
    _progress('DEG', 0, len(jobs), '')
    with prepared_results(jobs, worker_count(config), 'DEG') as results:
        for index, (comp, job, result) in enumerate(zip(comparisons, jobs, results), 1):
            up, down, fc, p = (result[key] for key in ('up', 'down', 'fc', 'p'))
            cap, top = result['cap'], result['annotate_top']
            if english:
                caption = (f'{comp} Differential Expression Volcano Plot. Treat relative to Control; '
                    f'upregulated on the right and downregulated on the left; raw P < {p} and |Log2FC| > {fc}. '
                    f'Upregulated {up}, downregulated {down}. Plotted -log10(P) is capped at {cap} '
                    f'(top label: {cap}+); original pvalue/padj values are retained. '
                    f'The top {top} significant genes per direction have leader-line labels.')
            else:
                caption = (f'{comp} 差异表达火山图。方向为 Treat 相对 Control；右侧上调、左侧下调；'
                    f'原始 P < {p} 且 |Log2FC| > {fc}。上调 {up}、下调 {down}。'
                    f'超出展示上限的 -log10(P) 在绘图层裁剪至 {cap}（顶部标注为“{cap}+”），'
                    f'原始 pvalue/padj 与上游结果保持一致。图中为上调/下调各 Top {top} 显著基因添加基因名引线标注。')
            evidence = {'kind': 'deg', 'comparison': comp, 'up': up, 'down': down}
            _emit_panels(result['panels'], caption, evidence)
            typst_note((f'{comp}: upregulated {up}, downregulated {down}; remaining records do not meet both cutoffs.'
                        if english else f'{comp}：上调 {up}，下调 {down}；其余记录未同时满足上述阈值。'))
            display_ai(f'rna.results.deg__{comp}')
            for table in result['tables']:
                direction = table['direction']
                display(Markdown(f"### {comp} Top {table['limit']} {direction}\n"))
                _emit_preview(table, job['path'], sort_by='pvalue',
                    caption=f'{comp} {direction} ' + ('Differential Gene Preview' if english else '差异表达基因预览'),
                    evidence={'kind': 'deg', 'comparison': comp, 'direction': direction})
            _progress('DEG', index, len(jobs), comp)


def render_pdf_enrichment(config, comparisons, display_ai, *, english=False):
    from IPython.display import display, Markdown
    from .config import display_path
    from .enrichment import enrichment_results
    from .utils.render_output import figure_group, typst_note

    def markdown(body):
        display(Markdown('\n\n' + body + '\n\n'))

    records = list(enrichment_results(config, comparisons))
    databases = list(dict.fromkeys(result.database for result in records))
    records = [result for database in databases for result in records if result.database == database]
    count = config.get('analysis', {}).get('enrichment', {}).get('top_n', 12)
    jobs = [{'kind': 'enrichment', 'label': f'{r.database} {r.comparison} {r.direction}',
             'result': asdict(r), 'top_n': count, 'english': english}
            for r in records if r.status == 'available']
    current_database = None
    _progress('enrichment', 0, len(records), '')
    with prepared_results(jobs, worker_count(config), 'enrichment') as prepared:
        for index, result in enumerate(records, 1):
            database = result.database
            if current_database != database:
                markdown(f"### {database or ('Enrichment' if english else '功能富集')}")
                current_database = database
            title = f'{result.comparison} {result.direction}'
            markdown(f'#### {title}')
            if result.status != 'available':
                statuses = ({'no_results': 'No significant enrichment', 'unavailable': 'Results not supplied',
                             'disabled': 'Analysis disabled', 'failed': 'Upstream analysis failed'} if english else
                            {'no_results': '无显著富集结果', 'unavailable': '未提供结果',
                             'disabled': '未启用分析', 'failed': '上游分析失败'})
                markdown(statuses.get(result.status, result.status)
                         + (': ' + '; '.join(result.messages) if result.messages else ''))
                _progress('enrichment', index, len(records), f'{database} {title}')
                continue
            prepared_result = next(prepared)
            source = display_path(result.path, config) if result.path else 'enrichment terms'
            markdown((f'{database} {title}: source {source}. Terms are selected using adjusted P < {result.cutoff} '
                      f'and ranked by adjusted P; up to {count} terms are shown.' if english else
                      f'{database} {title}：数据来自 {source}。按校正后 P < {result.cutoff} 筛选并依显著性排序，最多展示 {count} 个条目。'))
            chosen = prepared_result['chosen']
            if not chosen:
                markdown((f'No valid terms with adjusted P < {result.cutoff}.' if english
                          else f'无满足校正后 P < {result.cutoff} 的有效富集条目。'))
                _progress('enrichment', index, len(records), f'{database} {title}')
                continue
            evidence = {'kind': 'enrichment', 'database': database, 'comparison': result.comparison,
                        'direction': result.direction, 'top_n': count, 'p_cutoff': result.cutoff}
            pieces = prepared_result['pieces']
            for part, piece in enumerate(pieces):
                final_piece = part == len(pieces) - 1
                group = f'enrichment-{database}-{result.comparison}-{result.direction}'
                with figure_group(group) if final_piece else nullcontext():
                    start, length = piece['start'], piece['count']
                    caption = (f'{database} {title} enrichment, terms {start+1}–{start+length} of {chosen}; '
                               f'Top {count}. Bubble area: Count; color: adjusted P.' if english else
                               f'{database} {title}富集分析，Top {count} 中条目 {start+1}–{start+length}（实际展示 {chosen}）。气泡面积对应 Count，颜色对应校正后 P 值。')
                    _emit_panels(piece['panels'], caption, {**evidence, 'indices': piece['indices']})
                    if final_piece:
                        source = result.path or (config.get('_config_path', '') + '#enrichment')
                        _emit_preview(prepared_result['table'], source, sort_by='p.adjust',
                                      caption=f'{database} {title}', evidence=evidence)
            typst_note((f"{prepared_result['filtered']} / {prepared_result['total']} terms meet adjusted P < {result.cutoff}; {chosen} shown."
                        if english else f"{prepared_result['filtered']} / {prepared_result['total']} 个条目满足校正后 P < {result.cutoff}；展示前 {chosen} 个。"))
            if result.full_table:
                markdown(('Full results: ' if english else '完整结果：') + display_path(result.full_table, config))
            display_ai(result.result_id)
            _progress('enrichment', index, len(records), f'{database} {title}')
