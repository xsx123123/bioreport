import json,os
from pathlib import Path
from omics.rna.analysis.pca_plotly import draw_pca_plotly
from bioreport.utils.render_output import _responsive_figure_html
from plotly.offline import get_plotlyjs
from playwright.sync_api import sync_playwright
os.environ['BIOREPORT_LANGUAGE']='en'
root=Path.cwd();out=root/'output/pca-responsive';out.mkdir(exist_ok=True,parents=True)
fig,config=draw_pca_plotly(root/'examples/rna-seq/data/index/merge_rsem_tpm.tsv',root/'examples/rna-seq/data/index/sample.csv',height_num=500,width_num=1000)
html=_responsive_figure_html(fig,config)
(out/'pca.html').write_text('<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"><style>body{margin:16px}.report-plot .plotly-graph-div{position:absolute!important;inset:0;width:100%!important;height:100%!important}</style><script>'+get_plotlyjs()+'</script></head><body><section id="pca-panel">'+html+'</section></body></html>')
with sync_playwright() as pw:
 browser=pw.chromium.launch(args=['--no-sandbox']);page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto((out/'pca.html').as_uri());page.wait_for_function("document.querySelector('.plotly-graph-div')._fullLayout")
 rows=[];saved=None
 for width,height in [(1440,900),(390,844),(768,1024),(1920,1080)]:
  page.locator('#pca-panel').evaluate("n=>n.style.display='none'")
  page.set_viewport_size(dict(width=width,height=height));page.wait_for_timeout(60)
  page.locator('#pca-panel').evaluate("n=>n.style.display=''")
  page.wait_for_timeout(800)
  value=page.locator('.plotly-graph-div').evaluate('''n=>({domains:[n.layout.xaxis.domain,n.layout.xaxis2.domain,n.layout.yaxis.domain,n.layout.yaxis2.domain],data:JSON.stringify(n.data),width:n.clientWidth,height:n.clientHeight})''')
  data=value.pop('data')
  if saved is None:saved=data
  assert saved==data
  if width==390:assert value['domains'][0]==[0,1] and value['domains'][2]==[.6,1] and value['height']>600
  else:assert value['domains'][2]==[0,1] and value['domains'][0]!=[0,1]
  rows.append(dict(viewport=[width,height],**value));page.screenshot(path=str(out/f'pca-{width}.png'))
 page.locator('.plotly-graph-div').hover()
 with page.expect_download(timeout=30000) as pending:
  page.locator('.modebar-btn[data-title*="Download"]').first.click()
 pending.value.save_as(out/'pca-export.png')
 from PIL import Image
 with Image.open(out/'pca-export.png') as exported:
  assert exported.width>=10000 and exported.height>=5000, exported.size
 assert not errors,errors
 (out/'verification.json').write_text(json.dumps(dict(status='PASS',results=rows,errors=errors),indent=2));browser.close()
print('PASS: PCA reflows both ways at four viewports without changing trace data')
