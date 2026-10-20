"""Regenerate shipped static diagrams with the official Mermaid CLI Node API.

Install: PUPPETEER_SKIP_DOWNLOAD=1 npm install --prefix build/tools/mermaid-cli --no-save @mermaid-js/mermaid-cli@12.0.0
Run: PYTHONPATH=. python scripts/precompile_mermaid.py
"""
import hashlib
import os
import json
from pathlib import Path
import re
import subprocess
from bioreport.utils.font_stage import stage_fonts
from bioreport.utils.html_fonts import report_codepoints, subset_font_bytes
from bioreport.utils.mermaid_static import BLOCK, diagram_digest, diagram_source

root=Path(__file__).resolve().parents[1]
assets=root/'templates/shared/assets';work=root/'build/mermaid-precompile';work.mkdir(parents=True,exist_ok=True)
sources=[root/'templates/shared/about.qmd',root/'omics/rna/qmd/en/about.qmd',root/'omics/rna/qmd/workflow.qmd',root/'omics/rna/qmd/en/workflow.qmd']
jobs={};locations=[]
for path in sources:
    content=path.read_text()
    content=re.sub(r'\{\{< include assets/architecture.mmd >\}\}',(assets/'architecture.mmd').read_text(),content)
    for match in BLOCK.finditer(content):
        key=diagram_digest(match[1]);output=assets/f'mermaid-{key[:16]}.svg'
        jobs[key]={'digest':key,'source':diagram_source(match[1]),'output':str(output)}
        locations.append({'source':str(path.relative_to(root)),'digest':key})
jobfile=work/'jobs.json';jobfile.write_text(json.dumps(list(jobs.values()),ensure_ascii=False))
font_css=stage_fonts(work/'fonts')
points=report_codepoints([job['source'] for job in jobs.values()])
css=font_css.read_text()
for path in (font_css.parent/'fonts').glob('*.ttf'):
    converted=path.with_suffix('.woff2')
    converted.write_bytes(subset_font_bytes(path.read_bytes(),points))
    css=css.replace(path.name,converted.name)
font_css.write_text(css.replace("format('truetype')","format('woff2')"))
chromium=os.environ.get('BIOREPORT_CHROMIUM')
if not chromium:
    installed=list((Path.home()/'.cache/ms-playwright').glob('chromium-*/chrome-linux64/chrome'))
    chromium=str(max(installed,key=lambda path:path.stat().st_mtime)) if installed else 'auto'
subprocess.run(['node',str(root/'scripts/precompile_mermaid.mjs'),str(root/'build/tools/mermaid-cli'),str(jobfile),chromium,str(font_css)],check=True)
manifest={'compiler':'@mermaid-js/mermaid-cli@12.0.0','locations':locations,'diagrams':{}}
for key,job in jobs.items():
    path=Path(job['output']);data=path.read_bytes()
    if re.search(rb'(?:href|src)=[\'"](?:https?|file):',data):raise ValueError('External SVG resource: '+str(path))
    manifest['diagrams'][key]={'file':path.name,'svg_sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
(assets/'mermaid-precompiled.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
print(f'Mermaid source blocks: {len(locations)}; unique static SVGs: {len(jobs)}')
