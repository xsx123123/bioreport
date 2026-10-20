"""Render the same enrichment result records in HTML and PDF."""


def render_enrichment(config, comparisons, display_ai, *, pdf=False, english=False):
    import pandas as pd
    from IPython.display import display, Markdown
    from .enrichment import enrichment_results
    from .utils.render_output import show_figure, typst_note, figure_group
    from .utils.visualize_utils import display_gene_expression_table
    from .utils.pdf_results import preview, enrichment_chunks, raw_probability_columns
    from .config import display_path
    from omics.rna.analysis.enrichment_plotly import draw_fancy_dotplot, parse_gene_ratios
    from contextlib import nullcontext
    def markdown(body):
        # Quarto concatenates consecutive as-is display outputs. Separate every
        # block so headings and fenced divs cannot become paragraph text.
        display(Markdown('\n\n' + body + '\n\n'))

    results = list(enrichment_results(config, comparisons))
    count = config.get('analysis', {}).get('enrichment', {}).get('top_n', 12)
    databases = list(dict.fromkeys(r.database for r in results))
    for database in databases:
        heading = database or ('Enrichment' if english else '功能富集')
        markdown(f'### {heading}')
        if not pdf:
            markdown(':::: {.panel-tabset .enrichment-comparisons}')
        current_comparison = None
        for result in (r for r in results if r.database == database):
            title = f'{result.comparison} {result.direction}'
            if pdf:
                markdown(f'#### {title}')
            else:
                if result.comparison != current_comparison:
                    if current_comparison is not None:
                        markdown(':::')
                    current_comparison = result.comparison
                    markdown(f'#### {result.comparison}')
                    markdown('::: {.panel-tabset .enrichment-directions}')
                label = ({'UP':'Upregulated (UP)', 'DOWN':'Downregulated (DOWN)'} if english else
                         {'UP':'上调（UP）', 'DOWN':'下调（DOWN）'})[result.direction]
                markdown(f'##### {label}')
            if result.status != 'available':
                statuses = ({'no_results':'No significant enrichment', 'unavailable':'Results not supplied',
                             'disabled':'Analysis disabled', 'failed':'Upstream analysis failed'} if english else
                            {'no_results':'无显著富集结果', 'unavailable':'未提供结果',
                             'disabled':'未启用分析', 'failed':'上游分析失败'})
                message = statuses.get(result.status, result.status)
                markdown(message + (': ' + '; '.join(result.messages) if result.messages else ''))
                continue
            frame = result.frame()
            if pdf:
                source = display_path(result.path, config) if result.path else 'enrichment terms'
                markdown((f'{database} {title}: source {source}. Terms are selected using adjusted P < {result.cutoff} and ranked by adjusted P; up to {count} terms are shown.' if english else
                          f'{database} {title}：数据来自 {source}。按校正后 P < {result.cutoff} 筛选并依显著性排序，最多展示 {count} 个条目。'))
            filtered = frame[pd.to_numeric(frame['p.adjust'], errors='coerce') < result.cutoff].sort_values('p.adjust', kind='stable')
            valid = parse_gene_ratios(filtered['GeneRatio']).notna() & pd.to_numeric(filtered['Count'], errors='coerce').ge(0)
            chosen = filtered[valid].head(count).copy()
            chosen['Count'] = pd.to_numeric(chosen['Count'])
            if not pdf:
                display_gene_expression_table(frame)
            if chosen.empty:
                message = (f'No valid terms with adjusted P < {result.cutoff}.' if english else
                           f'无满足校正后 P < {result.cutoff} 的有效富集条目。')
                markdown(message)
                continue
            evidence = {'kind':'enrichment','database':database,'comparison':result.comparison,
                        'direction':result.direction,'top_n':count,'p_cutoff':result.cutoff}
            pieces = list(enrichment_chunks(chosen)) if pdf else [(0, chosen)]
            for part, (start, chunk) in enumerate(pieces):
                group = f'enrichment-{database}-{result.comparison}-{result.direction}'
                with figure_group(group) if pdf and part == len(pieces)-1 else nullcontext():
                    fig, options = draw_fancy_dotplot(chunk, top_n=None, p_cutoff=None, height_num=450 if pdf else 600, width_num=1000, wrap_width=28)
                    fig.update_layout(coloraxis_cmin=float(chosen['p.adjust'].min()), coloraxis_cmax=float(chosen['p.adjust'].max()),
                                      meta={**(fig.layout.meta or {}),'count_max':int(chosen['Count'].max())})
                    caption = (f'{database} {title} enrichment, terms {start+1}–{start+len(chunk)} of {len(chosen)}; Top {count}. Bubble area: Count; color: adjusted P.' if english else
                               f'{database} {title}富集分析，Top {count} 中条目 {start+1}–{start+len(chunk)}（实际展示 {len(chosen)}）。气泡面积对应 Count，颜色对应校正后 P 值。')
                    show_figure(fig, config=options, evidence={**evidence,'indices':list(chunk.index)}, caption=caption)
                    if pdf and part == len(pieces)-1:
                        source = result.path or (config.get('_config_path', '') + '#enrichment')
                        raw = raw_probability_columns(result.path, frame) if result.path else frame
                        preview(raw.loc[chosen.index], source, sort_by='p.adjust', limit=count,
                                caption=f'{database} {title}', columns=['Description','GeneRatio','Count','p.adjust'],
                                evidence=evidence)
            message = (f'{len(filtered)} / {len(frame)} terms meet adjusted P < {result.cutoff}; {len(chosen)} shown.' if english else
                       f'{len(filtered)} / {len(frame)} 个条目满足校正后 P < {result.cutoff}；展示前 {len(chosen)} 个。')
            if pdf:
                typst_note(message)
            else:
                markdown(message)
            if result.full_table:
                markdown(('Full results: ' if english else '完整结果：') + display_path(result.full_table, config))
            display_ai(result.result_id)
        if not pdf:
            if current_comparison is not None:
                markdown(':::')
            markdown('::::')
