"""Keep expensive render inputs available when document compilation fails."""
import json
from pathlib import Path
import shlex
import shutil

from .fonts import typst_font_paths


def preserve_failed_render(template_dir, output_dir, reason):
    """Move the staged project out of TemporaryDirectory before its cleanup."""
    template_dir = Path(template_dir)
    destination = Path(output_dir).resolve() / 'failed-render' / template_dir.parent.name
    destination.mkdir(parents=True, exist_ok=False)
    project = destination / 'templates'
    shutil.move(str(template_dir), str(project))
    details = {'error': str(reason), 'project': 'templates'}
    source = project / 'qmd' / 'report_pdf.typ'
    if source.is_file():
        # Relative asset paths remain valid inside the moved project. This
        # compiles the already executed document without repeating Python/AI.
        command = ['quarto', 'typst', 'compile', '--root', '.',
                   '--font-path', typst_font_paths(),
                   'qmd/report_pdf.typ', 'recovered.pdf']
        details['compile_command'] = command
        details['compile_output'] = 'templates/recovered.pdf'
        details['note'] = 'Typesetting recovery only; delivery validation and PDF protection are not applied.'
        script = project / 'compile-pdf.sh'
        script.write_text('#!/bin/sh\nset -eu\ncd -- "$(dirname -- "$0")"\n'
                          + shlex.join(command) + '\n', encoding='utf-8')
    (destination / 'recovery.json').write_text(
        json.dumps(details, ensure_ascii=False, indent=2), encoding='utf-8')
    return destination
