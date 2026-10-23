"""Verify real offline PNG/SVG/PDF downloads and dialog behavior in Chromium.

Run from the repository root: python tests/verify_plotly_download.py
"""
import base64
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright
from pypdf import PdfReader
import plotly.graph_objects as go

from bioreport.utils import render_output
from bioreport.utils.fonts import font_dir
from bioreport.utils.html_fonts import subset_font_bytes


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/plotly-download-validation'
OUT.mkdir(parents=True, exist_ok=True)
for name in ('BIOREPORT_OUTPUT_FORMAT', 'BIOREPORT_SHARED_ASSET_DIR', 'BIOREPORT_SHARED_ASSET_URL'):
    os.environ.pop(name, None)
os.environ['BIOREPORT_LANGUAGE'] = 'zh'
font = subset_font_bytes(
    (font_dir() / 'HarmonyOS_Sans_SC/HarmonyOS_Sans_SC_Regular.ttf').read_bytes(),
    set(range(32, 127)) | set(map(ord, '样本图表表达量分组宽度高度下载格式取消锁定比例恢复默认文件正在导出失败像素尺寸整数之间须为最多支持请减小重试或嵌无损保留矢形')),
)
css = "@font-face{font-family:BioReportTest;src:url(data:font/woff2;base64," + base64.b64encode(font).decode() + ") format('woff2')}"


def fixture(shared=False):
    shown = []
    render_output.display = shown.append
    render_output._plotly_loaded = False
    if shared:
        os.environ['BIOREPORT_SHARED_ASSET_DIR'] = str(OUT / 'assets')
        os.environ['BIOREPORT_SHARED_ASSET_URL'] = 'assets'
    else:
        os.environ.pop('BIOREPORT_SHARED_ASSET_DIR', None)
        os.environ.pop('BIOREPORT_SHARED_ASSET_URL', None)
    traces = [go.Scatter(x=[1, 2, 3], y=[1, 3, 2]), go.Heatmap(z=[[1, 2], [3, 4]])]
    for index, trace in enumerate(traces):
        figure = go.Figure(trace)
        figure.update_layout(title=f'样本图表 {index}', width=600, height=400,
                             font=dict(family='BioReportTest'), xaxis_title='表达量')
        render_output.show_figure(figure)
    path = OUT / ('shared.html' if shared else 'inline.html')
    path.write_text('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                    '<style>' + css + 'body{margin:16px}.report-plot{max-width:600px}</style></head><body>'
                    + ''.join(item.data for item in shown) + '</body></html>', encoding='utf-8')
    return path


