"""Exercise offline DataTables search, comparison tabs and Plotly gene highlights.

Run: BIOREPORT_TEST_BROWSER=firefox python tests/verify_volcano_link.py
"""
import json
import os
from pathlib import Path

import IPython.display as ipd
import numpy as np
import pandas as pd
from playwright.sync_api import sync_playwright

from bioreport.utils import html_table, render_output
from omics.rna.analysis.plot_utils import plot_volcano_pvalue

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/volcano-link-validation'
OUT.mkdir(parents=True, exist_ok=True)


def fixture(language):
    for name in ('BIOREPORT_OUTPUT_FORMAT', 'BIOREPORT_SHARED_ASSET_DIR', 'BIOREPORT_SHARED_ASSET_URL'):
        os.environ.pop(name, None)
    os.environ['BIOREPORT_LANGUAGE'] = language
    render_output._plotly_loaded = render_output._itables_loaded = False
    tables, plots = [], []
    table_blocks, plot_blocks = [], []
    ipd.display = lambda value: tables.append(value.data)
    html_table.display = ipd.display
    render_output.display = lambda value: plots.append(value.data)
    source = pd.DataFrame({'ENSEMBL': [f'G{i:03}' for i in range(24)],
                           'Symbol': ['DUP' if i in (5, 18) else f'Gene{i}' for i in range(24)],
                           'log2FoldChange': [float(i - 10) for i in range(24)],
                           'pvalue': [10. ** (-(i % 6 + 1)) for i in range(24)]})
    source['Description'] = ['基因描述 ' * 1000] * len(source)
    source.loc[7, 'pvalue'] = np.nan
    source.loc[9, 'ENSEMBL'] = '<G&"009>'
    for index, comparison in enumerate(('A_vs_Control', 'B_vs_Control')):
        frame = source.copy()
        if index:
            frame['log2FoldChange'] *= -1
        html_table.show_compact_table(frame, volcano_comparison=comparison)
        table_blocks.append(''.join(tables)); tables.clear()
        fig = plot_volcano_pvalue(frame, comparison, col_logfc='log2FoldChange', col_pval='pvalue', comparison=comparison)
        fig.update_layout(width=800, height=450)
        render_output.show_figure(fig)
        plot_blocks.append(''.join(plots)); plots.clear()
    bootstrap = Path('/opt/quarto/share/formats/html/bootstrap/dist/bootstrap.min.js').read_text()
    nav = lambda prefix: ('<ul class="nav" role="tablist">' + ''.join(
        f'<li><a id="{prefix}-tab-{i}" class="nav-link {"active" if not i else ""}" '
        f'data-bs-toggle="tab" href="#{prefix}-pane-{i}" role="tab" '
        f'aria-selected="{"true" if not i else "false"}">Comparison {i}</a></li>' for i in range(2)) + '</ul>')
    panes = lambda prefix, blocks: '<div class="tab-content">' + ''.join(
        f'<div id="{prefix}-pane-{i}" class="tab-pane {"active" if not i else ""}" role="tabpanel">{block}</div>'
        for i, block in enumerate(blocks)) + '</div>'
    html = (f'<!doctype html><html lang="{language}"><head><meta charset="utf-8">'
            '<style>body{margin:24px;font:14px sans-serif}.tab-pane{display:none}.tab-pane.active{display:block}'
            '.nav{display:flex;gap:24px;list-style:none}.nav-link{display:block;padding:12px}.nav-link.active{background:#e2e8f0}'
            '.report-plot{max-width:900px}.report-data-table{scroll-margin-top:16px}</style>'
            f'<script>{bootstrap}</script></head><body><h1>Gene table / volcano linkage</h1>'
            + nav('table') + panes('table', table_blocks) + '<h2>Volcano plots</h2>'
            + nav('plot') + panes('plot', plot_blocks) + '</body></html>')
    path = OUT / f'linked-{language}.html'
    path.write_text(html)
    return path


