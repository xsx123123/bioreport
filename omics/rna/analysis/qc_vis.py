#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import plotly.graph_objects as go
from IPython.display import display, Markdown
from bioreport.utils.render_output import show_figure, is_pdf
from typing import Optional, List, Dict, Any

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
    fig.update_layout(title=title, template='simple_white', height=500,
        xaxis_title=axis_title('xaxis') or config.get('xlab') or '',
        yaxis_title=axis_title('yaxis') or ('Sample' if plot.get('plot_type')=='bar plot' and horizontal else dconfig.get('ylab') or config.get('ylab') or ''))
    return fig, title


def _visualize_from_json(analysis_dir: str, target_modules: Optional[List[str]] = None) -> None:
    """Render interactive plots from a saved MultiQC report, including all stages."""
    path = os.path.join(analysis_dir, 'multiqc_data.json')
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
    
    json_path = os.path.join(analysis_dir, 'multiqc_data.json')
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
                                            analysis_dir,[module_name])
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


def _show_print_qc(fig, identifier, title):
    from bioreport.config import load_config
    from bioreport.utils.print_theme import plain
    config = load_config()
    detail = config.get('report',{}).get('pdf',{}).get('qc_detail','key')
    key = (str(identifier)+' '+plain(title)).lower()
    if detail != 'all' and not any(value in key for value in [
            'filtered reads', 'filtered_reads', 'sequence quality', 'sequence_quality',
            'mapped reads', 'mapped_reads', 'coverage histogram', 'coverage_histogram',
            'alignment scores', 'alignment_scores', 'star_alignment']):
        return
    # The same sample group uses the same color in QC, PCA, distribution and heatmap.
    sample_file = config.get('input_files', {}).get('sample_file')
    if sample_file and os.path.isfile(sample_file):
        import pandas as pd
        from bioreport.utils.print_theme import group_palette
        metadata = pd.read_csv(sample_file)
        if 'group' in metadata:
            palette = group_palette(metadata['group'])
            aliases = {}
            for _, row in metadata.iterrows():
                for column in ['sample','sample_name']:
                    if column in metadata:
                        aliases[str(row[column])] = (str(row.get('sample_name',row[column])),str(row['group']))
            for trace in fig.data:
                if trace.type == 'scatter' and trace.name in aliases:
                    sample, group = aliases[trace.name]
                    trace.line.color = palette[group]
                    # Preserve replicate identity through the sample legend.
                    trace.line.dash = ['solid','dash','dot','dashdot'][list(aliases).index(trace.name)%4]
                    trace.name = sample
            from bioreport.utils.pdf_results import ordered_samples
            order = ordered_samples(metadata)
            if all(t.type=='scatter' and 'lines' in (t.mode or 'lines') for t in fig.data):
                fig.data = sorted(fig.data,key=lambda t:order.index(t.name) if t.name in order else len(order))
            if fig.data and all(t.type=='bar' for t in fig.data):
                def identity(value):
                    for alias in sorted(aliases,key=len,reverse=True):
                        if str(value).startswith(alias):
                            sample, group = aliases[alias]
                            suffix = str(value)[len(alias):].removesuffix('_screen')
                            return sample+suffix, order.index(sample) if sample in order else len(order)
                    return str(value), len(order)
                horizontal = fig.data[0].orientation=='h'
                for trace in fig.data:
                    values = list(trace.y if horizontal else trace.x)
                    positions = sorted(range(len(values)),key=lambda i:identity(values[i])[1])
                    labels = [identity(values[i])[0] for i in positions]
                    numbers = list(trace.x if horizontal else trace.y)
                    if horizontal:
                        trace.y, trace.x = labels, [numbers[i] for i in positions]
                    else:
                        trace.x, trace.y = labels, [numbers[i] for i in positions]
                if horizontal: fig.update_layout(yaxis_autorange='reversed')
    is_screen = 'fastq screen' in key or 'fastq_screen' in key
    if is_screen:
        from bioreport.utils.print_theme import aggregate_bar_categories
        legend = config.get('analysis', {}).get('fastq_screen', {}).get('legend', {})
        fig = aggregate_bar_categories(fig, **{k: legend[k] for k in
            ('min_fraction','max_categories','aggregate_other') if k in legend})
    label = plain(title)
    x = plain(fig.layout.xaxis.title.text)
    y = plain(fig.layout.yaxis.title.text)
    aggregation_note = 'Other 为仅显示层聚合，原始类别完整保留在输入数据中。' if is_screen else ''
    show_figure(fig, caption=f"{label}。横轴：{x or '输入图表坐标'}；纵轴：{y or '输入图表统计量'}。颜色与图例对应输入样本或统计类别。{aggregation_note}")


def _visualize_pdf_json(data, analysis_dir, targets):
    """Export each real MultiQC dataset, including filtering/read stages."""
    from bioreport.config import load_config, display_path
    from bioreport.utils.render_output import typst_note
    from bioreport.utils.print_theme import plain
    detail = load_config().get('report',{}).get('pdf',{}).get('qc_detail','key')
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
