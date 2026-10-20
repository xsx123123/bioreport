#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
from pathlib import Path
import plotly.graph_objects as go
from IPython.display import display, Markdown
from bioreport.utils.render_output import show_figure, is_pdf
from typing import Optional, List, Dict, Any



def _qc_config():
    from bioreport.config import load_config
    try:
        return load_config()
    except FileNotFoundError:
        # Standalone plot helpers can operate without a report configuration.
        return {}


def _saved_multiqc_path(directory):
    """Accept a report data directory or its single wrapper directory."""
    path = Path(directory)/'multiqc_data.json'
    if path.is_file():
        return path
    candidates = list(Path(directory).rglob('multiqc_data.json'))
    if len(candidates) > 1:
        raise ValueError(f'Ambiguous MultiQC report directory: {directory}')
    return candidates[0] if candidates else path


def _percent_axis_enabled() -> bool:
    """横轴口径开关：analysis.fastq_screen.axis = percent | reads（默认 reads）。"""
    axis = _qc_config().get('analysis', {}).get('fastq_screen', {}).get('axis', 'reads')
    if axis not in ('reads', 'percent'):
        raise ValueError("analysis.fastq_screen.axis must be 'reads' or 'percent'")
    return axis == 'percent'


def _to_percent(fig):
    """把横向堆叠柱的绝对 Reads 归一化为各样本 100% 占比（仅展示层换算）。"""
    import numpy as np
    totals = None
    for trace in fig.data:
        values = np.asarray(trace.x, dtype=float)
        totals = values if totals is None else totals + np.nan_to_num(values)
    if totals is None or not np.any(totals):
        return fig
    for trace in fig.data:
        trace.x = (np.asarray(trace.x, dtype=float) / totals * 100).tolist()
    fig.update_layout(barmode='stack')
    fig.update_xaxes(range=[0, 100], ticksuffix='%', title_text='各物种比对占比（%，按样本归一化）')
    return fig


def _qualimap_coverage_options() -> Dict[str, Any]:
    """QualiMap 覆盖度曲线展示选项：剔除 0X 无覆盖 bin 与纵轴刻度口径。"""
    options = _qc_config().get('analysis', {}).get('qualimap', {}).get('coverage', {})
    drop_zero = options.get('drop_zero', True)
    yscale = options.get('yscale', 'linear')
    if not isinstance(drop_zero, bool):
        raise ValueError('analysis.qualimap.coverage.drop_zero must be a boolean')
    if yscale not in ('linear', 'log'):
        raise ValueError("analysis.qualimap.coverage.yscale must be 'linear' or 'log'")
    return {'drop_zero': drop_zero, 'yscale': yscale}


def _apply_coverage_options(identifier: str, fig):
    """0X bin 计数可达 1e9，不剔除会把 1X–100X 的有效覆盖压死在轴底。"""
    normalized = identifier.lower().replace('_', ' ').replace('-', ' ')
    if not any(term in normalized for term in ('coverage histogram', 'genome fraction')):
        return fig, ''
    options = _qualimap_coverage_options()
    note = ''
    if options['drop_zero']:
        for trace in fig.data:
            pairs = [(x, y) for x, y in zip(trace.x, trace.y) if float(x) != 0]
            trace.x = [pair[0] for pair in pairs]
            trace.y = [pair[1] for pair in pairs]
        note = '已剔除 0X 无覆盖 bin；'
    if options['yscale'] == 'log':
        fig.update_yaxes(type='log', title_text='Genome bin counts (log10)')
        note += '纵轴为对数刻度；'
    return fig, note


