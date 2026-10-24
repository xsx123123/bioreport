"""Lossless, offline payloads that stay small before Quarto reads the notebook."""
import base64
import gzip
import json
import math
import struct
import hashlib
import os
from pathlib import Path
import re


MIN_COMPRESS_BYTES = 65536
linked_tables = {}
PACKED_SCRIPT = re.compile(r'(<script\b[^>]*\bdata-encoding="(?:columnar-)?gzip-base64"[^>]*>)([A-Za-z0-9+/=\s]+)(</script\s*>)', re.I)


def payload_reference(data, directory):
    identity = 'report-payload-' + hashlib.sha256(data.encode('ascii')).hexdigest()
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (identity + '.b64')
    if not path.exists():
        path.write_text(data, encoding='ascii')
    return identity


def payload_markup(data, class_name, encoding):
    """CLI builds stage data outside the notebook, then embed it at delivery."""
    directory = os.environ.get('BIOREPORT_HTML_PAYLOAD_DIR')
    reference = ''
    if directory:
        identity = payload_reference(data, directory)
        reference = f' data-payload-ref="{identity}"'
        # Quarto's embed-resources pass serializes an EMPTY <script> without
        # its closing tag, so the next sibling script (chart registration or
        # the table module initializer) becomes inert raw text. A hyphenated
        # placeholder keeps the element non-empty; the hyphen is outside the
        # base64 character class, so staging/merge regexes never rematch it,
        # and consumers with data-payload-ref never read the text content.
        data = 'await-delivery'
    return (f'<script type="application/octet-stream" class="{class_name}" '
            f'data-encoding="{encoding}"{reference}>{data}</script>')


def stage_packed_html(markup, directory):
    """Also supports recovery of an already executed large notebook."""
    def stage(match):
        data = re.sub(r'\s+', '', match[2])
        identity = payload_reference(data, directory)
        return match[1][:-1] + f' data-payload-ref="{identity}">' + match[3]
    return PACKED_SCRIPT.sub(stage, markup)


def embed_payloads(path, directory):
    """Embed staged data into a non-bilingual HTML without a giant JS string."""
    path, directory = Path(path), Path(directory)
    document = path.read_text(encoding='utf-8')
    references = set(re.findall(r'data-payload-ref="(report-payload-[a-f0-9]+)"', document))
    if not references:
        return
    # Case-insensitive search, but index into the ORIGINAL text: str.lower()
    # expands İ (U+0130) to two code points, which would shift every later
    # index and split the closing </body> tag.
    match = None
    for match in re.finditer(r'</body\s*>', document, re.I):
        pass
    index = match.start() if match else len(document)
    temporary = path.with_name(path.name + '.payloads.tmp')
    with temporary.open('w', encoding='utf-8') as output:
        output.write(document[:index])
        for identity in sorted(references):
            output.write(f'<script id="{identity}" type="application/octet-stream" class="report-shared-payload">')
            with (directory / (identity + '.b64')).open(encoding='ascii') as source:
                while chunk := source.read(1024 * 1024):
                    output.write(chunk)
            output.write('</script>\n')
        output.write(document[index:])
    temporary.replace(path)


def packed_text(text):
    return base64.b64encode(gzip.compress(text.encode('utf-8'), compresslevel=6, mtime=0)).decode('ascii')


def unpacked_text(text):
    return gzip.decompress(base64.b64decode(text)).decode('utf-8')


def columnar_table(payload):
    """Keep IEEE float values exactly; store duplicate columns only once."""
    columns = list(map(list, zip(*payload['data']))) if payload['data'] else [[] for _ in payload['columns']]
    encoded, seen = [], {}
    for index, values in enumerate(columns):
        identity = json.dumps(values, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        previous = seen.get(identity)
        if previous is not None:
            encoded.append({'kind': 'alias', 'column': previous})
            continue
        seen[identity] = index
        if index in payload['numeric'] and any(isinstance(value, float) for value in values):
            extras = [[i, value] for i, value in enumerate(values)
                      if value is None or isinstance(value, str)]
            numbers = [0. if value is None or isinstance(value, str) else value for value in values]
            if all(math.isfinite(value) for value in numbers):
                data = struct.pack('<' + 'd' * len(numbers), *numbers)
                encoded.append({'kind': 'f64', 'values': base64.b64encode(data).decode('ascii'), 'extras': extras})
                continue
        encoded.append({'kind': 'json', 'values': values})
    return {'columns': payload['columns'], 'numeric': payload['numeric'],
            'rowCount': len(payload['data']), 'columnData': encoded}


def restored_table(payload):
    """Python counterpart of the browser decoder, for lossless checks/recovery."""
    columns = []
    for column in payload['columnData']:
        if column['kind'] == 'alias':
            values = columns[column['column']]
        elif column['kind'] == 'f64':
            data = base64.b64decode(column['values'])
            values = list(struct.unpack('<' + 'd' * (len(data) // 8), data))
            for index, value in column['extras']:
                values[index] = value
        else:
            values = column['values']
        columns.append(values)
    return {'columns': payload['columns'], 'numeric': payload['numeric'],
            'data': [[column[index] for column in columns] for index in range(payload['rowCount'])]}
