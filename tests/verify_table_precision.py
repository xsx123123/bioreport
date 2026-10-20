from pathlib import Path
import IPython.display as ipd
import pandas as pd
from bioreport.utils import render_output
from playwright.sync_api import sync_playwright
shown=[];ipd.display=shown.append
render_output._itables_loaded=False
from bioreport.utils.visualize_utils import display_gene_expression_table
display_gene_expression_table(pd.DataFrame({'id':['0001','0002'],'pvalue':[1.23456789e-18,0.42]}))
path=Path('output/table-callback.html').resolve();path.write_text('<!doctype html><html><head><meta charset="utf-8"></head><body>'+''.join(i.data for i in shown)+'</body></html>')
with sync_playwright() as pw:
 browser=pw.chromium.launch(args=['--no-sandbox']);page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(path.as_uri());page.wait_for_function("Array.from(document.querySelectorAll('table.dataTable')).some(n=>n._reportTable)",timeout=10000)
 stats=page.locator('.dt-scroll-body table').evaluate("n=>({rows:n._reportTable.rows().count(),first:n._reportTable.row(0).data(),tabindex:n.parentElement.tabIndex})")
 assert stats['rows']==2 and stats['first'][1]==1.23456789e-18 and stats['tabindex']==0,stats
 assert page.locator('.dt-scroll-body tbody tr').first.locator('td').nth(1).inner_text()=='1.235e-18'
 with page.expect_download() as pending:page.locator('.buttons-csv').click()
 target=Path('output/table-callback.csv');pending.value.save_as(target)
 assert '1.23456789e-18' in target.read_text(),target.read_text()
 import csv
 with target.open(newline='') as stream:assert len(list(csv.reader(stream)))==3
 assert not errors,errors
 print('PASS: native table lifecycle callback exposes raw precision and keyboard scrolling',stats)
 browser.close()
