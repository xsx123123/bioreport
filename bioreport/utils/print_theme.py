"""Shared scientific print theme and browser-free export of existing Plotly data.

The exporter uses the plotted trace coordinates; it does not rerun statistics,
filter genes, recluster samples, or change the underlying result files.
"""
import html
import re
from pathlib import Path

# Font discovery lives in utils.fonts (shared with Typst and the CLI); this
# re-export keeps the historical import path working.
from .fonts import FONT_STACK, font_families  # noqa: F401

# Discrete group palettes. 'seaside' is the default; the rest are available
# via group_palette(groups, palette='apple'|'ibm'|'candy').
PALETTES = {
    'seaside': ['#8ecae6', '#219ebc', '#023047', '#ffb703', '#fb8500'],
    'apple': ['#ff3b30', '#ff9500', '#ffcc00', '#4cd964', '#5ac8fa', '#007aff', '#5856d6'],
    'ibm': ['#5B8DFE', '#725DEE', '#DD227D', '#FE5F00', '#FFB109'],
    'candy': ['#9b5de5', '#f15bb5', '#fee440', '#00bbf9', '#00f5d4'],
}
PALETTE = PALETTES['seaside']

# Thousands of SVG marker objects per volcano multiply Typst's memory use in
# large reports. Render the complete dense point layer at print resolution;
# labels, axes, threshold lines and small scatter plots stay vector graphics.
SCATTER_RASTER_THRESHOLD = 1000


class UnsupportedTrace(ValueError):
    """A third-party plot needs Plotly's own static exporter."""


def group_palette(groups, palette=None):
    """Map sorted unique groups to colors; palette is a PALETTES name or a color list."""
    colors = PALETTES[palette] if isinstance(palette, str) else (palette or PALETTE)
    return {str(g): colors[i % len(colors)] for i, g in enumerate(sorted(set(map(str, groups))))}


def plain(value):
    value = str(value or '')
    scripts = {
        'sup': str.maketrans('0123456789+-=()ni', '⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ'),
        'sub': str.maketrans('0123456789+-=()aehijklmnoprstuvx', '₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ'),
    }
    def script(match):
        text = html.unescape(re.sub(r'<[^>]*>', '', match[2]))
        mapping = scripts[match[1].lower()]
        # Short scientific indices retain their meaning; prose subtitles stay
        # readable normal text. Never discard the contents of a script tag.
        return text.translate(mapping) if all(ord(c) in mapping for c in text) else text
    value = re.sub(r'<(sup|sub)\b[^>]*>(.*?)</\1>', script, value, flags=re.S | re.I)
    value = re.sub(r'<br\s*/?>', '\n', value, flags=re.I)
    return html.unescape(re.sub(r'<[^>]*>', '', value)).strip()


def vector_snapshot(figure):
    """Export 2-D WebGL scatter as SVG paths without changing the live figure."""
    if not any(trace.type == 'scattergl' for trace in figure.data):
        return figure
    import plotly.graph_objects as go
    spec = figure.to_plotly_json()
    for trace in spec['data']:
        if trace['type'] == 'scattergl':
            trace['type'] = 'scatter'
    return go.Figure(spec)


# Heatmaps retain the full clustering until more than 40 sample columns.
UNSPLIT_TYPES = {'heatmap': 40}


def _sample_batches(names, capacity, groups):
    """Pack complete groups; a large group remains intact on its own panel."""
    from collections import OrderedDict
    grouped = OrderedDict()
    for name in names:
        grouped.setdefault(groups.get(str(name), str(name)), []).append(name)
    batches, current = [], []
    for members in grouped.values():
        if current and len(current) + len(members) > capacity:
            batches.append(current)
            current = []
        current.extend(members)
    if current:
        batches.append(current)
    return batches


