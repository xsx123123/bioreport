"""Unified Plotly visual style for BioReport figures.

Every interactive chart (RNA results, QC/MultiQC, volcano, enrichment)
shares the same look: the report web fonts, one color system derived from
the print palette, and consistent axes, gridlines, legends and tooltips.
Draw helpers call ``style_figure`` at creation time; ``export_config``
keeps the PNG download settings identical across charts.

Grouped charts and continuous-scale charts can also carry interactive
``updatemenus`` dropdowns (pure ``restyle`` payloads, so they keep working
in the exported static HTML): readers can switch the discrete group
palette or the continuous colorscale directly in the browser.
"""
from __future__ import annotations

import re

import plotly.graph_objects as go

from .print_theme import PALETTE, PALETTES

# Aligned with templates/theme/styles.css design tokens.
INK = '#243746'        # primary text / marker outlines
MUTED = '#64748b'      # secondary text, tick labels
GRID = '#e4e8ed'       # light gridlines
AXIS_LINE = '#b4bec9'  # axis spines and ticks
GUIDE = '#8795a5'      # threshold / reference lines
SURFACE = '#ffffff'

# Same stack as the report theme ($font-family-sans-serif in bioreport.scss).
# Unquoted family names: quoted ones break kaleido's text measurement.
FONT_FAMILY = ('BioReport-Latin, BioReport-CN, Source Sans 3, '
               'HarmonyOS Sans SC, -apple-system, Segoe UI, Arial, sans-serif')

_AXIS = dict(
    showgrid=True,
    gridcolor=GRID,
    gridwidth=1,
    zeroline=False,
    showline=True,
    linecolor=AXIS_LINE,
    linewidth=1,
    ticks='outside',
    tickcolor=AXIS_LINE,
    ticklen=5,
    tickfont=dict(size=12, color=MUTED),
    title=dict(font=dict(size=13, color=INK)),
)

TEMPLATE = go.layout.Template(
    layout=dict(
        font=dict(family=FONT_FAMILY, size=13, color=INK),
        title=dict(font=dict(size=17, color=INK), x=0, xanchor='left',
                   pad=dict(b=12)),
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        colorway=list(PALETTE),
        xaxis=_AXIS,
        yaxis=_AXIS,
        legend=dict(
            bgcolor='rgba(0,0,0,0)',
            borderwidth=0,
            font=dict(size=12, color=INK),
            title=dict(font=dict(size=12.5, color=MUTED)),
        ),
        hoverlabel=dict(
            bgcolor=SURFACE,
            bordercolor='#cbd5e1',
            font=dict(family=FONT_FAMILY, size=12, color=INK),
            namelength=-1,
        ),
        coloraxis=dict(
            colorbar=dict(
                thickness=14,
                outlinewidth=0,
                tickfont=dict(size=11, color=MUTED),
                title=dict(font=dict(size=12.5, color=INK)),
            )
        ),
        margin=dict(t=60, b=50, l=60, r=40),
    )
)


def style_figure(fig, *, palette_menu=False, colorscale_menu=None, **layout):
    """Apply the shared BioReport style; keyword layout args take precedence.

    ``palette_menu=True`` adds an interactive dropdown that restyles the
    discrete group colors through every palette in ``PALETTES``;
    ``colorscale_menu='<current scale>'`` adds one that switches the
    continuous colorscale. Both are plain ``restyle`` updatemenus, so they
    keep working in the exported static HTML report.
    """
    fig.update_layout(template=TEMPLATE)
    if layout:
        fig.update_layout(**layout)
    menus = list(fig.layout.updatemenus or [])
    if palette_menu or colorscale_menu is not None:
        # Restyling a figure twice must replace the color menus, not stack them.
        menus = [m for m in menus
                 if not (m.buttons
                         and str(m.buttons[0].label).startswith(('Palette: ', 'Scale: ')))]
    if palette_menu:
        menu = palette_updatemenu(fig)
        if menu is not None:
            menus.append(menu)
    if colorscale_menu is not None:
        menu = colorscale_updatemenu(fig, current=colorscale_menu)
        if menu is not None:
            menus.append(menu)
    if menus:
        fig.update_layout(updatemenus=menus)
    return fig


def export_config(filename, *, height=None, width=None, scale=4,
                  responsive=True, remove=('lasso2d', 'select2d')):
    """Uniform PNG download / modebar config for interactive charts."""
    return {
        'toImageButtonOptions': {
            'format': 'png',
            'filename': filename,
            'height': height,
            'width': width,
            'scale': scale,
        },
        'displaylogo': False,
        'modeBarButtonsToRemove': list(remove),
        'responsive': responsive,
    }


# ---------------------------------------------------------------------------
# Interactive color switchers (Plotly updatemenus + restyle)
# ---------------------------------------------------------------------------

# Continuous colorscales offered by colorscale_updatemenu; the figure's own
# scale is always listed first and stays active.
COLORSCALES = ('Viridis', 'Blues', 'Cividis', 'RdBu_r', 'RdYlBu', 'Portland')

_HEX = re.compile(r'^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$')


def _norm_hex(value):
    h = value.lstrip('#').lower()
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    return '#' + h


def _hex_to_rgba(hex_color, alpha):
    h = _norm_hex(hex_color).lstrip('#')
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f'rgba({r},{g},{b},{alpha})'


