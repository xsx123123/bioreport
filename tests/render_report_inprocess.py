"""Render real QMD cells without a Jupyter socket, for restricted-host review.

This is a verification utility, not a production execution engine. It executes
trusted, composed report Python in source order, captures display outputs, then
runs Quarto/Pandoc/Typst normally with --no-execute. Statistical functions and
input files are unchanged. Normal hosts should use `bioreport run`.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def render(config_path: Path, output: Path, output_format: str, language=None):
    config_path, output = config_path.resolve(), output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    os.environ['REPORT_CONFIG'] = str(config_path)
    if language:
        os.environ['BIOREPORT_LANGUAGE'] = language
    os.environ['BIOREPORT_OUTPUT_FORMAT'] = output_format
    os.environ['BIOREPORT_DELIVERY_DIR'] = str(output)
    block_manifest = output / f'report-blocks-{output_format}.jsonl'
    block_manifest.unlink(missing_ok=True)
    os.environ['BIOREPORT_BLOCK_MANIFEST'] = str(block_manifest)
    os.environ.setdefault('MPLCONFIGDIR', str(output / 'cache' / 'matplotlib'))
    os.environ['XDG_CACHE_HOME'] = str(output / 'cache')
    os.environ['XDG_DATA_HOME'] = str(output / 'share')
    from bioreport.utils.fonts import typst_font_paths
    os.environ['TYPST_FONT_PATHS'] = typst_font_paths()
    from bioreport.config import load_config, report_artifact_name
    from bioreport.renderer import render_templates
    config = load_config(config_path)
    if language:
        from bioreport.i18n import localized_config
        config = localized_config(config, language)
    # The in-process utility renders one format at a time; align the composer's
    # format selection with the requested output even for configs pinned to pdf.
    config['report']['output_format'] = output_format
    if config.get('report', {}).get('layout', 'single') != 'single':
        raise ValueError('The verification utility supports single documents')
    staged = output / 'templates'
    shutil.copytree(ROOT / 'templates', staged, dirs_exist_ok=True)
    shutil.copytree(ROOT / 'templates/shared', staged / 'qmd', dirs_exist_ok=True)
    shutil.copytree(ROOT / 'omics/rna/qmd', staged / 'qmd', dirs_exist_ok=True)
    from bioreport.utils.provenance import build_provenance, write_provenance
    from bioreport.modules import selected_modules
    provenance = build_provenance(config, selected_modules(config))
    write_provenance(provenance, staged / 'qmd')
    render_templates(config, str(output / 'rendered'), str(staged))
    if output_format == 'pdf':
        shutil.copyfile(staged / 'qmd/report-plan.json', output / 'report-plan.json')
    source = staged / 'qmd' / ('report_pdf.qmd' if output_format == 'pdf' else 'report.qmd')
    original = source.read_text()
    source.with_suffix('.source.qmd').write_text(original)
    outputs = []
    import IPython.display as ipd

    def display(*items, **kwargs):
        for item in items:
            if isinstance(item, ipd.Markdown):
                outputs.append(item.data)
            elif isinstance(item, (ipd.HTML, ipd.Javascript)) and output_format == 'html':
                html = item.data if isinstance(item, ipd.HTML) else '<script>' + item.data + '</script>'
                outputs.append('```{=html}\n' + html + '\n```')
            else:
                raise TypeError(f'Unsupported {output_format} display: {type(item).__name__}')

    ipd.display = display
    from bioreport.utils import render_output
    render_output.display = display
    render_output._plotly_loaded = render_output._itables_loaded = False
    render_output._figure_count = render_output._table_count = 0
    namespace = {}
    cell_count = 0
    execution_log = []

    def execute(match):
        nonlocal cell_count
        cell_count += 1
        code = match.group(1)
        label = re.search(r'(?m)^#\| label:\s*(.*)', code)
        label = label.group(1) if label else str(cell_count)
        print(f'Executing cell {cell_count}: {label}', flush=True)
        outputs.clear()
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exec(compile(code, f'{source.name}:{label}', 'exec'), namespace)
        execution_log.append({'cell':label, 'stdout':stdout.getvalue(), 'display_outputs':len(outputs)})
        return '\n\n'.join(outputs)

    previous_directory = Path.cwd()
    try:
        os.chdir(source.parent)
        executed = re.sub(r'```\{python\}\n(.*?)\n```', execute, original, flags=re.DOTALL)
        executed = re.sub(r'`\{python\}\s+([^`]+)`', lambda m:str(eval(m.group(1), namespace)), executed)
        source.write_text(executed)
    finally:
        os.chdir(previous_directory)
    (output / 'execution.json').write_text(json.dumps(execution_log, ensure_ascii=False, indent=2))
    command = ['quarto', 'render', str(source.relative_to(staged)), '--to',
               'typst' if output_format == 'pdf' else 'html', '--no-execute']
    with (output / 'render.log').open('w') as log:
        result = subprocess.run(command, cwd=staged, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        print((output / 'render.log').read_text(), file=sys.stderr)
        raise RuntimeError(f'Quarto failed: {output / "render.log"}')
    artifact = output / 'rendered' / 'qmd' / f'{source.stem}.{output_format}'
    final = output / report_artifact_name(config, output_format, language)
    shutil.copyfile(artifact, final)
    if output_format == "html" and language:
        from bioreport.i18n import add_language_switch
        add_language_switch(final, config, language)
    if output_format == 'pdf':
        from bioreport.utils.pdf_metadata import set_pdf_metadata
        set_pdf_metadata(final, config)
        from bioreport.report.validation import write_validation
        validation = write_validation(final, source.with_suffix(".typ"), config)
        if validation["errors"]:
            raise RuntimeError(f"PDF validation failed: {output / 'pdf-validation.json'}")
    from bioreport.utils.provenance import write_delivery_manifests
    write_delivery_manifests(config, provenance, output)
    from bioreport.utils.provenance import validate_delivery_manifests
    validate_delivery_manifests(config, output)
    print(final)
    return final


def review_pdf(path: Path):
    import pypdfium2 as pdfium
    from pypdf import PdfReader
    from PIL import Image, ImageDraw
    directory = path.parent / 'pages'
    if directory.exists():
        for pattern in ('page-*.png', 'contact-*.png'):
            for stale in directory.glob(pattern):
                stale.unlink()
    directory.mkdir(exist_ok=True)
    reader = PdfReader(path)
    doc = pdfium.PdfDocument(path)
    pages = []
    for i, page in enumerate(doc):
        filename = directory / f'page-{i+1:02}.png'
        bitmap = page.render(scale=1.5)
        bitmap.to_pil().save(filename)
        bitmap.close()
        pages.append({'page':i+1, 'image':filename.name, 'text':reader.pages[i].extract_text()})
        page.close()
    doc.close()
    for first in range(0, len(pages), 6):
        sheet = Image.new('RGB', (1500, 1480), '#d8dee5')
        draw = ImageDraw.Draw(sheet)
        for j in range(first, min(first+6,len(pages))):
            im = Image.open(directory / pages[j]['image'])
            im.thumbnail((490, 700))
            x, y = (j-first)%3*500, (j-first)//3*740
            sheet.paste(im, (x+5,y+25))
            draw.text((x+8,y+8), f'Page {j+1}', fill='black')
        sheet.save(directory / f'contact-{first//6+1:02}.png')
    representative = {'cover':0}
    needles = {'summary':'平均 Q30', 'qc':'fastp 测序质控', 'volcano':'差异表达火山图', 'enrichment':'上调富集分析'}
    for name, needle in needles.items():
        for i, page in enumerate(pages[2:],start=2):
            if re.sub(r'\s+','',needle) in re.sub(r'\s+','',page['text']):
                representative[name] = i
                break
    for name, index in representative.items():
        shutil.copyfile(directory / pages[index]['image'], path.parent / f'{name}.png')
    bookmarks = []
    def walk(items):
        for item in items:
            if isinstance(item,list): walk(item)
            else: bookmarks.append({'title':item.title, 'page':reader.get_destination_page_number(item)+1})
    walk(reader.outline)
    review = {'pages':pages, 'bookmarks':bookmarks, 'representative':{name:index+1 for name,index in representative.items()},
              'execution':'trusted QMD cells in process; Quarto --no-execute; no mocked scientific functions'}
    (path.parent / 'review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2))
    print(f'Rendered {len(pages)} page previews in {directory}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-c', '--config', type=Path, required=True)
    parser.add_argument('-o', '--output', type=Path, required=True)
    parser.add_argument('--format', choices=['html','pdf'], default='pdf')
    parser.add_argument('--language', choices=['zh','en'])
    parser.add_argument('--pages', action='store_true')
    args = parser.parse_args()
    artifact = render(args.config, args.output, args.format, args.language)
    if args.pages:
        if args.format != 'pdf': parser.error('--pages requires PDF')
        review_pdf(artifact)
