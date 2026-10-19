"""Verify dedicated print composition and its data/plotting cells."""

from pathlib import Path
import json
import re
import shutil

from bioreport.config import load_config
from bioreport.modules import compose_report


ROOT = Path(__file__).resolve().parents[1]


def stage(tmp_path):
    shutil.copytree(ROOT / "templates", tmp_path / "templates")
    shutil.copytree(ROOT / "templates/shared", tmp_path / "templates/qmd")
    shutil.copytree(ROOT / "omics/rna/qmd", tmp_path / "templates/qmd", dirs_exist_ok=True)
    return tmp_path / "templates"


def test_pdf_has_own_content_and_print_layout(tmp_path):
    staged = stage(tmp_path)
    config = load_config(ROOT / "tests/report.rna.local.json")
    pdf = compose_report(config, staged, pdf=True).read_text()
    html = compose_report(config, staged).read_text()
    assert "rna-style.typ" in pdf
    assert "#heading(level: 1, numbering: none, outlined: false)[摘要]" in pdf
    assert pdf.index("Powered by JZHANG") < pdf.index("#heading(level: 1, numbering: none, outlined: false)[摘要]")
    assert "#heading(level: 2, numbering: none, outlined: false)[' + title + ']" in pdf
    assert "summary_heading('差异表达客观统计汇总')" in pdf
    assert "papersize: a4" in pdf
    assert "# 样本信息" in pdf
    assert "## 样本信息" in pdf
    assert "panel-tabset" not in pdf and "callout-" not in pdf
    assert "<div" not in pdf and "<span" not in pdf
    assert "静态图表与结果摘要" in pdf
    assert "assets/architecture.svg" in pdf
    assert "技术架构" in pdf
    assert "BioReport 愿景" in pdf
    assert "about-manifesto" in html
    assert "panel-tabset" in html
    assert "```{mermaid}" in html and "```{mermaid}" not in pdf
    cover = (staged / "pdf/rna-cover.typ").read_text()
    assert config["project"]["client"] in cover
    assert config["report"]["title"] in cover
    # 元数据卡片承载新的科研交付字段，物种学名走真斜体渲染。
    for label in ("项目编号", "核心比较组", "报告引擎"):
        assert label in cover
    assert f"ProjectID: {config['project']['project_id']}" in cover
    assert "BioReport: v2.0.0" in cover
    assert f"FlowVersion: {config['project']['pipeline_version']}" in cover
    print_style = (staged / "pdf/print-style.typ").read_text()
    assert 'numbering("1-1"' in print_style and 'supplement: [#(if report-language == "en" {"Figure"} else {"图"})#h(' in print_style

    assert "align: (x, y) => if y == 0 { center } else if numeric.at(x) { right } else { left }" in print_style
    assert 'rgb("#315f65")' in print_style and 'fill: rgb("#ffffff")' in print_style
    assert "block(sticky: true)[#figure(" in print_style
    assert "sci(" in cover and "Group 2 vs Group 1" in cover
    assert "2_vs_1" not in cover
    # 双徽标保留在同一眉栏。
    assert 'logo/logo.png' in cover and 'Huazhong_Agricultural_University_logo.svg' in cover
    # 报告日期与数据校验状态来自溯源快照，就绪时才写入封面。
    (staged / "qmd/provenance.json").write_text(json.dumps({
        "generated_at": "2026-10-17T01:18:04+0800",
        "input_checksums": {"tpm_file": "a" * 64},
        "input_manifest": [{"path": "index/merge_rsem_tpm.tsv"}],
    }), encoding="utf-8")
    compose_report(config, staged, pdf=True)
    cover = (staged / "pdf/rna-cover.typ").read_text()
    assert "报告生成日期" in cover and "2026-10-17" in cover
    assert "数据完整性校验状态" in cover and "已记录 SHA-256 指纹" in cover
    assert "Verified" not in cover
    assert "未与外部基准比对" not in cover


def test_pdf_cells_read_rna_example_and_produce_tables_and_figures(tmp_path, monkeypatch):
    from bioreport.utils import render_output
    from omics.rna.analysis import qc_vis

    monkeypatch.setenv("REPORT_CONFIG", str(ROOT / "tests/report.rna.local.json"))
    monkeypatch.setenv("BIOREPORT_OUTPUT_FORMAT", "pdf")
    monkeypatch.setenv("BIOREPORT_DELIVERY_DIR", str(tmp_path))
    tables, figures = [], []
    monkeypatch.setattr(render_output, "display", tables.append)
    monkeypatch.setattr(render_output, "show_figure", lambda figure, config=None, caption=None, **kwargs: figures.append(figure))
    monkeypatch.setattr(qc_vis, "show_figure", lambda figure, config=None, caption=None, **kwargs: figures.append(figure))
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


def test_cover_missing_metadata_does_not_invent_evidence(tmp_path):
    staged = stage(tmp_path)
    config = load_config(ROOT / "tests/report.rna.local.json")
    config["project"] = {"project_id": "DYNAMIC-42", "client": None,
                         "species": "null", "pipeline_version": "undefined"}
    config["report"]["modules"] = ["rna.index"]
    config["input_files"].pop("contrasts_file")
    compose_report(config, staged, pdf=True)
    cover = (staged / "pdf/rna-cover.typ").read_text()
    assert '"None"' not in cover and '"null"' not in cover and '"undefined"' not in cover
    assert "未提供校验结果" in cover and "Verified" not in cover
    assert "DYNAMIC-42" in cover and "未提供" in cover
    assert "STUDY INFORMATION" in cover and "ANALYSIS PROVENANCE" in cover
    config["project"].update(client="委托研究中心" * 20, pipeline_version="RNAFlow v3.2.1")
    compose_report(config, staged, pdf=True)
    cover = (staged / "pdf/rna-cover.typ").read_text()
    assert "委托研究中心" * 20 in cover and "RNAFlow v3.2.1" in cover


def test_print_table_preserves_title_and_escapes_typst(monkeypatch):
    import pandas as pd
    from bioreport.utils import render_output
    blocks, outputs = [], []
    monkeypatch.setattr(render_output, 'record_block', blocks.append)
    monkeypatch.setattr(render_output, 'display', outputs.append)
    title = '样本 "A" 与 Control 的质量统计'
    render_output.show_print_table(pd.DataFrame({'样本': ['A'], '数量': [6]}), caption=title)
    assert blocks[0].caption == title
    assert blocks[0].rows == [['A', '6']]
    assert 'caption: ' + json.dumps(title, ensure_ascii=False) in outputs[0].data
