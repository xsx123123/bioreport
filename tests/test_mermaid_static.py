import hashlib
import json
from bioreport.utils.mermaid_static import diagram_digest, inline_static_mermaid


def test_cached_svg_keeps_labels_text_and_unique_reference_ids(tmp_path):
    source='%%| label: fig-workflow\n%%| fig-cap: "Workflow"\ngraph LR\nA-->B'
    svg='<svg id="graph" viewBox="0 0 100 100"><defs><marker id="arrow"/></defs><path marker-end="url(#arrow)"/><text>Readable scientific evidence</text></svg>'
    (tmp_path/'graph.svg').write_text(svg)
    (tmp_path/'mermaid-precompiled.json').write_text(json.dumps({'diagrams':{diagram_digest(source):{'file':'graph.svg','svg_sha256':hashlib.sha256(svg.encode()).hexdigest()}}}))
    output,stats=inline_static_mermaid('```{mermaid}\n'+source+'\n```',tmp_path,'workflow')
    assert stats=={'total':1,'static':1,'runtime':0}
    assert '{mermaid}' not in output and '#fig-workflow' in output
    assert 'Readable scientific evidence' in output and '<text>' in output
    assert 'marker-end="url(#br-' in output and 'tabindex="0"' in output
    other,_=inline_static_mermaid('```{mermaid}\n'+source+'\n```',tmp_path,'other-module')
    assert output!=other


def test_uncompiled_or_modified_svg_retains_original_runtime(tmp_path):
    body='```{mermaid}\ngraph LR\nA-->B\n```'
    output,counts=inline_static_mermaid(body,tmp_path)
    assert output==body and counts['runtime']==1
    (tmp_path/'graph.svg').write_text('<svg/>')
    (tmp_path/'mermaid-precompiled.json').write_text(json.dumps({'diagrams':{diagram_digest('graph LR\nA-->B'):{'file':'graph.svg','svg_sha256':'changed'}}}))
    output,counts=inline_static_mermaid(body,tmp_path)
    assert output==body and counts['runtime']==1
