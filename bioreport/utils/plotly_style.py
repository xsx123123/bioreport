"""Unified Plotly visual style for BioReport figures.

Every interactive chart (RNA results, QC/MultiQC, volcano, enrichment)
shares the same look: the report web fonts, one color system derived from
the print palette, and consistent axes, gridlines, legends and tooltips.
Draw helpers call ``style_figure`` at creation time; ``export_config``
keeps the PNG download settings identical across charts.
"""
from __future__ import annotations

import plotly.graph_objects as go

from .print_theme import PALETTE

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


def style_figure(fig, **layout):
    """Apply the shared BioReport style; keyword layout args take precedence."""
    fig.update_layout(template=TEMPLATE)
    if layout:
        fig.update_layout(**layout)
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
