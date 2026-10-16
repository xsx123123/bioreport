"""Renderer-produced semantic evidence; no process-global report content cache."""
from dataclasses import fields, is_dataclass
import json
import os
from pathlib import Path


def serialize(value):
    if is_dataclass(value):
        return {'type':value.type, **{f.name:serialize(getattr(value,f.name)) for f in fields(value)}}
    if isinstance(value,(list,tuple)): return [serialize(v) for v in value]
    if isinstance(value,dict): return {str(k):serialize(v) for k,v in value.items()}
    return value


def record_block(block):
    path = os.environ.get('BIOREPORT_BLOCK_MANIFEST')
    if path:
        with Path(path).open('a',encoding='utf-8') as handle:
            handle.write(json.dumps(serialize(block),ensure_ascii=False,default=str)+'\n')
