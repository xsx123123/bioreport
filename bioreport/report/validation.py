"""Post-render checks based on PDF text and Typst physical layout observations."""
from collections import defaultdict
import json
from pathlib import Path
import re
import subprocess
from pypdf import PdfReader
from loguru import logger
from bioreport.utils.pdf_metadata import metadata_fields


def query_layout(source, env=None):
    source = Path(source).resolve()
    result = subprocess.run(['quarto', 'typst', 'query', '--root', str(source.parent.parent),
                             str(source), '<bioreport-layout>', '--field', 'value'],
                            # Querying lays out the document again. Reports
                            # with thousands of figures/tables exceed a minute.
                            cwd=source.parent, env=env, text=True, capture_output=True, timeout=600)
    if result.returncode:
        raise RuntimeError('Typst layout query failed: ' + (result.stderr or result.stdout)[-2000:])
    # Quarto versions may forward the bundled CLI stdout through stderr.
    for line in (result.stdout+'\n'+result.stderr).splitlines():
        if line.lstrip().startswith('['):
            return json.loads(line)
    raise RuntimeError('Typst returned no layout observations')


def validate_observations(observations):
    groups = defaultdict(list)
    errors = []
    for item in observations:
        groups[(item['kind'],item['id'])].append(item)
    headings = sorted((v for v in observations if v['kind']=='heading'), key=lambda v:(v['page'],v['y']))
    for intro in (v for v in observations if v['kind']=='intro'):
        previous = [h for h in headings if (h['page'],h['y']) <= (intro['page'],intro['y'])]
        if previous and previous[-1]['page'] != intro['page']:
            errors.append({'check':'orphan_heading','id':intro['id'],'heading_page':previous[-1]['page'],'paragraph_page':intro['page']})
    for (kind, identity), items in groups.items():
        if kind == 'figure':
            images = {v['page'] for v in items if v['part']=='image'}
            captions = {v['page'] for v in items if v['part']=='caption'}
            if images != captions or not images:
                errors.append({'check':'figure_caption', 'id':identity,'image_pages':sorted(images),'caption_pages':sorted(captions)})
        if kind == 'table':
            captions = [v for v in items if v['part']=='caption']
            first_rows = [v for v in items if v['part']=='row-0']
            if captions and (len(captions) != 1 or not first_rows
                             or captions[0]['page'] != first_rows[0]['page']
                             or captions[0]['y'] >= first_rows[0]['y']):
                errors.append({'check':'table_caption', 'id':identity})
            pages = {v['page'] for v in items if v['part'].startswith('row-')}
            headers = {v['page'] for v in items if v['part']=='header'}
            if pages - headers: errors.append({'check':'missing_header','id':identity,'pages':sorted(pages-headers)})
            if any(v['part']=='small' for v in items) and len(pages)>1:
                errors.append({'check':'small_table_split','id':identity,'pages':sorted(pages)})
            if len(pages)>1:
                continuation = {v['page'] for v in items if v['part']=='continuation'}
                for page in sorted(pages)[1:]:
                    if page not in continuation: errors.append({'check':'missing_continuation_label','id':identity,'page':page})
                    rows = {v['part'] for v in items if v['page']==page and v['part'].startswith('row-')}
                    if len(rows)<2: errors.append({'check':'single_row_continuation','id':identity,'page':page})
    return errors