def print_panels(figure):
    """Use plot-specific page capacities without recomputing results."""
    import numpy as np
    import plotly.graph_objects as go
    from bioreport.i18n import language
    english = language() == 'en'
    traces = list(figure.data)
    meta = figure.layout.meta or {}
    if not isinstance(meta, dict):
        meta = {}
    if meta.get('enrichment') or meta.get('paired_screen') or meta.get('coverage_groups'):
        return [(figure, '')]
    if len(traces) == 1 and traces[0].type == 'heatmap':
        trace = traces[0]
        names = list(trace.x)
        capacity = UNSPLIT_TYPES['heatmap']
        if len(names) <= capacity:
            return [(figure, '')]
        # Balanced contiguous slices avoid a tiny last panel; never recluster.
        chunks = np.array_split(np.arange(len(names)), int(np.ceil(len(names)/capacity)))
        z = np.asarray(trace.z)
        vmin = trace.zmin if trace.zmin is not None else figure.layout.coloraxis.cmin
        vmax = trace.zmax if trace.zmax is not None else figure.layout.coloraxis.cmax
        panels = []
        for indices in chunks:
            panel = go.Figure(figure)
            panel.data[0].x = [names[i] for i in indices]
            panel.data[0].z = z[:, indices]
            panel.data[0].zmin = float(np.nanmin(z)) if vmin is None else vmin
            panel.data[0].zmax = float(np.nanmax(z)) if vmax is None else vmax
            panel.update_layout(meta={**meta, 'show_gene_names': True})
            detail = (f'Clustered sample columns {indices[0]+1}–{indices[-1]+1} / {len(names)}; '
                      f'this panel: {len(indices)} / {len(names)} samples. All panels together cover every sample; '
                      'no random subsampling. Full clustering order and color scale are preserved.' if english else
                      f'聚类后样本列 {indices[0]+1}–{indices[-1]+1} / {len(names)}；'
                      f'本图 {len(indices)} / {len(names)} 个样本；全部面板合计覆盖全部样本，'
                      '未随机抽样；沿用整图聚类顺序与完整色标')
            panels.append((panel, detail))
        return panels
    kind = None
    if traces and all(t.type in ('violin', 'box') for t in traces):
        kind, capacity = 'distribution', 20
        names = list(meta.get('sample_order') or dict.fromkeys(str(v) for t in traces for v in t.x))
    elif traces and all(t.type == 'bar' for t in traces):
        kind, capacity = 'bar', 25
        horizontal = traces[0].orientation == 'h'
        names = list(traces[0].y if horizontal else traces[0].x)
        if not all(list(t.y if horizontal else t.x) == names for t in traces):
            return [(figure, '')]
    elif traces and all(t.type == 'scatter' and 'lines' in (t.mode or 'lines') for t in traces):
        kind, capacity = 'line', 20
        names = [t.name for t in traces]
    else:
        return [(figure, '')]
    if len(names) <= capacity:
        return [(figure, '')]
    groups = meta.get('sample_groups', {})
    if kind == 'distribution' and not groups:
        groups = {str(v): str(t.name) for t in traces for v in t.x}
    batches = _sample_batches(names, capacity, groups)
    panels = []
    # Resolve common numeric limits before subsetting, including stacked totals.
    horizontal = kind == 'bar' and traces[0].orientation == 'h'
    if kind == 'bar':
        values = np.array([t.x if horizontal else t.y for t in traces], dtype=float)
        maximum = float(np.nanmax(np.nansum(values, axis=0) if figure.layout.barmode in ('stack','relative') else values))
        minimum = min(0., float(np.nanmin(values)))
    elif kind in ('line', 'distribution'):
        values = np.concatenate([np.asarray(t.y, dtype=float) for t in traces])
        minimum, maximum = float(np.nanmin(values)), float(np.nanmax(values))
    span = maximum-minimum or 1
    common_range = [minimum - (0 if kind == 'bar' else .04*span), maximum+.06*span]
    for index, subset in enumerate(batches):
        panel = go.Figure(layout=figure.layout)
        panel.update_layout(meta={**meta, 'sample_order': subset})
        for trace in traces:
            if kind == 'line':
                if trace.name in subset:
                    panel.add_trace(trace)
                continue
            copy = go.Figure(data=[trace]).data[0]
            labels = trace.y if horizontal else trace.x
            keep = [i for i,v in enumerate(labels) if v in subset or str(v) in subset]
            if not keep:
                continue
            copy.x = [trace.x[i] for i in keep]
            copy.y = [trace.y[i] for i in keep]
            panel.add_trace(copy)
        if horizontal:
            if figure.layout.xaxis.range is None:
                panel.update_xaxes(range=common_range)
        elif figure.layout.yaxis.range is None:
            panel.update_yaxes(range=common_range)
        if kind == 'line' and figure.layout.xaxis.range is None:
            xs = np.concatenate([np.asarray(t.x,dtype=float) for t in traces])
            panel.update_xaxes(range=[float(np.nanmin(xs)),float(np.nanmax(xs))])
        detail = (f'Sample panel {index+1} / {len(batches)}; this panel: {len(subset)} / {len(names)} samples. '
                  'All panels together cover every sample in group/input order; no random subsampling.' if english else
                  f'分组面板 {index+1} / {len(batches)}；本图 {len(subset)} / {len(names)} 个样本；'
                  '全部面板合计覆盖全部样本，按分组与输入顺序分页，未随机抽样')
        panels.append((panel, detail))
    return panels