def _dataset_figure(identifier, plot, dataset):
    """Read one saved MultiQC dataset without merging filtering/read stages."""
    from bioreport.utils.print_theme import plain
    config = plot.get('pconfig', {})
    layout = dataset.get('layout', {})
    dconfig = dataset.get('dconfig', {})
    stage = dconfig.get('name', '')
    fig = go.Figure()
    horizontal = dataset.get('trace_params', {}).get('orientation') == 'h'
    if plot.get('plot_type') == 'x/y line':
        for line in dataset.get('lines', []):
            pairs = line.get('pairs', [])
            if pairs:
                fig.add_trace(go.Scatter(x=[v[0] for v in pairs], y=[v[1] for v in pairs],
                    mode='lines', name=line.get('name', 'Sample')))
    elif plot.get('plot_type') == 'bar plot':
        for category in dataset.get('cats', []):
            values = category.get('data', [])
            if not any(v is not None for v in values): continue
            samples = dataset.get('samples', [])
            fig.add_trace(go.Bar(x=values if horizontal else samples,
                y=samples if horizontal else values, orientation='h' if horizontal else 'v',
                name=category['name'], marker_color=category.get('color')))
        fig.update_layout(barmode='stack')
    def axis_title(axis):
        value = (layout.get(axis) or {}).get('title') or {}
        return value.get('text') if isinstance(value,dict) else value
    title = plain(config.get('title') or identifier)+(f'：{stage}' if stage else '')
    is_screen = 'fastq screen' in (identifier + ' ' + title).lower() or 'fastq_screen' in identifier.lower()
    if is_screen and horizontal and len(fig.data) and _percent_axis_enabled():
        fig = _to_percent(fig)
    x_title = axis_title('xaxis') or config.get('xlab') or ''
    fig.update_layout(title=title, template='simple_white', height=500,
        xaxis_title=x_title,
        yaxis_title=axis_title('yaxis') or ('Sample' if plot.get('plot_type')=='bar plot' and horizontal else dconfig.get('ylab') or config.get('ylab') or ''))
    if is_screen and horizontal and len(fig.data) and _percent_axis_enabled():
        fig.update_xaxes(title_text='各物种比对占比（%，按样本归一化）', range=[0, 100], ticksuffix='%')
    if len(fig.data) and all(t.type == 'bar' for t in fig.data):
        # 图例移到图表上方外侧水平排列，避免叠压前两根柱子。
        fig.update_layout(legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0,
            bgcolor='rgba(0,0,0,0)', font=dict(size=9)))
    return fig, title


def _visualize_from_json(analysis_dir: str, target_modules: Optional[List[str]] = None) -> None:
    """Render interactive plots from a saved MultiQC report, including all stages."""
    path = _saved_multiqc_path(analysis_dir)
    with open(path, encoding='utf-8') as handle:
        plots = json.load(handle).get('report_plot_data', {})
    rendered = 0
    for identifier, plot in plots.items():
        title = plot.get('pconfig', {}).get('title') or identifier
        if target_modules and not any(t.lower() in (identifier+' '+title).lower() for t in target_modules):
            continue
        for dataset in plot.get('datasets', []):
            fig, title = _dataset_figure(identifier, plot, dataset)
            if not fig.data: continue
            if 'coverage_histogram' in identifier:
                fig, _ = _prepare_print_qc(fig, identifier, title)
            rendered += 1
            display(Markdown(f'**{title}**'))
            show_figure(fig, config={'displaylogo':False,'toImageButtonOptions':{
                'format':'png','filename':identifier,'height':600,'width':1200,'scale':4}})
    if not rendered:
        raise ValueError(f'No supported QC datasets for {target_modules} in {path}')


