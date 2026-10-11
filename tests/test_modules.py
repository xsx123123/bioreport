import ast
import json
import re
import shutil
from pathlib import Path

import pytest

from bioreport.cli import check_input_files, load_config_with_fallback, output_formats
from bioreport.config import load_config, load_project_metadata
from bioreport.modules import compose_report, selected_modules
from bioreport.renderer import render_templates
from bioreport.utils.report_utils import get_comparisons_from_csv, get_file_path
from bioreport.utils.setup_report import update_json_config, update_yaml_config


def test_single_report_uses_shared_styles_by_default(tmp_path):
    root = Path(__file__).resolve().parents[1]
    shutil.copyfile(root / 'templates/_quarto-single.yml.j2', tmp_path / '_quarto-single.yml.j2')
    (tmp_path / 'qmd').mkdir()
    shutil.copyfile(root / 'omics/rna/qmd/about.qmd', tmp_path / 'qmd/about.qmd')

    render_templates({'report': {'layout': 'single', 'modules': ['about']}}, str(tmp_path / 'output'), str(tmp_path))

    settings = (tmp_path / '_quarto.yml').read_text(encoding='utf-8')
    assert 'theme/New_Brutalism.scss' in settings
    assert 'theme/styles.css' in settings
    assert 'theme/itables_saas.css' in settings
    assert 'toc-location: left' in settings
    assert 'theme/report-pages.html' in settings
    assert 'theme/load-mermaid.html' in settings
    assert 'dark:' not in settings
    assert '- theme/New_Brutalism.scss' in settings


def test_website_report_stages_six_independent_pages_with_shared_styles(tmp_path):
    import yaml

    root = Path(__file__).resolve().parents[1]
    shutil.copytree(root / "templates", tmp_path / "templates")
    staged = tmp_path / "templates"
    shutil.copytree(root / "omics/rna/qmd", staged / "qmd")
    config = load_config(root / "tests/report.rna.local.json")
    render_templates(config, str(tmp_path / "output"), str(staged))

    settings = yaml.safe_load((staged / "_quarto.yml").read_text())
    paths = settings["project"]["render"]
    assert len(paths) == 6
    assert settings["format"]["html"]["theme"] == ["theme/New_Brutalism.scss"]
    assert settings["format"]["html"]["css"] == ["theme/styles.css", "theme/itables_saas.css"]
    assert settings["website"]["navbar"]["pinned"] is True
    assert [page["href"] for page in settings["website"]["navbar"]["left"]] == paths
    documents = [(staged / path).read_text() for path in paths]
    assert all("report-page" not in doc for doc in documents)
    assert "get_project_summary_stats(" in documents[1]
    assert "Sample_Info_table_modern(df_final)" in documents[1]
    assert "Sample_Info_table_modern(df_final)" not in documents[0]
    assert [i for i, doc in enumerate(documents) if "bibliography:" in doc] == [2]
    assert "::: {#refs}" in documents[2]
    assert "```{mermaid}" in documents[2]
    assert "body-classes: about-project" in documents[5]
    assert "::: {.about-project}" not in documents[5]


def test_rna_report_has_six_pages_with_samples_outside_overview(tmp_path):
    root = Path(__file__).resolve().parents[1]
    shutil.copytree(root / "omics/rna/qmd", tmp_path / "qmd")
    shutil.copytree(root / "templates/reference", tmp_path / "reference")
    config = load_config(root / "tests/report.rna.local.json")

    document = compose_report(config, tmp_path).read_text(encoding="utf-8")

    titles = re.findall(r'<a href="#report-page-\d+"[^>]*>([^<]+)</a>', document)
    assert titles == ["项目概述", "样本信息", "分析概述", "质量控制", "分析结果", "关于"]
    overview = document.split("# 项目概述\n", 1)[1].split("# 样本信息\n", 1)[0]
    samples = document.split("# 样本信息\n", 1)[1].split("# 分析概述\n", 1)[0]
    assert "get_project_summary_stats(" in overview
    assert "Sample_Info_table_modern(df_final)" not in overview
    assert "Sample_Info_table_modern(df_final)" in samples
    assert "number-sections: false" in document
    assert "{{< include" not in document
    assert "## 总数据量" not in document
    assert len(re.findall(r"::: \{\.report-page(?: \.about-project)? #report-page-", document)) == 6
    workflow = document.split("# 分析概述\n", 1)[1].split("# 质量控制\n", 1)[0]
    assert "::: {#refs}" in workflow
    assert 'class="navbar report-navbar"' in document
    assert 'class="nav-link"' in document
    assert "# 关于本项目\n" in document
    assert "CygnusX BioOps" in document
    assert "../logo/logo.png" in document
    assert "../logo/Huazhong_Agricultural_University_logo.svg" in document

    pdf = compose_report(config, tmp_path, pdf=True).read_text(encoding="utf-8")
    assert "report-navbar" not in pdf
    assert "# 样本信息" in pdf