def validate_pdf(path, config, observations=None):
    reader = PdfReader(path)
    texts = [page.extract_text() or '' for page in reader.pages]
    errors = []
    blank = [i+1 for i,text in enumerate(texts) if not text.strip()]
    if blank: errors.append({'check':'blank_pages','pages':blank})
    from bioreport.registry import get_registry
    from bioreport.modules import selected_modules
    has_rna=any(get_registry().canonical(m).startswith('rna.') for m in selected_modules(config))
    if has_rna and (not texts or 'CygnusX' not in texts[0] or config.get('project',{}).get('project_id','') not in texts[0]):
        errors.append({'check':'cover_first'})
    for key,value in metadata_fields(config).items():
        if (reader.metadata or {}).get(key) != value: errors.append({'check':'metadata','field':key})
    if observations is None:
        errors.append({'check':'layout_observations_missing'})
    else:
        errors.extend(validate_observations(observations))
    compact = re.sub(r'\s+', '', '\n'.join(texts))
    result = {'page_count':len(texts), 'blank_pages':blank,
              'metadata':dict(reader.metadata or {}), 'errors':errors,
              'status':'FAIL' if errors else 'PASS',
              'scope':'PDF metadata, blank text pages, physical table rows/headers and figure-caption co-location',
              'pending_checks':['content_ratio','content_consistency','provenance_integrity','visual_regression'],
              'cover_first': bool(texts and 'CygnusX' in texts[0]),
              'text_characters':len(compact)}
    try:
        result['pages'] = page_content_metrics(path)
        result['pending_checks'].remove('content_ratio')
        exempt = {1,2}
        # References and architecture can have intentionally low occupancy.
        exempt.update(i+1 for i,t in enumerate(texts) if '报告生成架构' in t or '参考文献' in t[:100])
        result['warnings'] = [{'check':'low_content_ratio',**m} for m in result['pages'] if m['page'] not in exempt and m['content_ratio']<.55]
    except ImportError:
        result['warnings'] = [{'check':'page_metrics_unavailable','install':'bioreport[validation]'}]
    navigation = validate_navigation(path, reader=reader, texts=texts)
    result['navigation'] = navigation
    result['errors'].extend(navigation['errors'])
    result['status'] = 'FAIL' if result['errors'] else 'PASS'
    reader.close()
    return result