paths = [fixture(language) for language in ('zh', 'en')]
with sync_playwright() as p:
    try:
        browser_name = os.environ.get('BIOREPORT_TEST_BROWSER', 'chromium')
        browser = getattr(p, browser_name).launch(args=['--no-sandbox'] if browser_name == 'chromium' else [])
        checks = []
        for path in paths:
            page = browser.new_page(viewport={'width': 1100, 'height': 900})
            errors, remote = [], []
            page.on('pageerror', lambda error: errors.append(str(error)))
            for protocol in ('https', 'http'):
                page.route(protocol + '://**/*', lambda route: (remote.append(route.request.url), route.abort()))
            page.goto(path.as_uri())
            page.wait_for_function("document.querySelectorAll('.report-lazy-plot').length===2")
            assert page.locator('#plot-pane-1 .js-plotly-plot').count() == 0
            page.locator('#table-tab-1').click()
            region = page.locator('#table-pane-1')
            search = region.locator('input[type=search]')
            search.wait_for()
            search.fill('G018')
            gene = region.locator('.report-gene-locate')
            page.wait_for_function("document.querySelector('#table-pane-1 table[data-ready]')?._reportTable.rows({search:'applied'}).count()===1")
            gene.click()
            page.wait_for_function("document.querySelector('#plot-pane-1 .js-plotly-plot').data.some(t=>t.meta?.bioreport_gene_highlight)")
            assert page.locator('#plot-pane-1').is_visible()
            selected = page.locator('#plot-pane-1 .js-plotly-plot')
            point = selected.evaluate("c=>{const t=c.data.find(t=>t.meta?.bioreport_gene_highlight);return {x:t.x,y:t.y,text:t.text,range:c._fullLayout.xaxis.range}}")
            assert point['x'] == [-8.] and point['text'] == ['DUP (G018)'], point
            assert min(point['range']) <= -8 <= max(point['range'])
            assert page.locator('#plot-pane-0 .js-plotly-plot').evaluate_all("nodes=>nodes.every(c=>!c.data.some(t=>t.meta?.bioreport_gene_highlight))")
            toolbar = page.locator('#plot-pane-1 .report-volcano-tools')
            toolbar.wait_for(state='visible')
            assert 'G018' in toolbar.inner_text() and 'log2FC = -8' in toolbar.inner_text()
            if os.environ.get('BIOREPORT_CAPTURE_SCREENSHOTS') == '1':
                page.screenshot(path=str(OUT / f'{path.stem}-highlight.png'), timeout=10000)
            print('PASS first highlight',path.name,flush=True)
            toolbar.locator('button').nth(1).click()
            print('PASS back',path.name,flush=True)
            assert search.input_value() == 'G018'
            selected.evaluate("async c=>await Plotly.relayout(c,{'xaxis.range':[0,1],'yaxis.range':[0,1]})")
            gene.click()
            page.wait_for_function("document.querySelector('#plot-pane-1 .js-plotly-plot')._fullLayout.xaxis.range[0] <= -8")
            toolbar.locator('button').nth(1).click()
            # Copy/CSV exports retain raw IDs and full precision, with no action markup.
            exported = region.locator('table[data-ready]').evaluate("t=>t._reportTable.buttons.exportData({orthogonal:'export',columns:':visible'}).body")
            assert len(exported) == 1 and exported[0][0] == 'G018' and exported[0][3] == 1e-1, exported
            print('PASS raw export',path.name,flush=True)
            # A symbol shared by two different genes must not cross-select the other ID.
            search.fill('G005')
            page.wait_for_function("document.querySelector('#table-pane-1 .report-gene-locate')?.textContent.includes('G005')")
            region.locator('.report-gene-locate').click()
            page.wait_for_function("document.querySelector('#plot-pane-1 .js-plotly-plot').data.find(t=>t.meta?.bioreport_gene_highlight)?.text[0]==='DUP (G005)'")
            assert selected.evaluate("c=>c.data.filter(t=>t.meta?.bioreport_gene_highlight).length") == 1
            print('PASS duplicate symbols',path.name,flush=True)
            # Missing coordinates produce a useful message without highlighting a false point.
            toolbar.locator('button').nth(1).click()
            search.fill('G007')
            page.wait_for_function("document.querySelector('#table-pane-1 .report-gene-locate')?.textContent.includes('G007')")
            region.locator('.report-gene-locate').click()
            hint = region.locator('.report-volcano-hint')
            page.wait_for_function("()=>/坐标|coordinates/.test(document.querySelector('#table-pane-1 .report-volcano-hint').textContent)")
            assert '坐标' in hint.inner_text() or 'coordinates' in hint.inner_text()
            print('PASS missing coordinates',path.name,flush=True)
            # Sorting/pagination must still resolve source rows, not visible row offsets.
            search.fill('')
            region.locator('table[data-ready]').evaluate("t=>t._reportTable.order([0,'desc']).page.len(5).draw().page('last').draw('page')")
            first = region.locator('.report-gene-locate').first
            row_id = first.evaluate("b=>b.closest('table')._reportTable.row(b.closest('tr')).data()[0]")
            first.click()
            page.wait_for_function("c=>document.querySelector('#plot-pane-1 .js-plotly-plot').data.find(t=>t.meta?.bioreport_gene_highlight)?.text[0].includes(c)",arg=row_id)
            toolbar.locator('button').first.click()
            page.wait_for_function("!document.querySelector('#plot-pane-1 .js-plotly-plot').data.some(t=>t.meta?.bioreport_gene_highlight)")
            assert not errors and not remote, (errors, remote)
            checks.append({'fixture': path.name, 'search_and_location': True, 'comparison_tabs': True,
                           'duplicate_symbols': True, 'invalid_coordinates': True, 'raw_export': True,
                           'sort_and_pagination': True, 'clear': True, 'offline': True})
            print('PASS', path.name, flush=True)
            page.close()
        (OUT / 'verification.json').write_text(json.dumps({'browser': browser_name, 'checks': checks}, indent=2))
        print('PASS: offline table / volcano linkage', flush=True)
        browser.close()
    except BaseException:
        import traceback
        traceback.print_exc()
        raise
