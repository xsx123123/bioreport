"""报告溯源信息（Provenance）的单元测试与集成测试。"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

import bioreport
from bioreport.config import load_config, report_artifact_name
from bioreport.modules import selected_modules
from bioreport.utils.provenance import build_provenance, input_checksums, write_provenance
from bioreport.utils.report_utils import load_provenance

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_INTEGRATION = os.environ.get("RUN_REPORT_INTEGRATION") == "1"


def _minimal_config(tmp_path: Path, **overrides) -> dict:
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    sample = data_dir / "sample.csv"
    sample.write_text("sample,group\nS1,A\nS2,B\n", encoding="utf-8")
    config = {
        "report": {"layout": "single", "output_format": ["html", "pdf"]},
        "project": {"project_id": "PRJ-TEST-001", "pipeline_version": "RNAFlow test"},
        "input_files": {
            "data_dir": str(data_dir),
            "sample_file": "sample.csv",
            "missing_file": "not_there.txt",
        },
    }
    config.update(overrides)
    return config


def test_build_provenance_fields_complete(tmp_path):
    config = _minimal_config(tmp_path)
    sections = ["index", "rna.workflow", "rna.qc", "rna.results", "about"]

    provenance = build_provenance(config, sections)

    assert provenance["project_id"] == "PRJ-TEST-001"
    assert provenance["bioreport_version"] == bioreport.__version__
    assert provenance["rendered_modules"] == sections
    assert provenance["layout"] == "single"
    assert provenance["output_format"] == ["html", "pdf"]
    assert provenance["pipeline_version"] == "RNAFlow test"
    # 生成时间必须是带时区偏移的合法 ISO8601
    generated_at = provenance["generated_at"]
    parsed = datetime.fromisoformat(generated_at)
    assert parsed.tzinfo is not None
    assert "T" in generated_at


def test_build_provenance_omits_pipeline_version_and_normalizes_format(tmp_path):
    config = _minimal_config(tmp_path, project={"project_id": "PRJ-TEST-001"})
    config["report"]["output_format"] = "html"

    provenance = build_provenance(config, ["about"])

    assert "pipeline_version" not in provenance
    assert provenance["output_format"] == ["html"]
    assert provenance["layout"] == "single"  # 缺省值


def test_input_checksums_match_sha256_and_skip_missing(tmp_path):
    config = _minimal_config(tmp_path)
    sample_path = Path(config["input_files"]["data_dir"]) / "sample.csv"

    checksums = input_checksums(config)

    assert checksums["sample_file"] == hashlib.sha256(sample_path.read_bytes()).hexdigest()
    assert "missing_file" not in checksums
    assert "data_dir" not in checksums


def test_input_checksums_change_when_file_changes(tmp_path):
    config = _minimal_config(tmp_path)
    before = input_checksums(config)["sample_file"]

    sample_path = Path(config["input_files"]["data_dir"]) / "sample.csv"
    with sample_path.open("a", encoding="utf-8") as handle:
        handle.write("S3,C\n")

    after = input_checksums(config)["sample_file"]
    assert before != after


def test_write_and_load_provenance_roundtrip(tmp_path, monkeypatch):
    config = _minimal_config(tmp_path)
    provenance = build_provenance(config, ["about"])
    qmd_dir = tmp_path / "qmd"
    target = write_provenance(provenance, qmd_dir)

    assert target.is_file()
    on_disk = json.loads(target.read_text(encoding="utf-8"))
    assert on_disk == provenance

    # load_provenance 在 cwd == 项目根（qmd/provenance.json）时可读到
    monkeypatch.chdir(tmp_path)
    assert load_provenance() == provenance


def test_load_provenance_returns_empty_when_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert load_provenance() == {}


def test_load_config_requires_project_id(tmp_path):
    """project.project_id 是必填项：缺失或为空字符串都必须报错。"""
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "report": {"modules": ["about"]},
        "input_files": {"data_dir": "data"},
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="project_id"):
        load_config(config_path)

    config_path.write_text(json.dumps({
        "report": {"modules": ["about"]},
        "project": {"project_id": "  "},
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="project_id"):
        load_config(config_path)


def test_run_db_records_and_fetches_runs(tmp_path):
    """离线数据库：写入并读取运行记录，指纹等完整信息可还原。"""
    from bioreport.utils.run_db import fetch_runs, record_run

    db = tmp_path / "db" / "runs.db"
    config = _minimal_config(tmp_path)
    provenance = build_provenance(config, ["about"])

    row_id = record_run(
        db,
        project_id="PRJ-TEST-001",
        provenance=provenance,
        config_path="/tmp/config.json",
        output_dir="/tmp/output",
        status="success",
    )
    assert row_id == 1

    runs = fetch_runs(db)
    assert len(runs) == 1
    run = runs[0]
    assert run["project_id"] == "PRJ-TEST-001"
    assert run["status"] == "success"
    assert run["engine_version"] == bioreport.__version__
    assert json.loads(run["input_checksums"]) == provenance["input_checksums"]
    assert json.loads(run["modules"]) == ["about"]
    assert run["pipeline_version"] == "RNAFlow test"

    # 按项目过滤 + 缺失库文件返回空列表
    assert len(fetch_runs(db, project_id="PRJ-TEST-001")) == 1
    assert fetch_runs(db, project_id="OTHER") == []
    assert fetch_runs(tmp_path / "missing.db") == []


def test_run_db_search_filters_and_includes_date_boundaries(tmp_path):
    from bioreport.utils.run_db import record_run, search_runs

    db = tmp_path / "runs.db"
    provenance = {"generated_at": "2026-10-17T10:00:00+08:00", "output_format": ["html"],
                  "rendered_modules": [], "input_checksums": {}, "layout": "single"}
    record_run(db, project_id="RNA-A", provenance=provenance, config_path="a",
               output_dir="a", status="success")
    provenance["generated_at"] = "2026-10-18T10:00:00+08:00"
    record_run(db, project_id="RNA-B", provenance=provenance, config_path="b",
               output_dir="b", status="failed")

    rows = search_runs(db, project="RNA-A", status="success", since="2026-10-17", until="2026-10-17")
    assert [row["project_id"] for row in rows] == ["RNA-A"]
    assert search_runs(db, status="failed", limit=1)[0]["project_id"] == "RNA-B"


def test_compose_report_footer_cover_and_provenance_page(tmp_path):
    """组装阶段：页脚含引擎版本、封面自动注入、溯源为独立导航页面且 PDF 用简洁表格。"""
    from bioreport.modules import compose_report

    root = REPO_ROOT
    staged = tmp_path / "templates"
    shutil.copytree(root / "templates", staged)
    shutil.copytree(staged / "shared", staged / "qmd")
    shutil.copytree(root / "omics/rna/qmd", staged / "qmd", dirs_exist_ok=True)

    config = load_config(root / "tests/report.rna.local.json")
    provenance = build_provenance(config, selected_modules(config))
    write_provenance(provenance, staged / "qmd")

    report_qmd = compose_report(config, staged)
    html_doc = Path(report_qmd).read_text(encoding="utf-8")
    assert '<footer class="report-footer">' in html_doc
    from bs4 import BeautifulSoup
    footer = BeautifulSoup(html_doc, 'html.parser').select_one('footer.report-footer')
    assert [image['alt'] for image in footer.select('img')] == ['BioReport', 'Quarto']
    assert [image['src'] for image in footer.select('img')] == ['../logo/bioreport.png', '../logo/quarto.png']
    assert footer.select_one('.report-footer-version').text == f'v{bioreport.__version__}'
    assert footer.select_one('time')['datetime'] == provenance['generated_at']
    assert provenance["generated_at"] in html_doc

    # 溯源是独立页面：导航栏位于「分析结果」之后、「关于」之前
    nav_titles = re.findall(
        r'<a href="#report-page-\d+"[^>]*class="nav-link"[^>]*>([^<]+)</a>', html_doc
    )
    assert "溯源信息" in nav_titles
    assert nav_titles.index("溯源信息") == nav_titles.index("分析结果") + 1
    assert nav_titles.index("溯源信息") == nav_titles.index("关于") - 1
    # 页面正文包含卡片结构，且关于页不再重复溯源表格
    page = html_doc.split("溯源信息\n", 1)[1]
    assert "prov-card" in page
    assert "自动采集 · 不可修改" in page
    about_section = html_doc.split("# 关于 BioReport\n", 1)[1]
    assert "prov-card" not in about_section
    assert "报告溯源信息" not in about_section

    # PDF 分支：重映射到 pdf/provenance.qmd（简洁表格，无 HTML 卡片）
    pdf_qmd = compose_report(config, staged, pdf=True)
    pdf_doc = Path(pdf_qmd).read_text(encoding="utf-8")
    assert "prov-card" not in pdf_doc
    assert "load_provenance(" in pdf_doc
    assert "show_print_table" in pdf_doc

    cover = (staged / "pdf" / "rna-cover.typ").read_text(encoding="utf-8")
    assert "报告引擎" in cover and f"BioReport v{bioreport.__version__}" in cover


@pytest.mark.skipif(not RUN_INTEGRATION, reason="需要 Quarto + Jupyter 完整环境")
def test_integration_provenance_json_written(tmp_path):
    """端到端：完整生成后输出目录的报告中体现溯源信息。"""
    config_path = REPO_ROOT / "tests/report.rna.html.json"
    output_dir = tmp_path / "output"
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO_ROOT), env.get("PYTHONPATH")]))
    subprocess.run(
        [sys.executable, "-m", "bioreport", "-c", str(config_path), "-o", str(output_dir)],
        check=True, env=env, timeout=900,
    )

    html = (output_dir / report_artifact_name(
        load_config(config_path), "html")).read_text(encoding="utf-8")
    assert f"BioReport v{bioreport.__version__}" in html
    assert "报告溯源信息" in html
    assert "prov-card" in html
    assert "自动采集 · 不可修改" in html
    assert "SHA256" in html
    assert 'class="report-footer-bioreport"' in html and 'class="report-footer-quarto"' in html