def _annotate_points(axes, x, y, texts):
    """Scatter labels with deterministic de-collision.

    PCA replicates can land on nearly identical coordinates, which leaves their
    text labels unreadable. Each label is tried at a fixed ladder of offsets and
    the first non-overlapping one wins, so identical input always produces the
    same layout (no random jitter).
    """
    offsets = [(0, 7), (0, -12), (12, 3), (-12, 3), (12, -10), (-12, -10),
               (0, 17), (0, -22), (18, 8), (-18, 8)]
    placed = []  # display-space boxes of already-placed labels
    renderer = axes.figure.canvas.get_renderer()
    for px, py, label_text in zip(x, y, texts):
        label_text = str(label_text)
        anchor = (float(px), float(py))
        for dx, dy in offsets:
            annotation = axes.annotate(label_text, anchor, xytext=(dx, dy),
                                       textcoords='offset points', ha='center', fontsize=9)
            box = annotation.get_window_extent(renderer=renderer).expanded(1.06, 1.12)
            if not any(box.overlaps(other) for other in placed):
                placed.append(box)
                break
            annotation.remove()
        else:
            # 全部槽位都被占用时保留第一条标签，绝不丢弃样本标注。
            annotation = axes.annotate(label_text, anchor, xytext=offsets[0],
                                       textcoords='offset points', ha='center', fontsize=9)
            placed.append(annotation.get_window_extent(renderer=renderer))


