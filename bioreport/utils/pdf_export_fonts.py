"""Small, offline TrueType subsets for browser chart PDF downloads."""
import base64
from functools import lru_cache
from html import unescape
from io import BytesIO
import json
from collections.abc import Mapping

from .fonts import font_dir
from .html_fonts import subset_font_bytes


@lru_cache(maxsize=64)
def _font_data(relative_path, characters):
    from fontTools.ttLib import TTFont

    # The browser PDF engine cannot reliably re-embed transformed WOFF2 glyf
    # tables. Decode with fontTools at report generation time, retaining real
    # TrueType glyph outlines rather than relying on browser font conversion.
    reduced = subset_font_bytes((font_dir() / relative_path).read_bytes(), set(map(ord, characters)))
    font = TTFont(BytesIO(reduced), recalcTimestamp=False)
    font.flavor = None
    output = BytesIO()
    font.save(output)
    font.close()
    return base64.b64encode(output.getvalue()).decode('ascii')


def chart_pdf_fonts(figure):
    # Visit text directly: serializing large numeric arrays only to collect
    # their ASCII characters can dominate preparation for hundreds of plots.
    points = set(range(32, 127)) | set(map(ord, '−±×÷°µμΔαβγπ≤≥≠∞'))
    def collect(value):
        if isinstance(value, str):
            points.update(map(ord, unescape(value)))
        elif isinstance(value, Mapping):
            for item in value.values():
                collect(item)
        elif hasattr(value, 'dtype'):
            if value.dtype.kind not in 'biufc':
                for item in value.flat:
                    collect(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                collect(item)
    collect(figure.to_plotly_json())
    latin = ''.join(chr(point) for point in sorted(points) if point < 0x2E80)
    chinese = ''.join(chr(point) for point in sorted(points))
    fonts = {'BioReport-Latin': {
        variant: _font_data(f'Source_Sans_3/static/SourceSans3-{suffix}.ttf', latin)
        for variant, suffix in [('normal', 'Regular'), ('bold', 'Bold'),
                                ('italics', 'Italic'), ('bolditalics', 'BoldItalic')]
    }}
    if any(point >= 0x2E80 for point in points):
        fonts['BioReport-CN'] = {'normal': _font_data('HarmonyOS_Sans_SC/HarmonyOS_Sans_SC_Regular.ttf', chinese)}
    return fonts