def test_json_paths_resolve_from_data_dir(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "report": {"modules": ["about"], "output_format": ["html", "pdf"]},
        "input_files": {"data_dir": "data", "sample_file": "samples.csv"},
    }), encoding="utf-8")

    config = load_config(config_path)

    assert config["input_files"]["sample_file"] == str(tmp_path / "data" / "samples.csv")
    assert output_formats(config) == ["html", "pdf"]


def test_ai_prompt_resolves_from_config_directory(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "report": {"modules": ["about", "ai"]},
        "ai": {"prompt_file": "prompts/interpretation.txt"},
        "input_files": {"data_dir": "data"},
    }), encoding="utf-8")

    config = load_config(config_path)

    assert config["ai"]["prompt_file"] == str(tmp_path / "prompts" / "interpretation.txt")


def test_generated_config_uses_container_data_mount_and_preserves_paths(tmp_path):
    yaml_path = tmp_path / "report.yaml"
    json_path = tmp_path / "project.json"
    update_yaml_config("Client", "Species", "Genome", "Pipeline", yaml_path)
    update_json_config("Client", "Species", "Genome", "Pipeline", json_path)

    for path in (yaml_path, json_path):
        config = load_config(path)
        assert config["input_files"]["data_dir"] == "/data"
        assert config["input_files"]["tpm_file"] == "/data/index/merge_rsem_tpm.tsv"
        assert config["input_files"]["deg_dir"] == "/data/res/DEG"

    json_data = json.loads(json_path.read_text(encoding="utf-8"))
    json_data["input_files"]["tpm_file"] = "/custom/matrix.tsv"
    json_path.write_text(json.dumps(json_data), encoding="utf-8")
    update_json_config("New Client", "Species", "Genome", "Pipeline", json_path)
    assert load_config(json_path)["input_files"]["tpm_file"] == "/custom/matrix.tsv"


def test_cli_default_search_and_explicit_missing_config(tmp_path, monkeypatch):
    config_path = tmp_path / "report.json"
    config_path.write_text('{"report": {"modules": ["about"]}}', encoding="utf-8")
    monkeypatch.setattr("bioreport.config.DEFAULT_CONFIG_PATHS", [str(config_path)])

    assert load_config_with_fallback(None)["_config_path"] == str(config_path)
    with pytest.raises(SystemExit):
        load_config_with_fallback(str(tmp_path / "missing.json"))


def test_metadata_does_not_fill_missing_inputs_from_sample_data(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "report": {"modules": ["results.matrix"]},
        "input_files": {"tpm_file": "matrix.tsv"},
    }), encoding="utf-8")
    monkeypatch.setenv("REPORT_CONFIG", str(config_path))

    metadata = load_project_metadata()

    assert metadata["input_files"] == {"tpm_file": str(tmp_path / "matrix.tsv")}
    monkeypatch.setenv("REPORT_CONFIG", str(tmp_path / "missing.json"))
    with pytest.raises(FileNotFoundError, match="Report config not found"):
        load_project_metadata()


def test_json_schema_reports_invalid_analysis_field(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "report": {"modules": ["about"], "output_format": "html"},
        "analysis": {"deg": {"pvalue_threshold": 1.5}},
    }), encoding="utf-8")

    with pytest.raises(ValueError, match=r"analysis\.deg\.pvalue_threshold"):
        load_config(config_path)


def test_selected_modules_require_declared_inputs():
    with pytest.raises(ValueError, match="tpm_file"):
        selected_modules({"report": {"modules": ["results"]}, "input_files": {}})
    with pytest.raises(ValueError, match="Unknown report modules"):
        selected_modules({"report": {"modules": ["unknown"]}})
    with pytest.raises(ValueError, match="require the index"):
        selected_modules({"report": {"layout": "website", "modules": ["about"]}})


def test_disabling_ai_removes_its_module():
    config = {"report": {"modules": ["about", "ai"]}, "ai": {"enabled": False}}
    assert selected_modules(config) == ["about"]
    with pytest.raises(ValueError, match="No report modules remain"):
        selected_modules({"report": {"modules": ["ai"]}, "ai": {"enabled": False}})