paths = [fixture(), fixture(shared=True)]
with sync_playwright() as pw:
    browser_name = os.environ.get('BIOREPORT_TEST_BROWSER', 'chromium')
    browser = getattr(pw, browser_name).launch(args=['--no-sandbox'] if browser_name == 'chromium' else [])
    for path in paths:
        context = browser.new_context(accept_downloads=True, viewport={'width': 1000, 'height': 850})
        remote, errors = [], []
        for protocol in ('http', 'https'):
            context.route(protocol + '://**/*', lambda route: (remote.append(route.request.url), route.abort()))
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(path.as_uri())
        buttons = page.locator('.modebar-btn[data-report-export]')
        buttons.first.wait_for()
        assert buttons.count() == 2
        buttons.first.click()
        dialog = page.locator('.report-export-dialog')
        assert dialog.is_visible()
        assert dialog.locator('[name=format]').input_value() == 'png'
        assert dialog.locator('[name=width]').input_value() == '600'
        assert dialog.locator('[name=height]').input_value() == '400'
        dialog.locator('[name=width]').fill('900')
        assert dialog.locator('[name=height]').input_value() == '600'
        dialog.locator('[name=lock]').uncheck()
        dialog.locator('[name=height]').fill('500')
        dialog.locator('[name=width]').fill('0')
        dialog.locator('[type=submit]').click()
        assert '整数' in dialog.locator('[role=status]').inner_text()
        dialog.locator('[name=width]').fill('16000')
        dialog.locator('[name=height]').fill('16000')
        dialog.locator('[type=submit]').click()
        assert '1600 万' in dialog.locator('[role=status]').inner_text()
        dialog.locator('[data-label=reset]').click()
        assert dialog.locator('[name=lock]').is_checked()
        dialog.locator('[name=lock]').uncheck()
        dialog.locator('[name=width]').fill('800')
        dialog.locator('[name=height]').fill('500')
        downloads = {}
        for fmt in ('png', 'svg', 'pdf'):
            if not dialog.is_visible():
                buttons.first.click()
            dialog.locator('[name=format]').select_option(fmt)
            with page.expect_download(timeout=30000) as pending:
                dialog.locator('[type=submit]').click()
            download = pending.value
            assert download.suggested_filename == f'样本图表_0.{fmt}'
            destination = OUT / f'{path.stem}-chart.{fmt}'
            download.save_as(destination)
            downloads[fmt] = destination
            assert not dialog.is_visible()
        png = Image.open(downloads['png'])
        assert png.size == (800, 500) and png.getbbox()
        svg = ET.parse(downloads['svg']).getroot()
        assert float(svg.attrib['width']) == 800 and float(svg.attrib['height']) == 500
        assert svg.find('.//{http://www.w3.org/2000/svg}path') is not None
        assert 'data:font/woff2;base64,' in downloads['svg'].read_text()
        pdf = PdfReader(downloads['pdf'], strict=True)
        assert len(pdf.pages) == 1
        assert tuple(pdf.pages[0].mediabox) == (0, 0, 600, 375)
        # Compare decoded lossless PDF pixels to the PNG from the same chart.
        pdf_image = pdf.pages[0].images[0].image.convert('RGB')
        assert pdf_image.size == (800, 500)
        png_rgb = Image.new('RGB', png.size, 'white')
        png_rgb.paste(png, mask=png.getchannel('A') if png.mode == 'RGBA' else None)
        np.testing.assert_array_equal(np.asarray(pdf_image), np.asarray(png_rgb))
        buttons.nth(1).click()
        assert dialog.locator('[name=format]').input_value() == 'png'
        assert dialog.locator('[name=width]').input_value() == '600'
        page.keyboard.press('Escape')
        assert not dialog.is_visible()
        page.set_viewport_size({'width': 390, 'height': 844})
        page.wait_for_function("[...document.querySelectorAll('.modebar-btn[data-report-export]')].length===2")
        buttons.first.click()
        assert dialog.locator('[name=width]').input_value() == '800'
        assert dialog.locator('[name=format]').input_value() == 'pdf'
        box = dialog.bounding_box()
        assert box['x'] >= 0 and box['x'] + box['width'] <= 390
        page.screenshot(path=str(OUT / f'{path.stem}-mobile.png'))
        page.keyboard.press('Escape')
        # A failed conversion must leave the controls usable for a retry.
        # IIFE: Playwright otherwise executes the assigned function while
        # serializing the expression's completion value.
        page.evaluate('(()=>{window.originalToImage=Plotly.toImage;'
                      'Plotly.toImage=()=>Promise.reject(new Error("test export failure"));})()')
        buttons.first.click()
        dialog.locator('[type=submit]').click()
        page.wait_for_function("document.querySelector('.report-export-status').textContent.includes('失败')")
        assert dialog.locator('[type=submit]').is_enabled()
        page.evaluate('(()=>{Plotly.toImage=window.originalToImage;})()')
        with page.expect_download(timeout=30000) as pending:
            dialog.locator('[type=submit]').click()
        pending.value.save_as(OUT / f'{path.stem}-retry.pdf')
        assert not remote and not errors, (remote, errors)
        context.close()
    browser.close()
(OUT / 'verification.json').write_text(json.dumps({'status': 'PASS', 'formats': ['png', 'svg', 'pdf'],
    'deliveries': ['inline', 'shared'], 'dimensions': [800, 500], 'offline': True,
    'pdf_lossless_pixels_match_png': True}, indent=2))
print(f'PASS: offline PNG/SVG/PDF export, dimensions, validation, retry and mobile dialog: {OUT}')
