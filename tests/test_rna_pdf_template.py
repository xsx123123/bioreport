"""Verify dedicated print composition and its data/plotting cells."""

from pathlib import Path
import re
import shutil

from bioreport.config import load_config
from bioreport.modules import compose_report


ROOT = Path(__file__).resolve().parents[1]


def stage(tmp_path):
    shutil.copytree(ROOT / "templates", tmp_path / "templates")
    shutil.copytree(ROOT / "omics/rna/qmd", tmp_path / "templates/qmd")
    return tmp_path / "templates"


def test_pdf_has_own_content_and_print_layout(tmp_path):
    staged = stage(tmp_path)
    config = load_config(ROOT / "tests/report.rna.local.json")
    pdf = compose_report(config, staged, pdf=True).read_text()
    html = compose_report(config, staged).read_text()
    assert "rna-style.typ" in pdf and "rna-cover.typ" in pdf
    assert "papersize: a4" in pdf
    assert "# 样本信息" in pdf
    assert "## 样本信息" in pdf
    assert "panel-tabset" not in pdf and "callout-" not in pdf
    assert "<div" not in pdf and "<span" not in pdf
    assert "静态图表与结果摘要" in pdf
    assert "about-manifesto" in html
    assert "panel-tabset" in html
    assert "```{mermaid}" in html and "```{mermaid}" not in pdf
    cover = (staged / "pdf/rna-cover.typ").read_text()
    assert config["project"]["client"] in cover
    assert config["report"]["title"] in cover


def test_pdf_cells_read_rna_example_and_produce_tables_and_figures(tmp_path, monkeypatch):
    from bioreport.utils import render_output
    from omics.rna.analysis import qc_vis

    monkeypatch.setenv("REPORT_CONFIG", str(ROOT / "tests/report.rna.local.json"))
    monkeypatch.setenv("BIOREPORT_OUTPUT_FORMAT", "pdf")
    tables, figures = [], []
    monkeypatch.setattr(render_output, "display", tables.append)
    monkeypatch.setattr(render_output, "show_figure", lambda figure, config=None, caption=None: figures.append(figure))
    monkeypatch.setattr(qc_vis, "show_figure", lambda figure, config=None, caption=None: figures.append(figure))
    pdf = compose_report(load_config(ROOT / "tests/report.rna.local.json"), stage(tmp_path), pdf=True).read_text()
    namespace = {}
    for cell in re.findall(r"```\{python\}\n(.*?)\n```", pdf, re.DOTALL):
        exec(compile(cell, "rna-pdf-cell", "exec"), namespace)
    assert len(figures) >= 6
    assert all(figure is not None for figure in figures)
    assert len(tables) >= 6
    assert namespace["comparisons"]
    assert len(namespace["shown"].columns) > 1
    assert not namespace["mapping"].empty