def test_composed_pdf_retains_content_without_remote_callout_icons(tmp_path):
    qmd = tmp_path / "qmd"
    qmd.mkdir()
    (qmd / "about.qmd").write_text(
        "---\ntitle: Example\n---\n\n::: {.callout-note}\nVisible content\n:::\n",
        encoding="utf-8",
    )
    config = {"report": {"modules": ["about"], "title": "Report"}}

    html_doc = compose_report(config, tmp_path).read_text(encoding="utf-8")
    pdf_doc = compose_report(config, tmp_path, pdf=True).read_text(encoding="utf-8")

    assert "Visible content" in html_doc and "Visible content" in pdf_doc
    assert "callout-note" in html_doc
    assert "callout-note" not in pdf_doc
    assert "report-note" in pdf_doc


def test_selected_result_fragments_keep_shared_setup_once(tmp_path):
    source = Path(__file__).resolve().parents[1] / "omics" / "rna" / "qmd"
    qmd = tmp_path / "qmd"
    qmd.mkdir()
    shutil.copyfile(source / "results.qmd", qmd / "results.qmd")
    shutil.copytree(source / "modules" / "results", qmd / "modules" / "results")
    config = {
        "report": {"modules": ["results.matrix", "results.enrichment"]},
        "input_files": {"tpm_file": "matrix.tsv", "contrasts_file": "contrasts.csv", "enrichment_dir": "enrichments"},
    }

    content = compose_report(config, tmp_path).read_text(encoding="utf-8")

    assert content.count("label: setup-import-res") == 1
    assert "table-tpm-preview" in content
    assert "plot-enrichments-dynamic-up" in content
    assert "plot-pca" not in content
    assert "fig-volcano-dynamic" not in content
    assert "图注说明: Enrichment Dotplot" in content


def test_selected_qc_fragments_keep_shared_setup_once(tmp_path):
    source = Path(__file__).resolve().parents[1] / "omics" / "rna" / "qmd"
    qmd = tmp_path / "qmd"
    qmd.mkdir()
    shutil.copyfile(source / "qc.qmd", qmd / "qc.qmd")
    shutil.copytree(source / "modules" / "qc", qmd / "modules" / "qc")
    config = {
        "report": {"modules": ["qc.fastp", "qc.star"]},
        "input_files": {"fastp_stats_file": "stats.tsv", "fastp_report_dir": "fastp", "qualimap_dir": "qualimap"},
    }

    content = compose_report(config, tmp_path).read_text(encoding="utf-8")

    assert content.count("label: setup-import-qc") == 1
    assert "label: fastp-table" in content
    assert "label: STAR" in content
    assert "label: QualiMap" not in content
    assert "label: fastq-screen-R1" not in content


def test_legacy_json_uses_default_modules():
    legacy = Path(__file__).resolve().parents[1] / "examples" / "rna-seq-project_summary.json"
    config = load_config(legacy)

    assert selected_modules(config) == ["index", "workflow", "qc", "results", "about"]


def test_ai_include_is_resolved_after_generation(tmp_path):
    source = Path(__file__).resolve().parents[1] / "omics" / "rna" / "qmd" / "AI.qmd"
    qmd = tmp_path / "qmd"
    qmd.mkdir()
    shutil.copyfile(source, qmd / "AI.qmd")
    config = {"report": {"modules": ["ai"]}, "ai": {"enabled": True}}

    html_doc = compose_report(config, tmp_path).read_text(encoding="utf-8")
    pdf_doc = compose_report(config, tmp_path, pdf=True).read_text(encoding="utf-8")

    assert "{{< include ../data/consolidated_rna_seq_report.md >}}" in html_doc
    assert "{{< include ../data/consolidated_rna_seq_report.md >}}" in pdf_doc


def test_custom_module_resolves_from_json_and_stages_bibliography(tmp_path):
    source_dir = tmp_path / "custom"
    source_dir.mkdir()
    (source_dir / "finding.qmd").write_text(
        "---\nbibliography: finding.bib\n---\n\nCustom result [@finding].\n",
        encoding="utf-8",
    )
    (source_dir / "finding.bib").write_text(
        "@article{finding, title={Example}, author={A}, year={2024}}\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "report": {
            "modules": ["custom.finding"],
            "module_definitions": {
                "custom.finding": {
                    "path": "custom/finding.qmd",
                    "title": "Finding",
                    "required_inputs": ["measurements"],
                }
            },
        },
        "input_files": {"measurements": "measurements.csv"},
    }), encoding="utf-8")
    template_dir = tmp_path / "templates"
    (template_dir / "qmd").mkdir(parents=True)
    config = load_config(config_path)

    assert selected_modules(config) == ["custom.finding"]
    pdf_doc = compose_report(config, template_dir, pdf=True).read_text(encoding="utf-8")

    assert "# Finding" in pdf_doc
    assert "Custom result [@finding]." in pdf_doc
    assert "../reference/custom.finding-finding.bib" in pdf_doc
    assert (template_dir / "reference" / "custom.finding-finding.bib").exists()