def visualize_multiqc_logs(analysis_dir: str, target_modules: Optional[List[str]] = None, plot_captions: Optional[Dict[str, str]] = None) -> None:
    """
    解析指定目录的 MultiQC 日志，并交互式展示 Plotly 图表。
    
    Args:
        analysis_dir (str): MultiQC 数据目录路径。
        target_modules (List[str], optional): 指定只展示哪些模块（例如 ['fastp']）。
                                              如果不填，默认展示所有发现的模块。
        plot_captions (Dict[str, str], optional): 图表说明字典，Key 为 plot_id (例如 'fastp_filtered_reads_plot')，
                                                  Value 为 Markdown 格式的说明文本。
    """
    
    json_path = _saved_multiqc_path(analysis_dir)
    if os.path.isfile(json_path):
        if is_pdf():
            with open(json_path, encoding='utf-8') as source:
                _visualize_pdf_json(json.load(source), analysis_dir, target_modules)
        else:
            _visualize_from_json(analysis_dir, target_modules)
        return
    try:
        import multiqc
    except ImportError:
        _visualize_from_json(analysis_dir, target_modules)
        return

    # --- 🧹 1. 关键步骤：清除 MultiQC 的旧记忆 ---
    try:
        multiqc.reset()
    except AttributeError:
        if hasattr(multiqc, 'report'):
            multiqc.report.data = {}
            multiqc.report.general_stats_data = []

    # --- 🛡️ 2. 路径检查 ---
    if not os.path.exists(analysis_dir):
        if is_pdf():
            raise FileNotFoundError(f'Missing QC directory: {analysis_dir}')
        print(f"❌ 错误：找不到数据目录: {analysis_dir}")
        return
        
    # --- 📂 3. 解析日志 ---
    try:
        multiqc.parse_logs(analysis_dir, quiet=True)
    except Exception as e:
        print(f"⚠️ 解析日志时遇到警告: {e}")
    
    # 获取所有发现的模块
    found_modules = multiqc.list_modules()
    all_plots = multiqc.list_plots()
    
    # --- 🔄 4. Fallback Logic ---
    if not found_modules:
        # 如果解析失败，尝试从 multiqc_data.json 直接加载
        # print(f"⚠️ Parsing logs failed to find modules. Attempting to load from multiqc_data.json...")
        _visualize_from_json(analysis_dir, target_modules)
        return

    # --- 🔍 5. 模块过滤 ---
    if target_modules:
        modules_to_visualize = [m for m in found_modules if m.lower() in [t.lower() for t in target_modules]]
        if not modules_to_visualize:
            if is_pdf():
                raise ValueError(f'QC modules {target_modules} not found in {analysis_dir}; available: {found_modules}')
            # Maybe the user asked for "QualiMap" but it's not found in parsed logs
            # Check JSON fallback as well before giving up? 
            # Often if parse_logs finds SOME modules but not the target, it might be partial parse.
            # But simpler to just warn.
            print(f"⚠️ 警告: 目录中包含 {found_modules}，但没有你指定的 {target_modules}")
            return
    else:
        modules_to_visualize = found_modules

    # --- 🎨 6. 开始绘图 (Standard Method) ---
    source_written = False
    for module_name in modules_to_visualize:
        
        modules_plots = all_plots.get(module_name, [])
        if not modules_plots:
            if is_pdf():
                raise ValueError(f'No QC plots for {module_name} in {analysis_dir}')
            continue

        for item in modules_plots:
            item_name = "Unknown"
            if isinstance(item, str):
                item_name = item
            elif isinstance(item, dict):
                item_name = list(item.keys())[0]
            
            my_config = {
                'toImageButtonOptions': {
                    'format': 'png',
                    'filename': f'{module_name}_{item_name}_plot',
                    'height': 600,
                    'width': 1200,
                    'scale': 4
                },
                'displaylogo': False
            }
            
            try:
                mqc_plot_obj = multiqc.get_plot(module_name, item_name)
                
                if mqc_plot_obj:
                    if is_pdf() and hasattr(mqc_plot_obj, 'model_dump'):
                        serialized = mqc_plot_obj.model_dump(mode='json')
                        _visualize_pdf_json({'report_plot_data':{f'{module_name}_{item_name}':serialized}},
                                            analysis_dir,[module_name],emit_source=not source_written)
                        source_written = True
                        if plot_captions and item_name in plot_captions:
                            from bioreport.utils.render_output import typst_note
                            typst_note(plot_captions[item_name])
                        continue
                    fig = mqc_plot_obj.get_figure(0)
                    if is_pdf():
                        _show_print_qc(fig, item_name, str(fig.layout.title.text or item_name))
                    else:
                        display(Markdown(f"**{module_name}** - **{item_name}** Visualization"))
                        show_figure(fig, config=my_config)
                    
                    # --- 显示图注 (Caption) ---
                    if plot_captions and item_name in plot_captions:
                        display(Markdown(plot_captions[item_name]))
                    
                    # display(Markdown("\n---\n"))
                else:
                    pass
                    
            except Exception as e:
                if is_pdf():
                    raise RuntimeError(f'PDF QC plot failed: {module_name} - {item_name}') from e
                print(f"❌ 绘制失败 [{module_name} - {item_name}]: {e}")


