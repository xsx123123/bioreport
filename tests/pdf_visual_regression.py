"""Create a reviewed PDF baseline or compare ten semantic pages against it.

Usage: python tests/pdf_visual_regression.py report.pdf --golden tests/golden/rna
The --update option deliberately replaces the baseline; review pages first.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import sys
import numpy as np
import pypdfium2 as pdfium
from PIL import Image, ImageDraw

NEEDLES = {
    'overview':'Executive Summary', 'project':'样本预览',
    'qc':'Fastp: Filtered Reads', 'pca':'样本 PCA', 'hvg':'主图展示',
    'volcano':'Values exceeding the display range', 'enrichment':'上调富集分析',
    'provenance':'数据完整性校验说明', 'architecture':'Configuration',
}


def screenshot(page):
    scale=1.25
    bitmap=page.render(scale=scale)
    image=bitmap.to_pil().convert('RGB')
    bitmap.close()
    textpage=page.get_textpage()
    text=textpage.get_text_range()
    # Generation time is volatile. Mask only exact date/time glyph rectangles,
    # leaving all surrounding labels, hashes, paths and numbers in comparison.
    for match in re.finditer(r'\d{4}-\d\d-\d\d[T ]\d\d:\d\d:\d\d(?:[+-]\d\d:\d\d)?',text):
        search=textpage.search(match.group())
        found=search.get_next()
        if found:
            start,count=found
            boxes=[textpage.get_charbox(i) for i in range(start,start+count)]
            left=min(b[0] for b in boxes)*scale-2
            right=max(b[2] for b in boxes)*scale+2
            top=(page.get_height()-max(b[3] for b in boxes))*scale-2
            bottom=(page.get_height()-min(b[1] for b in boxes))*scale+2
            ImageDraw.Draw(image).rectangle((left,top,right,bottom),fill='white')
        search.close()
    textpage.close()
    return image


def snapshots(pdf, directory):
    directory.mkdir(parents=True,exist_ok=True)
    doc=pdfium.PdfDocument(pdf)
    texts=[]
    for page in doc:
        textpage=page.get_textpage();texts.append(textpage.get_text_range());textpage.close();page.close()
    selection={'cover':0,'toc':1}
    for name,needle in NEEDLES.items():
        compact=re.sub(r'\s+','',needle)
        matches=[i for i,text in enumerate(texts) if i>1 and compact in re.sub(r'\s+','',text)]
        if not matches: raise ValueError(f'Missing snapshot reading unit: {name} ({needle})')
        selection[name]=matches[0]
    for name,index in selection.items():
        page=doc[index];screenshot(page).save(directory/f'{name}.png');page.close()
    result={'page_count':len(doc),'pages':{k:v+1 for k,v in selection.items()}}
    doc.close()
    return result


def compare(pdf, golden, output):
    current=snapshots(pdf,output/'pages')
    baseline=json.loads((golden/'baseline.json').read_text())
    errors=[];differences=[]
    if current['page_count']!=baseline['page_count']:errors.append('page_count')
    for name in current['pages']:
        a=np.asarray(Image.open(golden/f'{name}.png').convert('RGB'),dtype=float)
        b=np.asarray(Image.open(output/'pages'/f'{name}.png').convert('RGB'),dtype=float)
        if a.shape!=b.shape:
            errors.append(name+':dimensions');continue
        changed=float((np.max(np.abs(a-b),axis=2)>12).mean())
        differences.append({'name':name,'changed_pixel_fraction':changed})
        if changed>.005:errors.append(name)
    result={'status':'FAIL' if errors else 'PASS','errors':errors,'differences':differences,
            'page_count':current['page_count'],'threshold':.005,
            'mask':'Only generation timestamp glyphs; no statistical or figure regions masked.'}
    (output/'visual-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf',type=Path)
    parser.add_argument('--golden',type=Path,default=Path('tests/golden/rna'))
    parser.add_argument('--output',type=Path,default=Path('output/visual-regression'))
    parser.add_argument('--update',action='store_true')
    args=parser.parse_args()
    if args.update:
        baseline=snapshots(args.pdf,args.golden)
        shutil.copyfile(args.pdf,args.golden/'report.pdf')
        baseline['pdf_sha256']=hashlib.sha256(args.pdf.read_bytes()).hexdigest()
        baseline['source_config']='tests/report.rna.pdf.json'
        baseline['renderer']='Quarto 1.8.26 / Typst 0.13.0; bundled fonts; inprocess trusted QMD verification'
        (args.golden/'baseline.json').write_text(json.dumps(baseline,ensure_ascii=False,indent=2))
        print(json.dumps(baseline,ensure_ascii=False))
    else:
        result=compare(args.pdf,args.golden,args.output)
        print(json.dumps(result,ensure_ascii=False));sys.exit(result['status']!='PASS')
