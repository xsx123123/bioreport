"""Subset embedded HTML CJK fonts without touching PDF fonts or report data."""
from __future__ import annotations

import base64
import hashlib
import html
import io
import json
from pathlib import Path
import re
from collections import OrderedDict
from urllib.parse import unquote

from loguru import logger

_STYLE = re.compile(r"(<style\b[^>]*>)(.*?)(</style>)", re.I | re.S)
_FONT_FACE = re.compile(r'@font-face\s*\{[^{}]*\}', re.I)
_FONT_URL = re.compile(r'''url\(\s*['"]?(data:[^,()]+;base64,([A-Za-z0-9+/=\s]+))['"]?\s*\)''', re.I)
_CJK_FAMILY = re.compile(r'''font-family\s*:\s*['"]?BioReport-CN\b''', re.I)
_CACHE: OrderedDict[tuple[str, str], bytes] = OrderedDict()


def report_codepoints(documents: list[str]) -> set[int]:
    """Include rendered text, escaped chart/UI strings and embedded SVG text."""
    # ASCII covers numeric formatting, searches and identifiers; common symbols
    # cover controls, typography and hover labels generated after page load.
    points = set(range(32, 127)) | set(range(0x2000, 0x2070)) | set(range(0x2080, 0x20A0))
    points.update(map(ord, '±×÷°µμΔαβγπ≤≥≠∞−→←↗✓✗'))
    for source in documents:
        text = html.unescape(source)
        points.update(map(ord, text))
        for match in re.finditer(r'(?:\\u[0-9a-fA-F]{4})+', text):
            points.update(map(ord, json.loads('"' + match.group() + '"')))
        for match in re.finditer(r'data:image/svg\+xml;base64,([A-Za-z0-9+/=]+)', text):
            points.update(map(ord, base64.b64decode(match[1]).decode('utf-8')))
        for match in re.finditer(r'''data:image/svg\+xml(?:;charset=[^,]+)?,([^'"\s)]+)''', text):
            points.update(map(ord, unquote(match[1])))
    return {point for point in points if not 0xD800 <= point <= 0xDFFF}


def subset_font_bytes(data: bytes, points: set[int]) -> bytes:
    from fontTools import subset
    from fontTools.ttLib import TTFont

    identity = (hashlib.sha256(data).hexdigest(), hashlib.sha256(','.join(map(str, sorted(points))).encode()).hexdigest())
    if identity in _CACHE:
        _CACHE.move_to_end(identity)
        return _CACHE[identity]
    font = TTFont(io.BytesIO(data), recalcTimestamp=False)
    original = set(font.getBestCmap() or {})
    options = subset.Options()
    options.hinting = True
    options.notdef_glyph = True
    options.notdef_outline = True
    worker = subset.Subsetter(options=options)
    worker.populate(unicodes=points & original)
    worker.subset(font)
    font.flavor = 'woff2'
    buffer = io.BytesIO()
    font.save(buffer)
    font.close()
    result = buffer.getvalue()
    check = TTFont(io.BytesIO(result))
    retained = set(check.getBestCmap() or {})
    check.close()
    missing = (points & original) - retained
    if missing:
        raise ValueError('HTML font subset removed referenced glyphs: ' + ', '.join(f'U+{point:04X}' for point in sorted(missing)))
    _CACHE[identity] = result
    if len(_CACHE) > 8:
        _CACHE.popitem(last=False)
    return result


def subset_html_fonts(paths: list[Path]) -> list[dict]:
    """Use both languages' character union, rewrite CJK faces and report sizes.

    This is a delivery step after Quarto embeds resources and before bilingual
    compression/manifests. Full staged TTF files remain intact for PDF rendering.
    """
    documents = [path.read_text(encoding='utf-8') for path in paths]
    points = report_codepoints(documents)
    metrics = []
    for path, source in zip(paths, documents):
        before = len(source.encode('utf-8'))
        faces = []

        def rewrite_face(match):
            face = match.group()
            if not _CJK_FAMILY.search(face):
                return face

            def rewrite_url(url):
                original = base64.b64decode(url[2])
                reduced = subset_font_bytes(original, points)
                faces.append({'original_bytes': len(original), 'subset_bytes': len(reduced)})
                return "url('data:font/woff2;base64," + base64.b64encode(reduced).decode('ascii') + "')"

            updated = _FONT_URL.sub(rewrite_url, face)
            if updated != face:
                updated = re.sub(r'''format\(\s*['"](?:truetype|opentype|woff2?)['"]\s*\)''', "format('woff2')", updated)
            return updated

        result = _STYLE.sub(lambda style: style[1] + _FONT_FACE.sub(rewrite_face, style[2]) + style[3], source)
        if result != source:
            temporary = path.with_name(path.name + '.font-subset.tmp')
            temporary.write_text(result, encoding='utf-8')
            temporary.replace(path)
        summary = dict(file=path.name, codepoints=len(points), faces=faces,
                       original_html_bytes=before, subset_html_bytes=len(result.encode('utf-8')),
                       removed_referenced_glyphs=0)
        metrics.append(summary)
        logger.info('HTML CJK font subset: {} codepoints; {} faces; {} -> {} font bytes; removed referenced glyphs: 0',
                    len(points),len(faces),sum(face['original_bytes'] for face in faces),sum(face['subset_bytes'] for face in faces))
    return metrics
