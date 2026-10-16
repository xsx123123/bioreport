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

PALETTE = ['#4477AA', '#EE6677', '#228833', '#CCBB44', '#66CCEE', '#AA3377', '#BBBBBB']


class UnsupportedTrace(ValueError):
    """A third-party plot needs Plotly's own static exporter."""


def group_palette(groups):
    return {str(g): PALETTE[i % len(PALETTE)] for i, g in enumerate(sorted(set(map(str, groups))))}


def plain(value):
    value = re.sub(r'<sup>.*?</sup>', '', str(value or ''), flags=re.S)
    return html.unescape(re.sub(r'<[^>]*>', '', value.replace('<br>', '\n'))).strip()


def print_panels(figure):
    """Split dense displays without recomputing statistics or clustering."""
    import numpy as np
    import plotly.graph_objects as go
    traces = list(figure.data)
    meta = figure.layout.meta or {}
    if isinstance(meta, dict) and meta.get('enrichment'):
        return [(figure, '')]
    if len(traces) == 1 and traces[0].type == 'heatmap':
        trace = traces[0]
        names = list(trace.x)
        if len(names) <= 12: return [(figure, '')]
        panels = []
        for start in range(0, len(names), 12):
            panel = go.Figure(figure)
            panel.data[0].x = names[start:start+12]
            panel.data[0].z = np.asarray(trace.z)[:,start:start+12]
            panels.append((panel, f'聚类后样本列 {start+1}–{min(start+12,len(names))} / {len(names)}；沿用整图的基因与样本聚类顺序及色标'))
        return panels
    if traces and all(t.type in ['violin','box'] for t in traces):
        names = list(meta.get('sample_order') or dict.fromkeys(str(v) for t in traces for v in t.x))
        if len(names) <= 12: return [(figure, '')]
        panels = []
        for start in range(0, len(names), 12):
            subset = names[start:start+12]
            panel = go.Figure(layout=figure.layout)
            panel.update_layout(meta={**meta, 'sample_order':subset})
            for trace in traces:
                keep = [i for i,v in enumerate(trace.x) if str(v) in subset]
                if not keep: continue
                copy = go.Figure(data=[trace]).data[0]
                copy.x = [trace.x[i] for i in keep]
                copy.y = [trace.y[i] for i in keep]
                panel.add_trace(copy)
            panels.append((panel, f'样本 {start+1}–{min(start+12,len(names))} / {len(names)}'))
        return panels
    if traces and all(t.type == 'bar' for t in traces):
        horizontal = traces[0].orientation == 'h'
        names = list(traces[0].y if horizontal else traces[0].x)
        if len(names) <= 12: return [(figure, '')]
        if not all(list(t.y if horizontal else t.x) == names for t in traces):
            return [(figure, '')]
        panels = []
        for start in range(0,len(names),12):
            panel = go.Figure(figure)
            for trace in panel.data:
                trace.x = list(trace.x)[start:start+12]
                trace.y = list(trace.y)[start:start+12]
            panels.append((panel, f'样本 {start+1}–{min(start+12,len(names))} / {len(names)}'))
        return panels
    if len(traces) > 12 and all(t.type == 'scatter' and 'lines' in (t.mode or 'lines') for t in traces):
        return [(go.Figure(data=traces[i:i+12],layout=figure.layout),
                 f'样本曲线 {i+1}–{min(i+12,len(traces))} / {len(traces)}') for i in range(0,len(traces),12)]
    return [(figure, '')]


def export_vector(figure, path):
    """Export supported RNA/MultiQC traces to SVG, with text as embedded paths.

    Unsupported traces fail explicitly. Vector lines/points/text are retained;
    large heatmap cells use a 400 dpi raster layer inside the SVG.
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
    width = 6.45
    height = max(2.7, min(7.0, float(meta.get('print_height', 4.0))))
    if figure.data and all(t.type=='bar' and t.orientation=='h' for t in figure.data):
        height = max(2.7, min(7., 1.4 + .3*len(figure.data[0].y)))
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
        for i, trace in enumerate(figure.data):
            ax, xcfg, ycfg = axes[trace.xaxis or 'x', trace.yaxis or 'y']
            name = plain(trace.name); label = name if trace.showlegend is not False else '_nolegend_'
            x = list(trace.x) if trace.x is not None else []
            y = list(trace.y) if trace.y is not None else []
            if trace.type == 'scatter' and not any(v is not None for v in x):
                continue
            if trace.type == 'scatter':
                mode = trace.mode or 'lines'
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
                        cb.ax.set_title('Adjusted\nP value', fontsize=8.5, pad=9)
                        cb.formatter = FuncFormatter(lambda value,pos:f'{value:.1e}'); cb.update_ticks()
                        values = np.unique(np.round(np.quantile(size_values, [.0,.5,1])).astype(int))
                        handles = [Line2D([],[],marker='o',linestyle='',markerfacecolor='#8b9cad',
                                           markeredgecolor='#637083',markersize=np.sqrt(v*scale),label=str(v)) for v in values]
                        ax.legend(handles=handles,title='Count',bbox_to_anchor=(1.06,.30),loc='upper left',frameon=False)
                        ax.set_xlabel(plain(xcfg.title.text) or 'Gene ratio')
                    else:
                        ax.scatter(x, y, s=float(sizes or 6)**2/2,
                                   color=color(c, PALETTE[i % len(PALETTE)]),
                                   alpha=trace.marker.opacity or .8, label=label, edgecolors='none')
                        if 'text' in mode and trace.text is not None:
                            for px, py, label_text in zip(x, y, trace.text):
                                ax.annotate(str(label_text), (px, py), xytext=(0, 6),
                                            textcoords='offset points', ha='center', fontsize=9)
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
                if len(z)<=40:
                    ax.set_yticks(range(len(y))); ax.set_yticklabels(y,fontsize=7)
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
            for shape in layout.shapes or []:
                if shape.xref not in [None,xkey,xkey+' domain','paper'] or shape.yref not in [None,ykey,ykey+' domain','paper']: continue
                if shape.x0==shape.x1:ax.axvline(shape.x0,color='#8795a5',linewidth=.7,linestyle='--')
                elif shape.y0==shape.y1:ax.axhline(shape.y0,color='#8795a5',linewidth=.7,linestyle='--')
            handles,labels=ax.get_legend_handles_labels()
            if handles and not enrichment and heatmap is None:
                dense_bar = any(t.type=='bar' and t.orientation=='h' and len(t.y)>8 for t in figure.data)
                if len(handles)>8 or dense_bar:
                    wrapped = ['\n'.join(textwrap.wrap(v.replace('_',' '),26)) for v in labels]
                    ax.legend(handles, wrapped, loc='upper center',bbox_to_anchor=(.5,-.25),ncol=2,frameon=False,fontsize=9)
                else:ax.legend(loc='best',frameon=False)
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