def _prepare_print_qc(fig, identifier, title, *, aggregate=True):
    from bioreport.utils.print_theme import plain
    config = _qc_config()
    detail = config.get('report',{}).get('pdf',{}).get('qc_detail','key')
    key = (str(identifier)+' '+plain(title)).lower()
    if detail != 'all' and not any(value in key for value in [
            'filtered reads', 'filtered_reads', 'sequence quality', 'sequence_quality',
            'mapped reads', 'mapped_reads', 'coverage histogram', 'coverage_histogram',
            'alignment scores', 'alignment_scores', 'star_alignment']):
        return None
    coverage_plot = 'coverage histogram' in key or 'coverage_histogram' in key
    aliases = {}
    sample_file = config.get('input_files', {}).get('sample_file')
    if sample_file and os.path.isfile(sample_file):
        import pandas as pd
        from bioreport.utils.print_theme import group_palette
        from bioreport.utils.pdf_results import ordered_samples
        metadata = pd.read_csv(sample_file)
        if 'group' in metadata:
            palette = group_palette(metadata['group'])
            order = ordered_samples(metadata)
            for _, row in metadata.iterrows():
                for column in ('sample', 'sample_name'):
                    if column in metadata:
                        aliases[str(row[column])] = (str(row.get('sample_name',row[column])),str(row['group']))
            def identity(value):
                for alias in sorted(aliases, key=len, reverse=True):
                    if str(value) == alias or str(value).startswith(alias+'_'):
                        return aliases[alias]
                return str(value), str(value)
            groups = {}
            for trace in fig.data:
                if trace.type == 'scatter':
                    sample, group = identity(trace.name)
                    groups[sample] = group
                    trace.name = sample
                    trace.line.color = palette.get(group, '#4477AA')
                    trace.line.dash = ['solid','dash','dot','dashdot'][order.index(sample)%4] if sample in order else 'solid'
                elif trace.type == 'bar':
                    horizontal = trace.orientation == 'h'
                    values = list(trace.y if horizontal else trace.x)
                    positions = sorted(range(len(values)), key=lambda i: order.index(identity(values[i])[0]) if identity(values[i])[0] in order else len(order))
                    labels = [identity(values[i])[0] for i in positions]
                    groups.update({identity(v)[0]:identity(v)[1] for v in values})
                    numbers = list(trace.x if horizontal else trace.y)
                    if horizontal:
                        trace.y, trace.x = labels, [numbers[i] for i in positions]
                    else:
                        trace.x, trace.y = labels, [numbers[i] for i in positions]
            fig.update_layout(meta={**(fig.layout.meta or {}), 'sample_groups': groups})
            if fig.data and all(t.type=='bar' and t.orientation=='h' for t in fig.data):
                fig.update_yaxes(autorange='reversed')
    is_screen = 'fastq screen' in key or 'fastq_screen' in key
    if is_screen and aggregate:
        from bioreport.utils.print_theme import aggregate_bar_categories
        legend = config.get('analysis', {}).get('fastq_screen', {}).get('legend', {})
        fig = aggregate_bar_categories(fig, **{k: legend[k] for k in
            ('min_fraction','max_categories','aggregate_other') if k in legend})
    coverage_note = ''
    if coverage_plot:
        fig, coverage_note = _apply_coverage_options(identifier, fig)
        fig = _group_coverage(fig)
        coverage_note += '横轴截断至 0–100X；每组曲线为样本均值，色带为 min–max 范围。'
    label = plain(title)
    x = plain(fig.layout.xaxis.title.text)
    y = plain(fig.layout.yaxis.title.text)
    aggregation_note = 'Other 为仅显示层聚合，原始类别完整保留在输入数据中。' if is_screen else ''
    return fig, f"{label}。{coverage_note}横轴：{x or '输入图表坐标'}；纵轴：{y or '输入图表统计量'}。{aggregation_note}"



