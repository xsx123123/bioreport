"""Report errors after code execution without blaming the last successful cell."""

from io import StringIO

import pytest

from bioreport.cli import render_report


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
    assert "代码执行后的图表转换或文档渲染阶段" in message
    assert "Cell 20/20" not in message
    assert str(log_file) in message
