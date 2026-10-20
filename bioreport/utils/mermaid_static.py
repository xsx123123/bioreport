"""Inline verified static Mermaid SVGs; retain Quarto runtime for unknown graphs."""
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re

from loguru import logger
import yaml

BLOCK = re.compile(r'```\{mermaid\}\s*\n(.*?)\n```', re.S)


def diagram_source(raw):
    return '\n'.join(line.rstrip() for line in raw.replace('\r\n','\n').splitlines()
                     if not line.lstrip().startswith('%%|')).strip()+'\n'


def diagram_digest(raw):
    return sha256(diagram_source(raw).encode('utf-8')).hexdigest()


def _inline_svg(svg, namespace, caption):
    svg=re.sub(r'<\?xml.*?\?>','',svg,flags=re.S).strip()
    identifiers=re.findall(r'(?<![\w:-])id="([^"]+)"',svg)
    mapping={identity:namespace+'-'+identity for identity in identifiers}
    svg=re.sub(r'(?<![\w:-])id="([^"]+)"',lambda m:'id="'+mapping[m[1]]+'"',svg)
    svg=re.sub(r'aria-(labelledby|describedby)="([^"]+)"',lambda m:'aria-'+m[1]+'="'+' '.join(mapping.get(part,part) for part in m[2].split())+'"',svg)
    for before in sorted(mapping,key=len,reverse=True):
        svg=re.sub('#'+re.escape(before)+r'(?![\w.-])','#'+mapping[before],svg)
    def root(match):
        attrs=match[1]
        found=re.search(r'\bclass="([^"]*)"',attrs)
        if found:attrs=attrs[:found.start()]+f'class="{found[1]} report-mermaid-svg"'+attrs[found.end():]
        else:attrs+=' class="report-mermaid-svg"'
        found=re.search(r'\bstyle="([^"]*)"',attrs)
        style='width:100%;max-width:100%;height:auto;'
        if found:attrs=attrs[:found.start()]+f'style="{found[1]};{style}"'+attrs[found.end():]
        else:attrs+=f' style="{style}"'
        if 'aria-label' not in attrs:attrs+=' aria-label="'+escape(caption,quote=True)+'"'
        return '<svg'+attrs+'>'
    return re.sub(r'<svg\b([^>]*)>',root,svg,count=1)


def inline_static_mermaid(body, assets, namespace='report', language='en'):
    assets=Path(assets)
    manifest=assets/'mermaid-precompiled.json'
    entries=json.loads(manifest.read_text())['diagrams'] if manifest.is_file() else {}
    counts={'total':0,'static':0,'runtime':0}
    def replace(match):
        counts['total']+=1
        raw=match[1];digest=diagram_digest(raw);entry=entries.get(digest)
        if not entry or re.search(r'^\s*click\s',raw,re.M):
            counts['runtime']+=1
            return match.group()
        filename=entry['file']
        if Path(filename).name!=filename:
            raise ValueError('Mermaid cache filename must stay inside shared assets')
        path=assets/filename
        if not path.is_file():
            counts['runtime']+=1
            return match.group()
        svg=path.read_text(encoding='utf-8')
        if sha256(svg.encode()).hexdigest()!=entry['svg_sha256']:
            logger.warning('Mermaid SVG checksum changed; keeping runtime rendering for {}',filename)
            counts['runtime']+=1
            return match.group()
        options={}
        for line in raw.splitlines():
            if line.lstrip().startswith('%%|'):
                value=yaml.safe_load(line.lstrip()[3:])
                if isinstance(value,dict):options.update(value)
        caption=str(options.get('fig-cap') or ('Technical architecture' if language=='en' else '技术架构'))
        scope='br-'+sha256(f'{namespace}:{counts["total"]}'.encode()).hexdigest()[:12]
        svg=_inline_svg(svg,scope,caption)
        markup='```{=html}\n<div class="report-mermaid-container" tabindex="0" role="region" aria-label="'+escape(caption,quote=True)+'">\n'+svg+'\n</div>\n```'
        label=options.get('label')
        if label:
            markup='::: {#'+str(label)+'}\n\n'+markup+'\n\n'+str(options.get('fig-cap',''))+'\n\n:::'
        counts['static']+=1
        return markup
    result=BLOCK.sub(replace,body)
    if counts['total']:
        logger.info('Mermaid diagrams {}: {}; pre-rendered SVG: {}; retained runtime: {}',namespace,counts['total'],counts['static'],counts['runtime'])
    return result,counts