def export_vector(figure, path):
    """Export supported RNA/MultiQC traces to SVG, with text as embedded paths.

    Unsupported traces fail explicitly. Lines/text and small point layers are
    vector graphics; dense scatter/heatmap layers use 400 dpi inside the SVG.
    """
    if not figure.data:
        raise ValueError('Cannot export a figure without data traces')
    unsupported = {t.type for t in figure.data} - {'scatter','bar','box','violin','heatmap'}
    if unsupported:
        raise UnsupportedTrace(f'Unsupported static traces: {sorted(unsupported)}')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap
    from matplotlib.ticker import PercentFormatter, FuncFormatter
    from matplotlib.lines import Line2D
    import numpy as np
    import textwrap
    from .fonts import init_bioreport_plot_style

    def color(value, default=PALETTE[0]):
        if value is None: return default
        if isinstance(value, str) and value.startswith(('rgb(', 'rgba(')):
            v = [float(n) for n in re.findall(r'[\d.]+', value)]
            return tuple([n / 255 for n in v[:3]] + ([v[3]] if len(v) > 3 else []))
        return value

    layout = figure.layout
    title = plain(layout.title.text)
    meta = layout.meta or {}
    if not isinstance(meta, dict): meta = {}
    enrichment = bool(meta.get('enrichment'))
    scatter_points = sum(len(t.x) if t.x is not None else 0 for t in figure.data
                         if t.type == 'scatter' and 'lines' not in (t.mode or 'lines'))
    rasterize_scatter = scatter_points > SCATTER_RASTER_THRESHOLD and not enrichment
    width = 6.45
    height = max(2.7, min(7.0, float(meta.get('print_height', 3.25))))
    if figure.data and all(t.type=='bar' and t.orientation=='h' for t in figure.data):
        height = max(2.7, min(7., 1.1 + .18*len(figure.data[0].y)))
    if meta.get('paired_screen'):
        height = max(3.5, 1.3 + .20*len(figure.data[0].y))
    if any(t.type == 'heatmap' for t in figure.data):
        height = 5.0
    # Built-in fonts (Source Sans 3 + CJK) registered first, DejaVu kept as last resort.
    plot_fonts = init_bioreport_plot_style()
    with plt.rc_context({'font.family': [*plot_fonts, 'DejaVu Sans'], 'font.size': 10,
                         'axes.labelsize': 10, 'xtick.labelsize': 9, 'ytick.labelsize': 9,
                         'legend.fontsize': 9, 'svg.fonttype': 'path',
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'axes.edgecolor': '#b4bec9', 'axes.linewidth': .6}):
        out = plt.figure(figsize=(width, height), facecolor='white')
        axes = {}
        # Preserve subplot assignment, including the two PCA panels.
        keys = list(dict.fromkeys((t.xaxis or 'x', t.yaxis or 'y') for t in figure.data))
        for xkey, ykey in keys:
            xcfg = getattr(layout, 'xaxis' + xkey[1:])
            ycfg = getattr(layout, 'yaxis' + ykey[1:])
            xd = xcfg.domain or [0, 1]; yd = ycfg.domain or [0, 1]
            left = .39 if enrichment else .13
            right = .16 if enrichment else .04
            ax = out.add_axes([left + xd[0]*(1-left-right), .18+yd[0]*.68,
                               (xd[1]-xd[0])*(1-left-right), (yd[1]-yd[0])*.68])
            ax.set_xlabel(plain(xcfg.title.text)); ax.set_ylabel(plain(ycfg.title.text))
            ax.grid(axis='x' if enrichment else 'y', color='#e4e8ed', linewidth=.5)
            ax.set_axisbelow(True)
            axes[xkey, ykey] = (ax, xcfg, ycfg)
        stacked = {}
        heatmap = None
        scatter_labels = {}  # (xkey, ykey) -> [(x, y, text), ...] placed after limits settle
        for i, trace in enumerate(figure.data):
            ax, xcfg, ycfg = axes[trace.xaxis or 'x', trace.yaxis or 'y']
            name = plain(trace.name); label = name if trace.showlegend is not False else '_nolegend_'
            x = list(trace.x) if trace.x is not None else []
            y = list(trace.y) if trace.y is not None else []
            if trace.type == 'scatter' and not any(v is not None for v in x):
                continue
            if trace.type == 'scatter':
                mode = trace.mode or 'lines'
                if trace.fill == 'toself':
                    ax.fill(x, y, color=color(trace.fillcolor), linewidth=0, label='_nolegend_')
                    continue
                if 'lines' in mode:
                    ax.plot(x, y, color=color(trace.line.color, PALETTE[i % len(PALETTE)]),
                            linewidth=1.2, label=label,
                            linestyle={'dash':'--','dot':':','dashdot':'-.'}.get(trace.line.dash,'-'))
                else:
                    c = trace.marker.color
                    sizes = trace.marker.size
                    if enrichment:
                        yy = np.arange(len(y)); ax.set_yticks(yy)
                        ax.set_yticklabels([plain(v) for v in y], fontsize=9)
                        # Leave room for the complete first/last multiline label.
                        ax.set_ylim(-.65, len(y)-.35 if len(y)>1 else .65)
                        size_values = np.asarray(sizes, dtype=float)
                        scale = 180 / max(float(meta.get('count_max',size_values.max())), 1)
                        cmap = LinearSegmentedColormap.from_list('adjusted-p', [(float(a), color(b)) for a,b in layout.coloraxis.colorscale])
                        color_values = np.asarray(c,dtype=float)
                        minimum = layout.coloraxis.cmin if layout.coloraxis.cmin is not None else float(color_values.min())
                        maximum = layout.coloraxis.cmax if layout.coloraxis.cmax is not None else float(color_values.max())
                        pts = ax.scatter(x, yy, s=size_values*scale, c=np.asarray(c,dtype=float), cmap=cmap,
                                         vmin=minimum, vmax=maximum if maximum>minimum else minimum+max(abs(minimum)*.1,1e-300),
                                         edgecolors='#637083', linewidths=.5)
                        cax = out.add_axes([.88,.48,.022,.30]); cb = out.colorbar(pts, cax=cax)
                        cb.set_ticks(np.linspace(minimum,maximum,4) if maximum>minimum else [minimum])
                        cb.ax.set_title(plain(layout.coloraxis.colorbar.title.text).replace('Adjusted P value', 'Adjusted\nP value'), fontsize=8.5, pad=9)
                        cb.formatter = FuncFormatter(lambda value,pos:f'{value:.1e}'); cb.update_ticks()
                        values = np.unique(np.round(np.quantile(size_values, [.0,.5,1])).astype(int))
                        handles = [Line2D([],[],marker='o',linestyle='',markerfacecolor='#8b9cad',
                                           markeredgecolor='#637083',markersize=np.sqrt(v*scale),label=str(v)) for v in values]
                        ax.legend(handles=handles,title='Count',bbox_to_anchor=(1.06,.30),loc='upper left',frameon=False)
                        ax.set_xlabel(plain(xcfg.title.text) or 'Gene ratio')
                    else:
                        ax.scatter(x, y, s=float(sizes or 6)**2/2,
                                   color=color(c, PALETTE[i % len(PALETTE)]),
                                   alpha=trace.marker.opacity or .8, label=label, edgecolors='none',
                                   rasterized=rasterize_scatter)
                        if 'text' in mode and trace.text is not None:
                            # Labels are placed after every trace has set its limits,
                            # so cross-group replicates also de-collide.
                            scatter_labels.setdefault((trace.xaxis or 'x', trace.yaxis or 'y'), []).extend(
                                (px, py, label_text) for px, py, label_text in zip(x, y, trace.text))
                            ax.margins(x=.12, y=.18)

            elif trace.type == 'bar':
                horizontal = trace.orientation == 'h'
                categories = y if horizontal else x
                vals = np.asarray(x if horizontal else y, dtype=float)
                pos = np.arange(len(categories))
                key = (id(ax), tuple(categories))
                base = stacked.setdefault(key,np.zeros(len(vals)))
                style = dict(color=color(trace.marker.color,PALETTE[i%len(PALETTE)]),label=label)
                if horizontal:
                    ax.barh(pos, vals, left=base if layout.barmode in ['stack','relative'] else None, height=.7, **style)
                    ax.set_yticks(pos); ax.set_yticklabels(['\n'.join(textwrap.wrap(str(v),26,break_on_hyphens=False)) for v in categories])
                else:
                    ax.bar(pos, vals, bottom=base if layout.barmode in ['stack','relative'] else None,width=.7,**style)
                    ax.set_xticks(pos); ax.set_xticklabels(categories,rotation=35,ha='right')
                if layout.barmode in ['stack','relative']: base += np.nan_to_num(vals, nan=0.)
            elif trace.type == 'box':
                order = list(dict.fromkeys(str(v) for t in figure.data for v in t.x))
                for sample in dict.fromkeys(map(str, x)):
                    vals = np.asarray([v for k, v in zip(x, y) if str(k) == sample], dtype=float)
                    idx = order.index(sample)
                    boxes = ax.boxplot([vals], positions=[idx], widths=.55, patch_artist=True)
                    for body in boxes['boxes']:
                        body.set_facecolor(color(trace.marker.color, PALETTE[i % len(PALETTE)]))
                    if trace.boxpoints == 'all':
                        ax.scatter(np.full(len(vals), idx), vals, s=12, color='#243746', zorder=3)
                ax.set_xticks(range(len(order)))
                ax.set_xticklabels(order)
            elif trace.type == 'violin':
                order = meta.get('sample_order') or list(dict.fromkeys(str(v) for t in figure.data for v in t.x))
                for sample in dict.fromkeys(map(str,x)):
                    vals = np.asarray([v for k,v in zip(x,y) if str(k)==sample],dtype=float)
                    idx = order.index(sample)
                    if len(vals)>1 and np.std(vals)>0:
                        vp = ax.violinplot(vals,positions=[idx],widths=.75,showextrema=False)
                        for body in vp['bodies']: body.set_facecolor(color(trace.fillcolor or trace.line.color or trace.marker.color)); body.set_alpha(.8)
                    ax.boxplot([vals],positions=[idx],widths=.12,showfliers=False,
                               medianprops={'color':'#243746'},boxprops={'linewidth':.7},whiskerprops={'linewidth':.7})
                ax.set_xticks(range(len(order))); ax.set_xticklabels(['\n'.join(textwrap.wrap(str(v),18)) for v in order],rotation=90 if len(order)>8 else 40,ha='right')
                ax.plot([],[],color=color(trace.fillcolor or trace.line.color or trace.marker.color),linewidth=5,label=label)
            elif trace.type == 'heatmap':
                heatmap = trace
                z = np.asarray(trace.z,dtype=float)
                vmin = trace.zmin if trace.zmin is not None else layout.coloraxis.cmin
                vmax = trace.zmax if trace.zmax is not None else layout.coloraxis.cmax
                mesh = ax.imshow(z,aspect='auto',cmap='RdBu_r',vmin=vmin,vmax=vmax,
                                 interpolation='nearest',rasterized=len(z)>200)
                ax.grid(False); ax.set_xticks(range(len(x))); ax.set_xticklabels(['\n'.join(textwrap.wrap(str(v),18)) for v in x],rotation=90 if len(x)>8 else 40,ha='right')
                if len(z)<=60 or meta.get('show_gene_names'):
                    ax.set_yticks(range(len(y))); ax.set_yticklabels(y,fontsize=6 if len(z)>40 else 7)
                else: ax.set_yticks([])
                cb=out.colorbar(mesh,ax=ax,pad=.02,fraction=.035);cb.set_label('Z-score',fontsize=9)
                groups=meta.get('sample_groups',{}); cmap=meta.get('group_colors',{})
                if groups:
                    from matplotlib.patches import Rectangle,Patch
                    for j,sample in enumerate(x):
                        ax.add_patch(Rectangle((j-.5,-max(len(z)*.035,1)),1,max(len(z)*.025,1),
                                               color=cmap[str(groups[str(sample)])],clip_on=False))
                    ax.legend(handles=[Patch(color=c,label=g) for g,c in cmap.items()],loc='upper center',
                              bbox_to_anchor=(.5,1.17),ncol=min(4,len(cmap)),frameon=False,title='Group')
            else:
                plt.close(out)
                raise UnsupportedTrace(f'Unsupported static trace: {trace.type}')
        for (xkey,ykey),(ax,xcfg,ycfg) in axes.items():
            for cfg,axis in [(xcfg,ax.xaxis),(ycfg,ax.yaxis)]:
                if cfg.tickformat and '%' in cfg.tickformat: axis.set_major_formatter(PercentFormatter(xmax=1))
                if cfg.type=='log':
                    (ax.set_xscale if cfg is xcfg else ax.set_yscale)('log')
            if xcfg.range and xcfg.type!='log': ax.set_xlim(xcfg.range)
            if ycfg.range and ycfg.type!='log': ax.set_ylim(ycfg.range)
            if ycfg.tickvals is not None:
                ax.set_yticks(list(ycfg.tickvals))
                if ycfg.ticktext is not None: ax.set_yticklabels(list(ycfg.ticktext))
            if ycfg.autorange=='reversed' and heatmap is None: ax.invert_yaxis()
            # 点位标签在所有 trace 与坐标范围确定后统一避让，跨分组重复样本也能分开。
            pending = scatter_labels.get((xkey, ykey))
            if pending:
                out.canvas.draw()
                ax.autoscale_view()
                _annotate_points(ax, [p[0] for p in pending], [p[1] for p in pending],
                                 [p[2] for p in pending])
            for shape in layout.shapes or []:
                if shape.xref not in [None,xkey,xkey+' domain','paper'] or shape.yref not in [None,ykey,ykey+' domain','paper']: continue
                if shape.x0==shape.x1:ax.axvline(shape.x0,color='#8795a5',linewidth=.7,linestyle='--')
                elif shape.y0==shape.y1:ax.axhline(shape.y0,color='#8795a5',linewidth=.7,linestyle='--')
            handles,labels=ax.get_legend_handles_labels()
            if handles and not enrichment and heatmap is None:
                dense_bar = any(t.type=='bar' and t.orientation=='h' and len(t.y)>8 for t in figure.data)
                stacked_bar = any(t.type=='bar' and t.orientation=='h' and layout.barmode in ['stack','relative']
                                  for t in figure.data)
                horizontal_legend = (getattr(layout.legend, 'orientation', None) == 'h' or 'display_cap' in meta)
                multi_panel = len(axes) > 1
                if meta.get('paired_screen'):
                    if (xkey,ykey) == keys[0]:
                        ax.legend(handles, labels, loc='lower left', bbox_to_anchor=(0, 1.15),
                                  ncol=min(3,len(handles)),frameon=False,fontsize=8)
                elif multi_panel:
                    ax.legend(handles, labels, loc='lower left', bbox_to_anchor=(0, 1.16),
                              ncol=min(4,len(handles)), frameon=False,fontsize=8)
                elif horizontal_legend or stacked_bar:
                    # Plotly 声明的水平公共图例或横向堆叠柱：图例移到轴外上方，避免叠压点位。
                    title = plain(layout.legend.title.text) if getattr(layout.legend, 'title', None) and layout.legend.title.text else None
                    ax.legend(handles, labels, loc='lower left', bbox_to_anchor=(0, 1.01),
                              ncol=min(6, len(handles)), frameon=False, fontsize=8.5,
                              handlelength=1.2, columnspacing=1.2, title=title)
                elif len(handles)>8 or dense_bar:
                    wrapped = ['\n'.join(textwrap.wrap(v.replace('_',' '),26)) for v in labels]
                    ax.legend(handles, wrapped, loc='upper center',bbox_to_anchor=(.5,-.25),ncol=2,frameon=False,fontsize=9)
                else:ax.legend(loc='best',frameon=False)
        # Render data-anchored Plotly annotations (including volcano gene leaders).
        leaders = [a for a in (layout.annotations or []) if a.showarrow and a.xref != 'paper' and a.yref != 'paper']
        if leaders:
            ax = next(iter(axes.values()))[0]
            xmin, xmax = ax.get_xlim(); ymin, ymax = ax.get_ylim()
            for side in (-1, 1):
                selected = [a for a in leaders if (-1 if float(a.x)<0 else 1) == side]
                selected.sort(key=lambda a: float(a.y))
                for rank, annotation in enumerate(selected):
                    # Dedicated label lanes keep the capped points' labels apart.
                    yy = ymin + (ymax-ymin)*(.43 + .46*(rank+1)/max(len(selected),1))
                    xx = xmin+(xmax-xmin)*(.02 if side<0 else .98)
                    ax.annotate(plain(annotation.text), (annotation.x, annotation.y),
                                xytext=(xx,yy), textcoords='data',
                                ha='left' if side<0 else 'right', va='center',fontsize=7,
                                bbox=dict(facecolor='white',edgecolor='none',alpha=.85,pad=.5),
                                arrowprops=dict(arrowstyle='-',color='#637083',lw=.65), zorder=8)
        # PCA subplot labels are real axis titles, not duplicate report headings.
        for annotation in layout.annotations or []:
            if annotation.xref=='paper' and annotation.yref=='paper' and not enrichment:
                out.text(.13+float(annotation.x)*.83,.18+float(annotation.y)*.68+.02,plain(annotation.text),
                         ha='center',fontsize=9)
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        out.savefig(path,format='svg',dpi=400,bbox_inches='tight',pad_inches=.06)
        plt.close(out)
    return width,height


