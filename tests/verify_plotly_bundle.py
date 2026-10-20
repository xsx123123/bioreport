"""Exercise shipped Cartesian traces and native PNG export offline in Chromium."""
from pathlib import Path
import json
import plotly.graph_objects as go
from playwright.sync_api import sync_playwright
from bioreport.utils import render_output

out=Path('output/cartesian-bundle-validation');out.mkdir(parents=True,exist_ok=True)
shown=[];render_output.display=shown.append;render_output._plotly_loaded=False
for trace in [go.Scatter(x=[1,2],y=[2,1]),go.Bar(x=['A','B'],y=[1,2]),
              go.Heatmap(z=[[1,2],[3,4]]),go.Violin(y=[1,2,3,4,5])]:
    figure=go.Figure(trace);figure.update_layout(width=600,height=400)
    render_output.show_figure(figure)
figure=go.Figure(go.Scatter(x=[.1,.2],y=['Long pathway label','Another pathway']))
figure.update_layout(width=900,height=600,margin=dict(l=290,r=120),meta={'enrichment':True})
render_output.show_figure(figure)
source=out/'cartesian.html';source.write_text('<!doctype html><html><head><meta charset="utf-8"><style>.report-plot{position:relative;width:600px}.report-plot .plotly-graph-div{position:absolute!important;inset:0;width:100%!important;height:100%!important}</style><style>'+Path('templates/theme/styles.css').read_text()+'</style></head><body>'+''.join(value.data for value in shown)+'</body></html>')
with sync_playwright() as pw:
    browser=pw.chromium.launch(args=['--no-sandbox']);context=browser.new_context(accept_downloads=True,viewport={'width':390,'height':844})
    remote=[];errors=[]
    context.route('http://**/*',lambda r:(remote.append(r.request.url),r.abort()))
    context.route('https://**/*',lambda r:(remote.append(r.request.url),r.abort()))
    page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(source.resolve().as_uri())
    page.wait_for_function("document.querySelectorAll('.js-plotly-plot').length===5 && [...document.querySelectorAll('.js-plotly-plot')].every(n=>n._fullLayout)")
    types=page.locator('.plotly-graph-div').evaluate_all('nodes=>nodes.map(n=>n._fullData[0].type)')
    assert types==['scatter','bar','heatmap','violin','scatter']
    sizes=page.locator('.plotly-graph-div').evaluate_all('nodes=>nodes.map(n=>n._fullLayout._size)')
    assert all(size['w']>20 and size['h']>20 for size in sizes),sizes
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+2')
    assert page.locator('.report-chart-scroll').evaluate('n=>n.scrollWidth>n.clientWidth')
    interactions=[]
    for index,kind in enumerate(types):
        graph=page.locator('.plotly-graph-div').nth(index)
        graph.scroll_into_view_if_needed()
        point=graph.locator('.scatterlayer .point, .barlayer .point path, .violinlayer .violin, .heatmaplayer image').first
        # Plotly deliberately places a transparent drag surface over traces.
        point.hover(force=True)
        page.wait_for_function("node => node.querySelector('.hoverlayer')?.textContent.length>0",arg=graph.element_handle())
        before=graph.evaluate('n=>({data:JSON.stringify(n.data), x:[...n._fullLayout.xaxis.range], y:[...n._fullLayout.yaxis.range]})')
        drag=graph.locator('.nsewdrag').first
        box=drag.bounding_box()
        # Restrict the drag to the visible portion of a scrollable chart.
        left=max(box['x'],5); right=min(box['x']+box['width'],385)
        page.mouse.move(left+(right-left)*.15,box['y']+box['height']*.2)
        page.mouse.down()
        page.mouse.move(left+(right-left)*.75,box['y']+box['height']*.8,steps=8)
        page.mouse.up()
        page.wait_for_function("args=>JSON.stringify(args.node._fullLayout.xaxis.range)!==JSON.stringify(args.x)||JSON.stringify(args.node._fullLayout.yaxis.range)!==JSON.stringify(args.y)",arg={'node':graph.element_handle(),'x':before['x'],'y':before['y']})
        assert graph.evaluate('n=>JSON.stringify(n.data)')==before['data']
        graph.locator('.modebar-btn[data-title="Autoscale"]').click()
        interactions.append({'type':kind,'hover':True,'drag_zoom':True,'data_unchanged':True})
        with page.expect_download(timeout=30000) as pending:
            graph.locator('.modebar-btn[data-title*="Download"]').first.click()
        pending.value.save_as(out/f'{kind}-{index}.png')
    assert not remote and not errors,(remote,errors)
    (out/'verification.json').write_text(json.dumps(dict(status='PASS',types=types,interactions=interactions,remote=remote,errors=errors),indent=2))
    browser.close()
print('PASS: scatter, bar, heatmap, violin and PNG downloads with local Cartesian bundle')
