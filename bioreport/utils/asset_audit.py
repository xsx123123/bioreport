"""Build-only asset diagnostics; never emit implementation details into reports."""
import ast
import json
import os
from pathlib import Path


def static_plotly_calls(directory):
    calls=set()
    for path in Path(directory).glob('*.py'):
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name):
                alias,name=node.func.value.id,node.func.attr
                if alias in {'go','px'} and name!='Figure':calls.add(alias+'.'+name)
    return sorted(calls)


def record_asset(event):
    target=os.environ.get('BIOREPORT_ASSET_AUDIT_FILE')
    if target:
        with Path(target).open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(event,ensure_ascii=True,allow_nan=False)+'\n')