def _show_print_qc(fig, identifier, title):
    prepared = _prepare_print_qc(fig, identifier, title)
    if prepared:
        show_figure(prepared[0], caption=prepared[1])


def _group_coverage(fig):
    """Display-only group means/ranges at saved coverage bins; input stays intact."""
    import numpy as np
    from bioreport.utils.print_theme import group_palette
    groups = (fig.layout.meta or {}).get('sample_groups', {})
    members = {}
    for trace in fig.data:
        members.setdefault(groups.get(trace.name, trace.name), []).append(trace)
    palette = group_palette(members)
    result = go.Figure(layout=fig.layout)
    for group, traces in members.items():
        # Exact bin alignment: missing bins are excluded, never invented as zeros.
        bins = sorted({float(x) for t in traces for x in t.x if 0 <= float(x) <= 100})
        mappings = [dict(zip(map(float,t.x),map(float,t.y))) for t in traces]
        values = np.array([[mapping.get(x,np.nan) for x in bins] for mapping in mappings])
        low, high = np.nanmin(values,axis=0), np.nanmax(values,axis=0)
        color = palette[group]
        rgb = ','.join(str(int(color[i:i+2],16)) for i in (1,3,5))
        result.add_trace(go.Scatter(x=bins+bins[::-1], y=high.tolist()+low[::-1].tolist(),
            mode='lines',line=dict(width=0), fill='toself', fillcolor=f'rgba({rgb},0.2)',
            name=group,legendgroup=group,showlegend=False,hoverinfo='skip'))
        result.add_trace(go.Scatter(x=bins,y=np.nanmean(values,axis=0),mode='lines',
            name=group,legendgroup=group,line=dict(color=color,dash='solid'),showlegend=True))
    result.update_layout(meta={**(fig.layout.meta or {}),'coverage_groups':True},
                         legend=dict(orientation='h',y=1.03,yanchor='bottom'),
                         margin=dict(t=110,b=60,l=75,r=35),
                         title=dict(y=.98,yanchor='top'))
    result.update_xaxes(range=[0,100])
    return result