def write_validation(pdf, source, config, env=None):
    logger.info('PDF validation: querying physical layout...')
    observations = query_layout(source, env)
    output = Path(pdf).parent
    (output/'layout-observations.json').write_text(json.dumps(observations,ensure_ascii=False,indent=2))
    logger.info('PDF validation: checking {} layout observations and rendered pages...', len(observations))
    validation = validate_pdf(pdf, config, observations)
    blocks = output / 'report-blocks-pdf.jsonl'
    if blocks.exists():
        logger.info('PDF validation: checking source result consistency...')
        from .content_validation import validate_content
        content = validate_content(config, blocks)
        (output/'content-validation.json').write_text(json.dumps(content,ensure_ascii=False,indent=2))
        validation['content_validation'] = content['status']
        validation['errors'].extend(content['errors'])
        validation['pending_checks'].remove('content_consistency')
        validation['status'] = 'FAIL' if validation['errors'] else 'PASS' 
    (output/'pdf-validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2))
    return validation


def page_content_metrics(path):
    """Measure body occupancy in 5 mm raster bands, excluding running headers."""
    import numpy as np
    import pypdfium2 as pdfium
    metrics=[]
    document=pdfium.PdfDocument(path)
    try:
        for number,page in enumerate(document,1):
            bitmap=page.render(scale=1)
            pixels=bitmap.to_numpy()
            # Crop the shared A4 body, without counting running page furniture.
            body=pixels[74:-68,62:-62,:3]
            ink=body.min(axis=2)<210
            band=14
            occupied=[bool(ink[i:i+band].sum()>ink[i:i+band].size*.001) for i in range(0,len(ink),band)]
            metrics.append({'page':number,'content_ratio':sum(occupied)/max(1,len(occupied)),
                            'ink_ratio':float(ink.mean())})
            bitmap.close();page.close()
    finally:document.close()
    return metrics


def _raw_destination_bytes(value):
    """Recover the raw PDF name bytes pypdf may have decoded with the wrong codec.

    Typst writes UTF-8 destination names without a BOM, so pypdf sometimes
    decodes them as latin-1 mojibake (TextStringObject) and sometimes keeps the
    original bytes (ByteStringObject). Both must compare equal.
    """
    original = getattr(value, 'original_bytes', None)
    if original is not None: return bytes(original)
    if isinstance(value, bytes): return bytes(value)
    return str(value).encode('utf-8')


def _destination_page_numbers(reader):
    """Map raw destination-name bytes to 1-based page numbers.

    Tree values are indirect references to explicit-destination arrays
    ``[page, /XYZ, ...]``, so resolve them and map the page object instead of
    relying on pypdf's Destination handling.
    """
    pages = {}
    page_ids={p.indirect_reference.idnum:i for i,p in enumerate(reader.pages)}
    def page_of(value):
        try:
            if hasattr(value,'get_object'): value=value.get_object()
            if isinstance(value,list) and value:
                first=value[0]
                indirect=getattr(first,'indirect_reference',None) or first
                number=page_ids.get(getattr(indirect,'idnum',None))
                return None if number is None else number+1
            return reader.get_destination_page_number(value)+1
        except Exception:
            return None
    def record(name, destination):
        number=page_of(destination)
        if number is not None: pages[_raw_destination_bytes(name)]=number
    root = reader.trailer['/Root']
    flat = root.get('/Dests')
    if flat is not None:
        for name, destination in flat.get_object().items(): record(name, destination)
    tree = root.get('/Names')
    if tree is not None:
        pending = [tree.get_object().get('/Dests')]
        while pending:
            node = pending.pop()
            if node is None: continue
            node = node.get_object()
            pending.extend(node.get('/Kids', []) or [])
            entries = node.get('/Names') or []
            for index in range(0, len(entries)-1, 2): record(entries[index], entries[index+1])
    return pages


def validate_navigation(path, *, reader=None, texts=None):
    """Check outline targets and printed TOC numbers against PDF destinations."""
    owns_reader = reader is None
    if owns_reader:
        reader=PdfReader(path)
    errors=[];bookmarks=0;toc_links=0
    compact=lambda value:re.sub(r'\s+','',value)
    # The full validation already extracted every page. Reuse that work and
    # the parsed PDF objects rather than reading a thousand-page PDF twice.
    if texts is None:
        texts=[p.extract_text() or '' for p in reader.pages]
    texts=[compact(text) for text in texts]
    def walk(items):
        nonlocal bookmarks
        for item in items:
            if isinstance(item,list):walk(item)
            else:
                bookmarks+=1
                page=reader.get_destination_page_number(item)
                if page is None or page<0 or page>=len(texts) or compact(item.title) not in texts[page]:
                    errors.append({'check':'bookmark_target','title':item.title,'page':page})
    walk(reader.outline)
    try:
        import pypdfium2 as pdfium
        document=pdfium.PdfDocument(path)
        destinations=_destination_page_numbers(reader)
        page_numbers={p.indirect_reference.idnum:i+1 for i,p in enumerate(reader.pages)}
        for index,pdf_page in enumerate(reader.pages):
            if index>3 or '目录' not in texts[index]:continue
            page=document[index];textpage=page.get_textpage()
            for ref in pdf_page.get('/Annots',[]):
                annotation=ref.get_object();action=annotation.get('/A',{})
                if action.get('/S')!='/GoTo':continue
                target=action.get('/D')
                if isinstance(target,list) and target:
                    # Direct page-array destinations carry their own page reference.
                    indirect=getattr(target[0],'indirect_reference',None) or target[0]
                    actual=page_numbers.get(getattr(indirect,'idnum',None))
                else:
                    actual=destinations.get(_raw_destination_bytes(target))
                if actual is None:
                    errors.append({'check':'toc_target_missing','target':str(target)})
                    continue
                left,y1,right,y2=map(float,annotation['/Rect'])
                line=textpage.get_text_bounded(left,min(y1,y2),right,max(y1,y2))
                match=re.search(r'(\d+)\s*$',line)
                toc_links+=1
                if not match or int(match.group(1))!=actual:
                    errors.append({'check':'toc_page_number','line':line,'target_page':actual})
            textpage.close();page.close()
        document.close()
        toc_status='PASS' if toc_links and not errors else 'FAIL'
    except ImportError:toc_status='UNVERIFIED'
    if owns_reader:
        reader.close()
    return {'bookmarks':bookmarks,'toc_links':toc_links,'toc_status':toc_status,'errors':errors}
