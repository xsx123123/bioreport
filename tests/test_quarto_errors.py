"""Report errors after code execution without blaming the last successful cell."""

from io import StringIO
from pathlib import Path
import sys

import pytest

from bioreport.cli import _short_quarto_output_path, render_report


def test_quarto_output_path_is_shortened_for_terminal():
    assert _short_quarto_output_path(
        "Output created: ../../../../home/zj/project/output/qmd/report.html"
    ) == "[Quarto] Render output: qmd/report.html (before delivery processing)"


@pytest.mark.parametrize('override', [None, '/custom/python'])
def test_render_uses_cli_python_unless_explicitly_overridden(monkeypatch, tmp_path, override):
    if override is None:
        monkeypatch.delenv('QUARTO_PYTHON', raising=False)
    else:
        monkeypatch.setenv('QUARTO_PYTHON', override)
    captured = {}

    class Process:
        stdout = StringIO('ERROR: stop after checking environment\n')

        def wait(self):
            return 1

    def start(*args, **kwargs):
        captured.update(kwargs['env'])
        return Process()

    monkeypatch.setattr('bioreport.cli.subprocess.Popen', start)
    with pytest.raises(RuntimeError):
        render_report({'report': {'layout': 'single', 'output_format': 'html'}},
                      'config.json', str(tmp_path), tmp_path)
    assert captured['QUARTO_PYTHON'] == (override or sys.executable)


def test_mermaid_failure_includes_quarto_error_and_rendering_phase(monkeypatch, tmp_path):
    class Process:
        stdout = StringIO(
            "Cell 20/20: 'enrichment'...Done\n"
            "ERROR: Internal Error: Couldn't find an svg element in svg string\n"
        )

        def wait(self):
            return 1

    monkeypatch.setattr("bioreport.cli.subprocess.Popen", lambda *args, **kwargs: Process())

    log_file = tmp_path / "PRJ-TEST-001_20261016-143000_bioreport.log"
    with pytest.raises(RuntimeError) as error:
        render_report(
            {"report": {"layout": "single", "output_format": "pdf"}},
            "config.json", str(tmp_path), tmp_path, str(log_file),
        )

    message = str(error.value)
    assert "Couldn't find an svg element" in message
    assert "post-execution figure conversion or document rendering" in message
    assert "Cell 20/20" not in message
    assert str(log_file) in message


def test_rna_html_render_delivers_one_combined_file(monkeypatch, tmp_path):
    from base64 import b64decode
    import gzip
    from loguru import logger

    messages = []
    sink = logger.add(lambda message: messages.append(message.record['message']))

    monkeypatch.setattr('bioreport.cli.render_templates', lambda *args: None)

    class Process:
        def __init__(self):
            self.stdout = StringIO('')

        def wait(self):
            return 0

    def start(command, cwd, env, **kwargs):
        output = Path(command[4]) / 'qmd' / 'report.html'
        output.parent.mkdir(parents=True, exist_ok=True)
        language = env['BIOREPORT_LANGUAGE']
        text = 'Chinese edition' if language == 'zh' else 'English edition'
        output.write_text(f'<html lang="{language}"><body>{text}</body></html>', encoding='utf-8')
        return Process()

    monkeypatch.setattr('bioreport.cli.subprocess.Popen', start)
    config = {
        'report': {'type': 'rna-seq', 'layout': 'single', 'output_format': 'html'},
        'project': {'project_id': 'P1'},
    }
    try:
        render_report(config, 'config.json', str(tmp_path / 'output'), tmp_path / 'templates')
    finally:
        logger.remove(sink)
    assert 'Moved and renamed: qmd/report.html -> P1_report.html (staged for bilingual HTML merge)' in messages
    assert 'Moved and renamed: qmd/report.html -> P1_report.en.html (staged for bilingual HTML merge)' in messages
    assert 'Merged Chinese and English HTML into: P1_report.html (single file; language editions removed)' in messages
    combined = tmp_path / 'output' / 'P1_report.html'
    assert combined.is_file()
    assert not (tmp_path / 'output' / 'P1_report.en.html').exists()
    content = combined.read_text(encoding='utf-8')
    for edition, expected in (('zh', 'Chinese edition'), ('en', 'English edition')):
        payload = content.split(f'id="edition-{edition}" type="application/octet-stream">\n', 1)[1].split('</script>', 1)[0]
        assert expected in gzip.decompress(b64decode(payload)).decode('utf-8')