def visualize_fastq_screen_pair(r1_dir, r2_dir):
    """Two read panels, one shared category palette/legend and numeric scale."""
    import numpy as np
    from plotly.subplots import make_subplots
    from bioreport.config import display_path
    from bioreport.utils.print_theme import aggregate_bar_categories, PALETTE
    from bioreport.utils.render_output import typst_note
    figures = []
    for read, directory in (('R1',r1_dir),('R2',r2_dir)):
        json_path = _saved_multiqc_path(directory)
        with open(json_path,encoding='utf-8') as handle:
            plots = json.load(handle).get('report_plot_data',{})
        matches = [(key,plot,ds) for key,plot in plots.items() if 'fastq_screen' in key.lower()
                   for ds in plot.get('datasets',[]) if plot.get('plot_type')=='bar plot']
        if len(matches) != 1:
            raise ValueError(f'Expected one FastQ Screen dataset for {read}: {directory}')
        key,plot,ds = matches[0]
        _assert_sample_coverage(key, list(map(str,ds.get('samples',[]))),directory)
        fig,title = _dataset_figure(key,plot,ds)
        if is_pdf():
            fig,_ = _prepare_print_qc(fig,key,title,aggregate=False)
        figures.append(fig)
    # Aggregate jointly so Other and named categories have identical meanings.
    merged = go.Figure()
    categories = list(dict.fromkeys(t.name for f in figures for t in f.data))
    counts = [len(f.data[0].x) for f in figures]
    for name in categories:
        vals = []
        for f,n in zip(figures,counts):
            trace = next((t for t in f.data if t.name==name),None)
            vals.extend(list(trace.x) if trace is not None else [0]*n)
        merged.add_trace(go.Bar(x=vals,y=list(range(sum(counts))),name=name,orientation='h'))
    legend = _qc_config().get('analysis',{}).get('fastq_screen',{}).get('legend',{})
    merged = aggregate_bar_categories(merged, **{k:legend[k] for k in ('min_fraction','max_categories','aggregate_other') if k in legend})
    pair = make_subplots(rows=1,cols=2,subplot_titles=('R1','R2'),horizontal_spacing=.14)
    maximum = 0
    for col,fig in enumerate(figures,1):
        offset = sum(counts[:col-1])
        total = np.zeros(counts[col-1])
        for i,trace in enumerate(merged.data):
            values = list(trace.x)[offset:offset+counts[col-1]]
            total += np.asarray(values,dtype=float)
            pair.add_trace(go.Bar(x=values,y=list(fig.data[0].y),orientation='h',name=trace.name,
                marker_color=PALETTE[i%len(PALETTE)],legendgroup=trace.name,showlegend=col==1),row=1,col=col)
        maximum = max(maximum,float(np.nanmax(total)))
    pair.update_layout(barmode='stack',template='simple_white',height=540,width=1100,
        meta={'paired_screen':True},legend=dict(orientation='h',y=1.24,yanchor='bottom',x=0),margin=dict(t=120,l=80,r=40,b=50))
    pair.update_xaxes(range=[0,100 if _percent_axis_enabled() else maximum*1.02],title_text=figures[0].layout.xaxis.title.text)
    pair.update_yaxes(autorange='reversed')
    show_figure(pair, caption='FastQ Screen R1/R2 双面板：同一样本顺序、坐标范围与物种类别共用图例；Other 仅为显示层聚合。')
    if is_pdf():
        typst_note(f'外源污染评估图读取 MultiQC 保存的 FastQ Screen 汇总数据集。完整质控结果（数据目录内相对路径）：R1 {display_path(r1_dir)}；R2 {display_path(r2_dir)}')

def _expected_samples() -> Optional[List[str]]:
    """样本表声明的样本标识（含 sample/sample_name 两个别名），用于覆盖度核对。"""
    path = _qc_config().get('input_files', {}).get('sample_file')
    if not path or not os.path.isfile(path):
        return None
    import pandas as pd
    metadata = pd.read_csv(path)
    # sample_name is the report-facing canonical identifier. Including both
    # columns would count every library twice (e.g. 1-1_raw and 1-1).
    column = next((column for column in ('sample_name', 'sample', 'Sample') if column in metadata), None)
    if column is None:
        return []
    return list(dict.fromkeys(str(value) for value in metadata[column].dropna()))


def _sample_coverage(samples: List[str], expected: Optional[List[str]]) -> Dict[str, Any]:
    """比对 MultiQC 汇总样本与样本表全集，返回未匹配的声明样本。"""
    if not expected:
        return {'expected': [], 'missing': [], 'found': list(samples)}
    present = {str(value) for value in samples}
    # MultiQC 的样本名带 _raw/_R1_screen 等后缀，按声明名做前缀匹配。
    missing = [name for name in expected if not any(
        present_value == name or present_value.startswith(name) for present_value in present)]
    return {'expected': expected, 'missing': missing, 'found': list(samples)}


