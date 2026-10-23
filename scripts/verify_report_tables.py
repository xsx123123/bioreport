"""Check every Results table, including hidden tabs, and validate CSV exports."""
import argparse
import csv
import json
import math
import time
from pathlib import Path
from playwright.sync_api import sync_playwright


def json_safe(value):
    if isinstance(value,float) and not math.isfinite(value):
        return None
    if isinstance(value,list):
        return [json_safe(item) for item in value]
    if isinstance(value,dict):
        return {key:json_safe(item) for key,item in value.items()}
    return value


def verify(source, output, config=None):
    output.mkdir(parents=True, exist_ok=True)
    results=[];errors=[];remote=[]
    expected=[]
    if config:
        import pandas as pd
        from bioreport.config import load_config
        settings=load_config(config)
        for path in Path(settings['input_files']['deg_dir']).glob('*.csv'):
            expected.append((path,pd.read_csv(path)))
    with sync_playwright() as pw:
        browser=pw.chromium.launch(args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':1440,'height':900}, accept_downloads=True,
                                    permissions=['clipboard-read','clipboard-write'])
        context.route('http://**/*',lambda r:(remote.append(r.request.url),r.abort()))
        context.route('https://**/*',lambda r:(remote.append(r.request.url),r.abort()))
        page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(source.resolve().as_uri(),timeout=120000)
        page.locator('#loading').wait_for(state='hidden',timeout=120000)
        initial=page.locator('#report').element_handle().content_frame()
        if initial.locator('.report-data-table').count():
            assert initial.locator('.report-data-table table[data-ready="true"]').count()==0, 'Results tables initialized on the home page'
        for language in ['zh','en']:
            if language=='en':
                page.frame_locator('#report').locator('[data-report-language]').click()
                page.wait_for_function("document.querySelector('#report')?.contentDocument?.documentElement?.lang==='en'",timeout=120000)
                page.locator('#loading').wait_for(state='hidden',timeout=120000)
            frame=page.locator('#report').element_handle().content_frame()
            frame.locator('.report-navbar a.nav-link').filter(has_text='Results' if language=='en' else '分析结果').click()
            frame.wait_for_function("document.querySelector('.report-page[data-active=true] .report-data-table') || Array.from(document.querySelectorAll('.report-page[data-active=true] table.dataTable')).some(n=>n._reportTable)",timeout=60000)
            lazy=frame.locator('.report-page[data-active=true] .report-data-table')
            regions=lazy if lazy.count() else frame.locator('.report-page[data-active=true] .dt-container, .report-page[data-active=true] .dataTables_wrapper')
            for index in range(regions.count()):
                region=regions.nth(index)
                init_start=time.perf_counter()
                region.evaluate('''node=>{
                    const panes=[];
                    for(let pane=node.closest('.tab-pane');pane;pane=pane.parentElement.closest('.tab-pane')) panes.unshift(pane);
                    for(const pane of panes) document.querySelector('[data-bs-target="#'+pane.id+'"]')?.click();
                }''')
                region.scroll_into_view_if_needed()
                if lazy.count():
                    region.locator('table[data-ready="true"]').wait_for(timeout=60000)
                    wrapper=region.locator('.dt-container, .dataTables_wrapper')
                else:
                    wrapper=region
                ready_s=time.perf_counter()-init_start
                page.wait_for_timeout(250)
                assert wrapper.is_visible()
                table=wrapper.locator('.dt-scroll-body table.dataTable, .dataTables_scrollBody table.dataTable').first
                if not table.count():table=wrapper.locator('table.dataTable').last
                metadata=table.evaluate('''n=>{
                    const api=n._reportTable;
                    api.columns.adjust();
                    return {rows:api.rows().count(),columns:api.columns().header().toArray().map(h=>h.textContent),
                        first:api.row(0).data(),last:api.row(api.rows().count()-1).data()};
                }''')
                print(language,index,metadata['rows'],flush=True)
                metadata['visible_to_ready_s']=ready_s
                metadata['presentation']=wrapper.evaluate('''wrapper=>{
                    const head=wrapper.querySelector('.dt-scroll-head table, .dataTables_scrollHead table') || wrapper.querySelector('table');
                    const body=wrapper.querySelector('.dt-scroll-body table, .dataTables_scrollBody table') || head;
                    const headers=[...head.querySelectorAll('thead th')];
                    const cells=[...body.querySelectorAll('tbody td')];
                    const rows=[...body.querySelectorAll('tbody tr')];
                    return {
                        nowrap:headers.every(n=>getComputedStyle(n).whiteSpace==='nowrap'),
                        numericRight:cells.filter(n=>n.classList.contains('dt-right')).every(n=>getComputedStyle(n).textAlign==='right'),
                        padding:cells.every(n=>getComputedStyle(n).paddingTop==='6px' && getComputedStyle(n).paddingLeft==='12px'),
                        font:cells.every(n=>getComputedStyle(n).fontSize==='13px'),
                        noVerticalBorders:cells.every(n=>parseFloat(getComputedStyle(n).borderLeftWidth)===0 && parseFloat(getComputedStyle(n).borderRightWidth)===0),
                        tableHeight:head.getBoundingClientRect().height + rows.reduce((sum,n)=>sum+n.getBoundingClientRect().height,0),
                        rows:rows.length,
                        visibleColumns:body._reportTable.columns(':visible').header().toArray().map(n=>n.textContent)
                    };
                }''')
                presentation=metadata['presentation']
                assert all(presentation[key] for key in ('nowrap','numericRight','padding','font','noVerticalBorders')), presentation
                if presentation['rows'] <= 10:
                    assert presentation['tableHeight'] <= 400, presentation
                assert not ('ENSEMBL' in presentation['visibleColumns'] and 'Symbol' in presentation['visibleColumns']
                            and table.evaluate("n=>{const api=n._reportTable;const names=api.columns().header().toArray().map(h=>h.textContent);const a=names.indexOf('ENSEMBL'), b=names.indexOf('Symbol');return a>=0&&b>=0&&api.rows().data().toArray().every(row=>row[a]===row[b]);}")), presentation
                search=wrapper.locator('input[type=search]')
                search.fill('__no_matching_bioreport_record__');page.wait_for_timeout(250)
                assert table.evaluate("n=>n._reportTable.rows({search:'applied'}).count()") == 0
                wrapper.screenshot(path=str(output/f'{language}-table-{index+1}-search.png'))
                search.fill('');page.wait_for_timeout(250)
                header=wrapper.locator('.dt-scroll-head th, .dataTables_scrollHead th').first
                header.click();page.wait_for_timeout(150)
                wrapper.screenshot(path=str(output/f'{language}-table-{index+1}-sort.png'))
                pages=table.evaluate('n=>n._reportTable.page.info().pages')
                next_button=wrapper.locator('button.next:not(.disabled), a.next:not(.disabled)').first
                if pages>1:
                    next_button.click();page.wait_for_timeout(100)
                    assert table.evaluate('n=>n._reportTable.page.info().page')==1
                    wrapper.screenshot(path=str(output/f'{language}-table-{index+1}-page-2.png'))
                    table.evaluate("n=>n._reportTable.page('first').draw('page')")
                csv_button=wrapper.locator('.buttons-csv').first
                assert csv_button.count()==1
                assert wrapper.locator('.buttons-copy').count()==1
                frame.evaluate("navigator.clipboard.writeText('')")
                wrapper.locator('.buttons-copy').click()
                copied=''
                for attempt in range(100):
                    copied=frame.evaluate('navigator.clipboard.readText()')
                    if copied:break
                    page.wait_for_timeout(100)
                first_id=metadata['first'][0]
                last_id=metadata['last'][0]
                if isinstance(first_id,list):first_id=first_id[-1]
                if isinstance(last_id,list):last_id=last_id[-1]
                assert str(first_id) in copied and str(last_id) in copied, ('Copy IDs missing',first_id,last_id,copied[:200])
                assert copied.count('\n')>=metadata['rows'], ('Copy truncated',copied.count('\n'),metadata['rows'])
                metadata['copy_verified']=True
                with page.expect_download(timeout=30000) as download_info:
                    csv_button.click()
                exported=output/f'{language}-table-{index+1}.csv'
                download_info.value.save_as(exported)
                with exported.open(encoding='utf-8-sig',newline='') as stream:rows=[row for row in csv.reader(stream) if row]
                assert len(rows)==metadata['rows']+1,(len(rows),metadata)
                if config:
                    import pandas as pd
                    actual=pd.read_csv(exported,float_precision='round_trip')
                    # Only the verified duplicate presentation column may be
                    # omitted. Every retained source value must still match.
                    export_sources=[(path,original.drop(columns=['Symbol'])
                        if {'ENSEMBL','Symbol'} <= set(original.columns) and original['ENSEMBL'].equals(original['Symbol'])
                        else original) for path,original in expected]
                    candidates=[(path,original) for path,original in export_sources if list(actual.columns)==list(original.columns)]
                    if candidates:
                        for path,original in candidates:
                            key=original.columns[0]
                            try:
                                pd.testing.assert_frame_equal(
                                    actual.sort_values(key).reset_index(drop=True),
                                    original.sort_values(key).reset_index(drop=True),
                                    check_dtype=False, check_exact=True)
                            except AssertionError:
                                continue
                            metadata['source_verified']=str(path)
                            metadata['verified_source_rows']=len(original)
                            break
                        assert 'source_verified' in metadata, 'DEG export differs from every configured source with matching columns'
                metadata['numeric_sort']=table.evaluate('''n=>{
                    const api=n._reportTable;
                    const first=api.row(0).data();
                    const raw=v=>Array.isArray(v)&&v.length===2?v[1]:v;
                    const column=first.findIndex(v=>typeof raw(v)==='number');
                    if(column<0)return 'no numeric columns';
                    api.order([column,'asc']).draw();
                    const values=api.column(column,{order:'applied'}).data().toArray().map(raw).filter(v=>typeof v==='number');
                    return values.every((v,i)=>i===0 || values[i-1]<=v);
                }''')
                assert metadata['numeric_sort'] in [True,'no numeric columns']
                metadata['csv_rows']=len(rows)-1
                metadata['csv_file']=exported.name
                metadata.update(language=language,table=index+1)
                results.append(metadata)
                (output/'tables-progress.json').write_text(json.dumps(json_safe(results),ensure_ascii=False,indent=2,allow_nan=False))
                wrapper.screenshot(path=str(output/f'{language}-table-{index+1}.png'))
        browser.close()
    result={'status':'FAIL' if errors or remote else 'PASS','errors':errors,'remote':remote,'tables':results}
    (output/'tables-validation.json').write_text(json.dumps(json_safe(result),ensure_ascii=False,indent=2,allow_nan=False))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('html',type=Path);parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--config',type=Path,help='Compare full exported DEG data with the configured source CSVs')
    args=parser.parse_args()
    try:result=verify(args.html,args.output,args.config)
    except Exception as error:
        import traceback
        traceback.print_exc()
        result={'status':'FAIL','errors':[f'{type(error).__name__}: {error}']}
        args.output.mkdir(parents=True,exist_ok=True)
        (args.output/'tables-validation.json').write_text(json.dumps(json_safe(result),ensure_ascii=False,indent=2,allow_nan=False))
    print(json.dumps({key:value for key,value in result.items() if key!='tables'},ensure_ascii=False))
    raise SystemExit(result['status']!='PASS')
