"""Vendor the pinned pdfmake browser distribution under a private global.

Usage: python scripts/build_pdf_runtime.py /path/to/pdfmake-0.2.7/build/pdfmake.js
Requires terser 5.19.2. No npm install or network access at report runtime.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile


root = Path(__file__).resolve().parents[1] / 'bioreport/assets/js'
manifest_path = root / 'pdfmake-manifest.json'
manifest = json.loads(manifest_path.read_text())
source = Path(sys.argv[1]).read_bytes()
if hashlib.sha256(source).hexdigest() != manifest['source_sha256']:
    raise SystemExit('Source does not match the pinned pdfmake 0.2.7 distribution')
# Keep the converter independent of table exporters and any host-page pdfMake.
code = source.decode().replace('pdfMake', 'BioReportPdfMake')
# Quarto's notebook/table dependencies install RequireJS. Anonymous AMD
# registration would hide our private global and break every PDF download.
code, removed = re.subn(
    r"else if\(typeof define === 'function' && define\.amd\)\s*define\(\[\], factory\);\s*",
    '', code, count=1,
)
assert removed == 1, 'Expected the pinned UMD AMD branch'
old = 'for(var i in a) (typeof exports === \'object\' ? exports : root)[i] = a[i];'
assert old in code
code = code.replace(old, 'root.BioReportPdfMake = a;')
with tempfile.TemporaryDirectory() as directory:
    patched = Path(directory) / 'pdfmake.js'
    patched.write_text(code)
    subprocess.run(['terser', str(patched), '--compress', '--mangle', '--comments',
                    '/^!|@license|@preserve|Copyright/', '--output', str(root / manifest['bundle'])], check=True)
bundle = root / manifest['bundle']
notices = (root / 'pdfmake-LICENSE.txt').read_text().replace('*/', '* /').replace('</script', '<\\/script')
bundle.write_text('/*!\n' + notices + '\n*/\n' + bundle.read_text())
manifest['bundle_sha256'] = hashlib.sha256((root / manifest['bundle']).read_bytes()).hexdigest()
manifest['build_command'] = 'python scripts/build_pdf_runtime.py /path/to/pdfmake-0.2.7/build/pdfmake.js'
manifest['minifier'] = 'terser 5.19.2'
manifest['local_changes'] = 'Rename pdfMake global to BioReportPdfMake; bypass AMD registration and isolate UMD browser export; minify.'
manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