def _assert_sample_coverage(identifier: str, samples: List[str], analysis_dir: str) -> None:
    """缺样显性化：0 个样本直接失败；部分缺失按配置报错或写入正文提示。"""
    from bioreport.utils.print_theme import plain
    expected = _expected_samples()
    if expected is None:
        return
    coverage = _sample_coverage(samples, expected)
    if coverage['missing'] and not samples:
        raise ValueError(f'{identifier}: MultiQC 汇总未包含任何样本，无法绘制 {analysis_dir}')
    if not coverage['missing']:
        return
    report = _qc_config().get('report', {}).get('pdf', {})
    strict = report.get('qc_sample_coverage', 'warn')
    if strict not in ('warn', 'error'):
        raise ValueError("report.pdf.qc_sample_coverage must be 'warn' or 'error'")
    message = (f"{plain(identifier)}：MultiQC 实际汇总 {len(samples)} / {len(expected)} "
               f"个样本，缺失 {', '.join(coverage['missing'])}。缺失样本不出现在图中，"
               '请核对上游质控产物是否齐全。')
    if strict == 'error':
        raise ValueError(message)
    from bioreport.utils.render_output import typst_note
    typst_note(message)


def _visualize_pdf_json(data, analysis_dir, targets, *, emit_source=True):
    """Export each real MultiQC dataset, including filtering/read stages."""
    from bioreport.config import display_path
    from bioreport.utils.render_output import typst_note
    from bioreport.utils.print_theme import plain
    detail = _qc_config().get('report',{}).get('pdf',{}).get('qc_detail','key')
    plots = data.get('report_plot_data', {})
    matched = 0
    for identifier, plot in plots.items():
        config = plot.get('pconfig', {})
        title = config.get('title') or identifier
        if targets and not any(t.lower() in (identifier+' '+title).lower() for t in targets):
            continue
        if plot.get('plot_type') not in ['x/y line','bar plot']:
            # General-statistics violin plots duplicate the separate input tables.
            continue
        matched += 1
        datasets = plot.get('datasets', [])
        # 缺样仅在声明了样本轴的柱状数据集上判定：x/y 折线数据集不带 samples，跳过。
        declared = next((ds.get('samples') for ds in datasets if ds.get('samples')), None)
        if declared is not None:
            _assert_sample_coverage(identifier, [str(s) for s in declared], analysis_dir)
        from contextlib import nullcontext
        from bioreport.utils.render_output import figure_group
        quality = any(term in (identifier+' '+title).lower() for term in ('sequence quality','seq-quality','sequence_quality'))
        with figure_group('qc-'+identifier) if quality else nullcontext():
            for dataset in datasets:
                dconfig = dataset.get('dconfig', {})
                stage = dconfig.get('name', '')
                if detail == 'key' and len(datasets)>1 and 'Before filtering' in stage:
                    continue
                fig, caption = _dataset_figure(identifier, plot, dataset)
                if not fig.data: continue
                _show_print_qc(fig, identifier, caption)
    if not matched:
        raise ValueError(f'No QC plot datasets for {targets} in {analysis_dir}')
    if not emit_source:
        return
    # 底部数据源说明按模块区分：只有 fastp 存在 Before/After filtering 过滤阶段，
    # 其余模块（FastQ Screen、QualiMap 等）不引用“过滤曲线”措辞，避免张冠李戴。
    lowered = [str(t).lower() for t in (targets or [])]
    if any(t.startswith('fastp') for t in lowered):
        source_note = ('质控图读取 MultiQC 保存的 fastp 汇总数据集；'
                       + ('正文保留关键图，过滤曲线使用 After filtering 阶段' if detail=='key'
                          else '展示全部已保存的曲线和柱状诊断图，含各 reads 与过滤阶段')
                       + '。')
    elif any(t.startswith('fastq_screen') for t in lowered):
        source_note = '外源污染评估图读取 MultiQC 保存的 FastQ Screen 汇总数据集。'
    elif any(t.startswith('star') for t in lowered):
        source_note = '比对统计图读取 MultiQC 保存的 STAR 汇总数据集。'
    elif lowered:
        source_note = '比对质控图读取 MultiQC 保存的 QualiMap BamQC 汇总数据集。'
    else:
        source_note = '质控图读取 MultiQC 保存的汇总数据集。'
    typst_note(f"{source_note}完整质控结果（数据目录内相对路径）：{display_path(analysis_dir)}")
