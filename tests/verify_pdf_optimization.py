"""Audit the 15-sample PDF delivery and export real before/after page captures.

This checks the supplied project's page budget, complete matrix preview, caption
contracts and trailing blank space. It complements numerical plotting tests and
manual inspection of the exported heatmap/volcano/architecture screenshots.
"""
import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pypdfium2 as pdfium
from PIL import Image, ImageDraw
from pypdf import PdfReader

from bioreport.config import load_config


def compact(value):
    return re.sub(r'\s+', '', value)


def capture(pdf, destination):
    destination.mkdir(parents=True, exist_ok=True)
    reader = PdfReader(pdf)
    texts = [page.extract_text() or '' for page in reader.pages]
    chapter_starts = [reader.get_destination_page_number(item) + 1
                      for item in reader.outline if isinstance(item, dict)]
    chapter_ends = {page-1 for page in chapter_starts} | {len(texts)}
    document = pdfium.PdfDocument(pdf)
    trailing = []
    for number, page in enumerate(document, 1):
        bitmap = page.render(scale=1)
        pixels = bitmap.to_numpy()
        body = pixels[74:-68, 62:-62, :3]
        occupied = np.flatnonzero((body.min(axis=2) < 210).sum(axis=1) > 2)
        fraction = float((len(body)-occupied[-1]-1)/len(body)) if len(occupied) else 1.
        trailing.append({'page': number, 'trailing_blank_fraction': round(fraction, 4),
                         'chapter_end': number in chapter_ends,
                         'exempt': number <= 2 or number in chapter_ends})
        bitmap.close()
        page.render(scale=1.5).to_pil().save(destination / f'page-{number:02}.png')
        page.close()
    document.close()
    return {'page_count': len(texts), 'trailing_space': trailing}, texts


def verify(before, after, config_path, output):
    output.mkdir(parents=True, exist_ok=True)
    baseline, before_text = capture(before, output/'before')
    current, after_text = capture(after, output/'after')
    cfg = load_config(config_path)
    text = compact('\n'.join(after_text))
    checks = {}
    checks['page_budget'] = current['page_count'] <= 23
    checks['no_orphan_sample_panels'] = not re.search(r'样本(?:曲线|列)?13[–—-]15/15', text)
    checks['no_half_page_trailing_blank_in_nonfinal_chapter_pages'] = not any(
        row['trailing_blank_fraction'] > .5 and not row['exempt'] for row in current['trailing_space'])
    checks['caption_noise_removed'] = '颜色与图例对应输入样本或统计类别' not in text
    checks['cap_label_consistent'] = '上限+' not in text and '50+' in text
    source_counts = {label: text.count(compact(label)) for label in (
        '质控图读取 MultiQC 保存的 fastp 汇总数据集',
        '外源污染评估图读取 MultiQC 保存的 FastQ Screen 汇总数据集',
        '比对质控图读取 MultiQC 保存的 QualiMap BamQC 汇总数据集')}
    checks['one_source_note_per_qc_section'] = all(count == 1 for count in source_counts.values())
    blocks = [json.loads(line) for line in (after.parent/'report-blocks-pdf.zh.jsonl').read_text().splitlines()]
    figures = [block for block in blocks if block['type'] == 'figure']
    heatmaps = [f for f in figures if '高变异基因热图' in f['caption']]
    checks['one_heatmap'] = len(heatmaps) == 1
    checks['one_fastq_screen_pair'] = sum('FastQ Screen R1/R2' in f['caption'] for f in figures) == 1
    checks['volcano_caption_has_top_five'] = any('各 Top 5' in f['caption'] for f in figures)
    checks['coverage_caption'] = any('0–100X' in f['caption'] and 'min–max' in f['caption'] for f in figures)
    matrix = pd.read_csv(cfg['input_files']['tpm_file'], sep='\t', index_col=0)
    expected = matrix.mean(axis=1).sort_values(ascending=False, kind='stable').head(8).index.astype(str).tolist()
    preview = next(b for b in blocks if b['type'] == 'table' and '基因表达量矩阵' in b['caption'])
    observed = [row[preview['headers'].index('Gene ID')] for row in preview['rows']]
    checks['matrix_top_eight_across_all_samples'] = observed == expected
    checks['matrix_six_of_fifteen'] = '6/15个样本列' in text
    comparisons = {}
    needles = {'summary': '差异表达客观统计汇总', 'matrix': '基因表达量矩阵（TPM）预览',
               'heatmap': '高变异基因热图：', 'volcano': 'Salt_vs_AC 差异表达火山图',
               'coverage': 'Coverage histogram。', 'architecture': '报告生成架构',
               'fastq-screen': ('FastQ Screen: Mapped Reads', 'FastQ Screen R1/R2')}
    for name, needle in needles.items():
        pages = []
        for edition,texts in enumerate((before_text, after_text)):
            term = needle[edition] if isinstance(needle,tuple) else needle
            pages.append(next(i+1 for i,t in enumerate(texts) if i>1 and compact(term) in compact(t)))
        a = Image.open(output/'before'/f'page-{pages[0]:02}.png').convert('RGB')
        b = Image.open(output/'after'/f'page-{pages[1]:02}.png').convert('RGB')
        canvas = Image.new('RGB', (a.width+b.width, max(a.height,b.height)+30), 'white')
        canvas.paste(a,(0,30)); canvas.paste(b,(a.width,30))
        draw=ImageDraw.Draw(canvas)
        draw.text((15,8),f'Before - page {pages[0]} / {baseline["page_count"]}',fill='black')
        draw.text((a.width+15,8),f'After - page {pages[1]} / {current["page_count"]}',fill='black')
        canvas.save(output/f'{name}-comparison.png')
        comparisons[name] = {'before_page':pages[0], 'after_page':pages[1], 'file':f'{name}-comparison.png'}
    result = {'status':'PASS' if all(checks.values()) else 'FAIL', 'checks':checks,
              'before':baseline,'after':current,'source_counts':source_counts,
              'matrix_gene_ids':observed,'comparisons':comparisons}
    (output/'pdf-optimization-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before',type=Path);parser.add_argument('after',type=Path)
    parser.add_argument('--config',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=verify(args.before,args.after,args.config,args.output)
    print(json.dumps({'status':result['status'],'checks':result['checks'],
                      'pages':[result['before']['page_count'],result['after']['page_count']]},ensure_ascii=False))
    raise SystemExit(result['status'] != 'PASS')
