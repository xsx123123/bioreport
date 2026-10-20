"""Embedded font optimization keeps scientific/UI glyphs and original assets."""
import base64
import io
from pathlib import Path
import re

from fontTools.ttLib import TTFont

from bioreport.utils.html_fonts import report_codepoints, subset_html_fonts
from bioreport.utils.fonts import font_dir


def test_codepoints_include_escaped_labels_and_embedded_svg():
    svg=base64.b64encode('<svg><text>番茄</text></svg>'.encode()).decode()
    points=report_codepoints(['<p>质量</p><script>"\\u4e2d"</script><img src="data:image/svg+xml;base64,'+svg+'">'])
    assert set(map(ord,'番茄质量中±−→09e+')) <= points


def test_subset_uses_bilingual_union_and_leaves_pdf_font_untouched(tmp_path):
    source=font_dir()/'HarmonyOS_Sans_SC/HarmonyOS_Sans_SC_Regular.ttf'
    original=source.read_bytes()
    face="@font-face {font-family:'BioReport-CN';src:url('data:font/ttf;base64,"+base64.b64encode(original).decode()+"') format('truetype');}"
    paths=[tmp_path/'zh.html',tmp_path/'en.html']
    bodies=['<p>番茄</p><script>const p=1.23456789e-18;</script>','<p>English</p><script>"\\u4e2d"</script><pre>@font-face{font-family:BioReport-CN;src:url(data:font/ttf;base64,AAAA)}</pre>']
    for path,body in zip(paths,bodies):path.write_text('<style>'+face+'</style>'+body)
    metrics=subset_html_fonts(paths)
    for path,body,metric in zip(paths,bodies,metrics):
        html=path.read_text()
        assert body in html and "format('woff2')" in html
        font=TTFont(io.BytesIO(base64.b64decode(re.search('data:font/woff2;base64,([^\']+)',html)[1])))
        assert set(map(ord,'番茄中English09e+')) <= set(font.getBestCmap())
        font.close()
        assert metric['removed_referenced_glyphs']==0
        assert metric['faces'][0]['subset_bytes'] < len(original)/4
    assert source.read_bytes()==original