def _split_color(value):
    """Return (hex, alpha|None) for a CSS color string, else None."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if _HEX.match(value):
        return _norm_hex(value), None
    match = re.match(r'rgba?\(\s*([^)]+?)\s*\)$', value)
    if match:
        parts = [p.strip() for p in match.group(1).split(',')]
        try:
            r, g, b = (float(parts[i]) for i in range(3))
            alpha = float(parts[3]) if len(parts) > 3 else None
        except (ValueError, IndexError):
            return None
        return '#%02x%02x%02x' % (int(r), int(g), int(b)), alpha
    return None


def _trace_attr(trace, attr):
    obj = trace
    for part in attr.split('.'):
        obj = getattr(obj, part, None)
        if obj is None:
            return None
    return obj


def _primary_attrs(trace):
    """Color-bearing attributes a discrete palette should restyle."""
    if trace.type == 'bar':
        return ('marker.color',)
    if trace.type in ('violin', 'box'):
        return ('fillcolor', 'line.color')
    if trace.type == 'scatter':
        mode = trace.mode or ''
        return ('marker.color',) if 'markers' in mode else ('line.color',)
    return ()


def _is_dummy(trace):
    """Legend-only placeholder traces carry no data coordinates.

    Only xy traces can be placeholders; heatmaps legitimately omit x/y.
    """
    if trace.type not in ('scatter', 'bar', 'box', 'violin'):
        return False
    def blank(values):
        return values is None or all(v is None for v in values)
    return blank(trace.x) and blank(trace.y)


def _menu(x=1.0, y=1.02, active=0, buttons=()):
    return dict(
        type='dropdown',
        direction='down',
        showactive=True,
        active=active,
        x=x, xanchor='right', y=y, yanchor='bottom',
        bgcolor=SURFACE, bordercolor='#cbd5e1', borderwidth=1,
        font=dict(size=11, color=INK),
        pad=dict(r=2, t=2),
        buttons=list(buttons),
    )


def palette_updatemenu(fig):
    """Dropdown restyling discrete trace colors through every PALETTES entry.

    Traces sharing a base color keep sharing one after the switch, so group
    identity is preserved; violin fills keep their original alpha.
    """
    colored = [(i, t) for i, t in enumerate(fig.data)
               if not _is_dummy(t) and _primary_attrs(t)]
    if not colored:
        return None
    base_order = []
    color_index = []
    extra = 0
    for _, trace in colored:
        base = next((s for s in (_split_color(_trace_attr(trace, a))
                                 for a in _primary_attrs(trace)) if s), None)
        if base is not None:
            if base[0] not in base_order:
                base_order.append(base[0])
            color_index.append(base_order.index(base[0]))
        else:
            # Traces without an explicit color follow the default colorway.
            color_index.append(len(base_order) + extra)
            extra += 1
    attrs = sorted({a for _, t in colored for a in _primary_attrs(t)})
    trace_ids = [i for i, _ in colored]
    names = list(PALETTES)
    display = {'seaside': 'Seaside', 'apple': 'Apple', 'ibm': 'IBM', 'candy': 'Candy'}
    buttons = []
    for name in names:
        colors = PALETTES[name]
        updates = {}
        for (_, trace), index in zip(colored, color_index):
            color = colors[index % len(colors)]
            for attr in attrs:
                current = _trace_attr(trace, attr)
                split = _split_color(current)
                if split is not None and split[1] is not None:
                    value = _hex_to_rgba(color, split[1])
                elif attr == 'fillcolor':
                    value = _hex_to_rgba(color, 0.5 if current is None else 1)
                else:
                    value = color
                updates.setdefault(attr, []).append(value)
        buttons.append(dict(label=f'Palette: {display.get(name, name.title())}',
                            method='restyle', args=[updates, trace_ids]))
    return _menu(active=names.index('seaside') if 'seaside' in names else 0,
                 buttons=buttons)


def colorscale_updatemenu(fig, *, current=None):
    """Dropdown restyling continuous colorscales (heatmap / bubble charts).

    Plotly Express keeps the scale on ``layout.coloraxis`` when a trace
    references a shared coloraxis, so buttons combine a trace restyle with
    a layout relayout (``method='update'``) as needed. ``current`` names
    the scale the figure already uses so it stays the active, first entry;
    when omitted it is detected from string-valued trace scales.
    """
    groups = {}   # trace attribute -> [trace indices]
    axes = set()  # referenced layout coloraxes carrying a colorscale
    detected = current
    layout = fig.layout
    for i, trace in enumerate(fig.data):
        if _is_dummy(trace):
            continue
        value = getattr(trace, 'colorscale', None)
        if value is not None:
            groups.setdefault('colorscale', []).append(i)
            if detected is None and isinstance(value, str):
                detected = value
        marker = getattr(trace, 'marker', None)
        mscale = getattr(marker, 'colorscale', None) if marker is not None else None
        if mscale is not None:
            groups.setdefault('marker.colorscale', []).append(i)
            if detected is None and isinstance(mscale, str):
                detected = mscale
        for ref in (getattr(trace, 'coloraxis', None),
                    getattr(marker, 'coloraxis', None) if marker is not None else None):
            axis = getattr(layout, ref, None) if ref else None
            if axis is not None and axis.colorscale is not None:
                axes.add(ref)
    if not groups and not axes:
        return None
    scales = list(COLORSCALES)
    if detected in scales:
        scales.remove(detected)
        scales.insert(0, detected)
    trace_ids = sorted({i for ids in groups.values() for i in ids})
    buttons = []
    for scale in scales:
        data_update = {attr: [scale] * len(trace_ids) for attr in groups}
        layout_update = {f'{axis}.colorscale': scale for axis in sorted(axes)}
        if groups and axes:
            args = [data_update, layout_update, trace_ids]
            method = 'update'
        elif axes:
            args = [layout_update]
            method = 'relayout'
        else:
            args = [data_update, trace_ids]
            method = 'restyle'
        buttons.append(dict(label=f'Scale: {scale}', method=method, args=args))
    return _menu(active=0, buttons=buttons)
