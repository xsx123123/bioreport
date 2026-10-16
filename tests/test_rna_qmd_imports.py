"""Ensure the RNA setup cell defines its functions before later cells run."""

import re
import builtins
import json
from pathlib import Path

from bioreport.config import load_config
from omics.rna.analysis import qc_vis


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_qc_setup_defines_fastp_table_with_local_example(monkeypatch):
    monkeypatch.setenv("REPORT_CONFIG", str(REPO_ROOT / "tests" / "report.rna.local.json"))
    source = (REPO_ROOT / "omics" / "rna" / "qmd" / "modules" / "qc" / "setup.qmd").read_text(encoding="utf-8")
    cell = re.search(r"```\{python\}\n(.*?)\n```", source, re.DOTALL)
    assert cell is not None

    namespace = {}
    exec(cell.group(1), namespace)

    assert callable(namespace["display_fastp_table"])
    assert Path(namespace["input_files"]["fastp_stats_file"]).is_file()
    assert load_config(REPO_ROOT / "tests" / "report.rna.local.json")["input_files"]["fastp_stats_file"] == namespace["input_files"]["fastp_stats_file"]


def test_qc_visualization_uses_exported_json_when_multiqc_is_missing(tmp_path, monkeypatch):
    data = {
        "report_plot_data": {
            "fastp_reads": {
                "plot_type": "bar plot",
                "pconfig": {"title": "fastp reads"},
                "datasets": [{"samples":["sample"],"cats":[{"name":"reads","data":[10]}]}],
            }
        }
    }
    (tmp_path / "multiqc_data.json").write_text(json.dumps(data), encoding="utf-8")
    figures = []
    monkeypatch.setattr(qc_vis, "show_figure", lambda figure, config=None: figures.append(figure))
    original_import = builtins.__import__

    def import_without_multiqc(name, *args, **kwargs):
        if name == "multiqc":
            raise ImportError("No module named multiqc")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_multiqc)
    qc_vis.visualize_multiqc_logs(str(tmp_path), ["fastp"])

    assert len(figures) == 1
    assert list(figures[0].data[0].x) == ["sample"]
    assert list(figures[0].data[0].y) == [10]