def aggregate_bar_categories(figure, min_fraction=.01, max_categories=5, aggregate_other=True):
    """Display-only reduction; sum discarded categories into Other per sample."""
    import numpy as np
    import plotly.graph_objects as go
    if not 0 <= min_fraction <= 1 or max_categories < 2:
        raise ValueError('Legend requires a fraction in [0,1] and at least two categories')
    result = go.Figure(figure)
    traces = list(result.data)
    if not aggregate_other or not traces or any(t.type != 'bar' for t in traces):
        return result
    horizontal = traces[0].orientation == 'h'
    labels = list(traces[0].y if horizontal else traces[0].x)
    if any(list(t.y if horizontal else t.x) != labels for t in traces):
        raise ValueError('Cannot aggregate bar categories with different sample axes')
    values = [np.asarray(t.x if horizontal else t.y, dtype=float) for t in traces]
    totals = np.asarray([np.nansum(v) for v in values])
    total = totals.sum()
    ranked = np.argsort(-totals, kind='stable')
    keep = [int(i) for i in ranked if total > 0 and totals[i]/total >= min_fraction][:max_categories-1]
    rest = [i for i in range(len(traces)) if i not in keep]
    if not rest: return result
    result.data = tuple(traces[i] for i in keep)
    other = np.sum([np.nan_to_num(values[i]) for i in rest], axis=0)
    result.add_trace(go.Bar(name='Other', orientation='h' if horizontal else 'v',
                           x=other if horizontal else labels,
                           y=labels if horizontal else other, marker_color='#9aa5b1'))
    result.update_layout(meta={**(result.layout.meta or {}),
        'aggregated_categories':[str(traces[i].name) for i in rest]})
    return result
