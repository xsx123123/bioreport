"""Full Quarto checks for hosts that permit Jupyter kernels and image export."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from bs4 import BeautifulSoup


REPO_ROOT = Path(__file__).resolve().parents[1]
RNA_ROOT = REPO_ROOT
RUN_INTEGRATION = os.environ.get("RUN_REPORT_INTEGRATION") == "1"


def render_and_check(config_path: Path, output_dir: Path) -> str:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO_ROOT), env.get("PYTHONPATH")]))
    subprocess.run(
        [sys.executable, "-m", "bioreport", "-c", str(config_path), "-o", str(output_dir)],
        check=True, env=env, timeout=900,
    )

    html_path = output_dir / "report.html"
    pdf_path = output_dir / "report.pdf"
    assert html_path.is_file() and pdf_path.is_file()
    assert pdf_path.read_bytes().startswith(b"%PDF-")
    html = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    for tag, attribute in (("script", "src"), ("link", "href"), ("img", "src")):
        for node in soup.find_all(tag):
            value = node.get(attribute, "")
            assert not value or value.startswith(("data:", "#")), (tag, value)
    assert not (output_dir / "report_files").exists()
    return html


@pytest.mark.skipif(not RUN_INTEGRATION, reason="Set RUN_REPORT_INTEGRATION=1 on a Quarto host")
def test_generic_json_renders_one_html_and_pdf(tmp_path):
    if shutil.which("quarto") is None:
        pytest.skip("Quarto is not installed")
    example = RNA_ROOT / "configs" / "report.generic.json"
    config = json.loads(example.read_text(encoding="utf-8"))
    config["input_files"]["data_dir"] = str(REPO_ROOT / "examples" / "generic-assay")
    for definition in config["report"]["module_definitions"].values():
        definition["path"] = str(REPO_ROOT / "examples" / "generic-assay" / "measurements.qmd")
    config_path = tmp_path / "generic.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    html = render_and_check(config_path, tmp_path / "generic-output")

    assert "Baseline measurements" in html
    assert "Follow-up measurements" in html


@pytest.mark.skipif(not RUN_INTEGRATION, reason="Set RUN_REPORT_INTEGRATION=1 on a Quarto host")
def test_rna_json_renders_one_html_and_pdf(tmp_path):
    if shutil.which("quarto") is None:
        pytest.skip("Quarto is not installed")
    example = RNA_ROOT / "configs" / "report.example.json"
    config = json.loads(example.read_text(encoding="utf-8"))
    config["input_files"]["data_dir"] = str(REPO_ROOT / "examples" / "rna-seq" / "data")
    config_path = tmp_path / "rna.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    html = render_and_check(config_path, tmp_path / "rna-output")

    assert "RNA-seq" in html
    soup = BeautifulSoup(html, "html.parser")
    assert [node.get_text(strip=True) for node in soup.select('.report-navbar a')] == [
        "项目概述", "样本信息", "分析概述", "质量控制", "分析结果", "关于",
    ]
    pages = soup.select('.report-page')
    assert len(pages) == 6
    assert pages[2].select_one('.mermaid') is not None
    assert soup.select_one('#refs').find_parent(class_='report-page') == pages[2]
    assert len(soup.select('.report-brand img')) == 2
    assert pages[3].select_one('.plotly-graph-div') is not None
    assert pages[4].select_one('.plotly-graph-div') is not None
    assert "差异表达分析" in pages[4].get_text()
    assert not pages[0].select('.plotly-graph-div')
    assert "report-routing-ready" in html
    assert "history.pushState" in html
    assert not soup.select('.header-section-number')