def test_custom_module_expands_nested_includes(tmp_path):
    source_dir = tmp_path / "custom"
    fragments = source_dir / "fragments"
    fragments.mkdir(parents=True)
    (source_dir / "finding.qmd").write_text(
        "{{< include fragments/overview.qmd >}}\n", encoding="utf-8"
    )
    (fragments / "overview.qmd").write_text(
        "Overview\n{{< include details.qmd >}}\n", encoding="utf-8"
    )
    (fragments / "details.qmd").write_text("Measured result.\n", encoding="utf-8")
    template_dir = tmp_path / "templates"
    (template_dir / "qmd").mkdir(parents=True)
    config = {
        "report": {"modules": ["custom.finding"], "module_definitions": {
            "custom.finding": {"path": str(source_dir / "finding.qmd")}
        }}
    }

    content = compose_report(config, template_dir).read_text(encoding="utf-8")

    assert "Overview\nMeasured result." in content
    assert "{{< include" not in content
    (fragments / "details.qmd").write_text(
        "{{< include overview.qmd >}}\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="Circular QMD include"):
        compose_report(config, template_dir)


def test_same_custom_qmd_can_receive_distinct_parameters(tmp_path):
    source = tmp_path / "measurements.qmd"
    source.write_text("Measurements for this run.\n", encoding="utf-8")
    qmd = tmp_path / "templates" / "qmd"
    qmd.mkdir(parents=True)
    config = {"report": {
        "modules": ["custom.baseline", "custom.followup"],
        "module_definitions": {
            "custom.baseline": {"path": str(source), "params": {"input_key": "baseline"}},
            "custom.followup": {"path": str(source), "params": {"input_key": "followup"}},
        },
    }}

    content = compose_report(config, qmd.parent).read_text(encoding="utf-8")
    literals = re.findall(r"report_module = _bioreport_json.loads\((.+)\)", content)
    contexts = [json.loads(ast.literal_eval(value)) for value in literals]

    assert contexts == [
        {"id": "custom.baseline", "params": {"input_key": "baseline"}},
        {"id": "custom.followup", "params": {"input_key": "followup"}},
    ]


def test_reused_custom_module_has_distinct_chunk_labels_and_references(tmp_path):
    source = tmp_path / "finding.qmd"
    source.write_text(
        "See @fig-result.\n\n```{python}\n#| label: 'fig-result'\n#| fig-cap: Result\n"
        "print('result')\n```\n",
        encoding="utf-8",
    )
    qmd = tmp_path / "templates" / "qmd"
    qmd.mkdir(parents=True)
    config = {"report": {
        "modules": ["custom.baseline", "custom.followup"],
        "module_definitions": {
            "custom.baseline": {"path": str(source)},
            "custom.followup": {"path": str(source)},
        },
    }}

    content = compose_report(config, qmd.parent).read_text(encoding="utf-8")

    for name, position in (("baseline", 1), ("followup", 2)):
        label = f"fig-custom-{name}-{position}-result"
        assert f"#| label: '{label}'" in content
        assert f"@{label}" in content
    assert "@fig-result" not in content


def test_custom_module_required_file_is_checked(tmp_path):
    config = {
        "report": {
            "modules": ["custom.finding"],
            "module_definitions": {
                "custom.finding": {"path": "finding.qmd", "required_inputs": ["measurements"]}
            },
        },
        "input_files": {"measurements": str(tmp_path / "missing.csv")},
    }

    with pytest.raises(FileNotFoundError, match="Input files are missing"):
        check_input_files(config)


def test_explicit_result_file_takes_precedence(tmp_path):
    explicit = tmp_path / "explicit" / "comparison_DEG.csv"
    fallback = tmp_path / "fallback" / "comparison_DEG.csv"
    explicit.parent.mkdir()
    fallback.parent.mkdir()
    explicit.write_text("source,explicit\n", encoding="utf-8")
    fallback.write_text("source,fallback\n", encoding="utf-8")

    assert get_file_path({"files": {explicit.name: str(explicit)}}, explicit.name, str(fallback.parent)) == str(explicit)


def test_invalid_contrasts_file_fails_before_rendering_empty_results(tmp_path):
    contrasts = tmp_path / "contrasts.csv"
    contrasts.write_text("Control,Other\nA,B\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing columns: Treat"):
        get_comparisons_from_csv(contrasts)
