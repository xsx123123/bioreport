"""Exercise the actual rendered HTML offline in Chromium; never mock Plotly/DOM."""
import argparse
import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright


def verify(source, output):
    output.mkdir(parents=True,exist_ok=True)
    checks=[];errors=[];chart_details=[]
    def record_check(value):
        checks.append(value)
        (output/'html-progress.json').write_text(json.dumps({'checks':checks},ensure_ascii=False,indent=2))
    try:
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True,args=['--no-sandbox'],timeout=15000)
            page=browser.new_page(viewport={'width':1440,'height':1100})
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(source.resolve().as_uri(),wait_until='load',timeout=120000)
            if page.locator('iframe#report').count():
                page.wait_for_function("document.querySelector('#report')?.contentDocument?.querySelector('.report-navbar')",timeout=120000)
                record_check('report frame initialized')
                page.locator('#loading').wait_for(state='hidden',timeout=120000)
                frame=page.frame_locator('#report')
                assert page.locator('#report').evaluate('(node)=>node.contentDocument.documentElement.lang.toLowerCase().startsWith("zh")')
                record_check('Chinese edition loaded')
                frame.locator('[data-report-language] [data-language="en"]' if frame.locator('[data-report-language] [data-language]').count() else '[data-report-language]').evaluate('(node)=>node.click()')
                page.wait_for_function("document.querySelector('#report')?.contentDocument?.documentElement?.lang === 'en'",timeout=120000)
                page.locator('#loading').wait_for(state='hidden',timeout=120000)
                assert frame.locator('.report-navbar').count()==1
                record_check('single-file English edition switch')
                frame.locator('[data-report-language] [data-language="zh"]' if frame.locator('[data-report-language] [data-language]').count() else '[data-report-language]').evaluate('(node)=>node.click()')
                page.wait_for_function("document.querySelector('#report')?.contentDocument?.documentElement?.lang?.toLowerCase().startsWith('zh')",timeout=120000)
                page.locator('#loading').wait_for(state='hidden',timeout=120000)
                record_check('single-file Chinese edition switch')
                report=frame
            else:
                report=page
            if page.locator('iframe#report').count():
                page.wait_for_function("typeof document.querySelector('#report').contentWindow.Plotly !== 'undefined'",timeout=30000)
            else:
                page.wait_for_function("typeof Plotly !== 'undefined'",timeout=30000)
            links=report.locator('.report-navbar a.nav-link')
            for i in range(links.count()):
                link=links.nth(i);name=link.inner_text();target=link.get_attribute('aria-controls')
                link.evaluate('(node)=>node.click()')
                page.wait_for_function("target => {const doc = document.querySelector('iframe#report')?.contentDocument || document; const visible = [...doc.querySelectorAll('.report-page')].filter(n=>n.getBoundingClientRect().height>0); return visible.length===1 && visible[0].id===target;}", arg=target, timeout=30000)
                visible=report.locator('.report-page:visible')
                if visible.count()!=1 or visible.first.get_attribute('id')!=target:
                    raise AssertionError('Navigation failed: '+name)
                record_check('navigation:'+name)
                charts=report.locator('.report-page:visible .plotly-graph-div:visible')
                details = charts.evaluate_all("""nodes=>nodes.map(node=>{
                    if (!node._fullLayout || !node._fullData.length) throw new Error('Plotly did not initialize');
                    if (node.clientWidth<=0 || node.clientHeight<=0) throw new Error('Plotly has no visible dimensions');
                    return {id:node.id,pairedScreen:!!node.layout.meta?.paired_screen,
                        coverageGroups:!!node.layout.meta?.coverage_groups,
                        width:node.clientWidth,height:node.clientHeight,
                        legends:node.data.filter(t=>t.showlegend!==false && t.name).map(t=>t.name)};
                })""")
                chart_details.extend(details)
                for detail in details:
                    if not (detail['pairedScreen'] or detail['coverageGroups']):
                        continue
                    chart = report.locator('[id="'+detail['id']+'"]')
                    if detail['pairedScreen'] or detail['coverageGroups']:
                        chart.evaluate("""async node=>{
                            const win=node.ownerDocument.defaultView;
                            if(node.layout.meta.paired_screen && JSON.stringify(node.layout.xaxis.range)!==JSON.stringify(node.layout.xaxis2.range)) throw Error('Read panels have different ranges');
                            if(node.layout.meta.coverage_groups && (node.layout.xaxis.range[0]!==0 || node.layout.xaxis.range[1]!==100)) throw Error('Coverage axis is not 0–100X');
                            const index=node.data.findIndex(t=>t.showlegend!==false);
                            await win.Plotly.restyle(node,{visible:'legendonly'},[index]);
                            if(node.data[index].visible!=='legendonly') throw Error('Legend hiding failed');
                            await win.Plotly.restyle(node,{visible:true},[index]);
                            const saved=[...node.layout.xaxis.range];
                            await win.Plotly.relayout(node,{'xaxis.range':[10,30]});
                            if(node.layout.xaxis.range[0]!==10) throw Error('Zoom failed');
                            await win.Plotly.relayout(node,{'xaxis.range':saved});
                            win.Plotly.Fx.hover(node,[{curveNumber:index,pointNumber:1}]);
                            if(!node.querySelector('.hoverlayer .hovertext')) throw Error('Hover tooltip failed');
                            win.Plotly.Fx.unhover(node);
                            const legend=node.querySelector('.legend')?.getBoundingClientRect();
                            const titles=node.querySelectorAll(node.layout.meta.paired_screen?'.annotation':'.gtitle');
                            for(const title of titles){
                                const box=title.getBoundingClientRect();
                                if(legend && box.left<legend.right && box.right>legend.left && box.top<legend.bottom && box.bottom>legend.top) throw Error('Legend overlaps chart title');
                            }
                        }""")
                        record_check('interactive:'+('FastQ Screen pair' if detail['pairedScreen'] else 'QualiMap group coverage'))
                        chart.screenshot(path=str(output/('fastq-screen.png' if detail['pairedScreen'] else 'coverage.png')))
                if charts.count():record_check('plotly:'+str(charts.count()))
            assert report.locator('table').count()>0
            assert report.locator('table.dataTable, .dt-container, .itables').count()>0
            record_check('ITables initialized')
            assert report.locator('#TOC a').count()>0
            # The about page hides the TOC by design; return to a content page first.
            report.locator('.report-navbar a.nav-link').first.evaluate('(node)=>node.click()')
            page.wait_for_timeout(250)
            report.locator('#TOC a').first.evaluate('(node)=>node.click()');page.wait_for_timeout(250)
            record_check('TOC navigation')
            page.screenshot(path=str(output/'html.png'),full_page=True)
            browser.close()
    except Exception as error:
        errors.append(type(error).__name__+': '+str(error)[:4000])
    result={'status':'FAIL' if errors else 'PASS','checks':checks,'charts':chart_details,'errors':errors}
    (output/'html-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('html',type=Path);parser.add_argument('--output',type=Path,default=Path('output/html-validation'))
    parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    if args.worker:
        result=verify(args.html,args.output)
    else:
        args.output.mkdir(parents=True,exist_ok=True)
        command=[sys.executable,__file__,str(args.html),'--output',str(args.output),'--worker']
        process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
        try:
            stdout,stderr=process.communicate(timeout=300)
            target=args.output/'html-validation.json'
            if target.exists():result=json.loads(target.read_text())
            else:result={'status':'FAIL','checks':[],'errors':[f'Browser worker exited {process.returncode}: '+stderr[-3000:]]}
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL)
            process.communicate()
            progress_path=args.output/'html-progress.json'
            partial=json.loads(progress_path.read_text()) if progress_path.exists() else {}
            result={'status':'FAIL','checks':partial.get('checks',[]),'errors':['Browser process did not finish within 300 seconds.']}
        (args.output/'html-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False));raise SystemExit(result['status']!='PASS')
