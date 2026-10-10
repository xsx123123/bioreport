import json
from types import SimpleNamespace

import pytest

from bioreport import ai
from bioreport.pipeline import run_ai_pipeline
from bioreport.utils.consolidate_rna_seq_data import run_generate, run_report


def test_pipeline_passes_provider_to_report_command(tmp_path, monkeypatch):
    template_dir = tmp_path / "templates"
    (template_dir / "data").mkdir(parents=True)
    calls = {}

    def fake_generate(output_path, *args):
        calls["generate"] = args
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("consolidated", encoding="utf-8")

    def fake_report(input_path, output_dir, model, temperature, provider, verbose):
        calls["report"] = (input_path, output_dir, model, temperature, provider, verbose)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "AI_Interpretation_Report.md").write_text("AI finding", encoding="utf-8")

    monkeypatch.setattr("bioreport.pipeline.run_generate", fake_generate)
    monkeypatch.setattr("bioreport.pipeline.run_report", fake_report)
    config = {"ai": {"enabled": True, "provider": "aliyun", "model": "qwen-example"}}

    run_ai_pipeline(config, "report.json", str(tmp_path), template_dir)

    report_call = calls["report"]
    assert report_call[4] == "aliyun"
    assert report_call[2] == "qwen-example"
    assert (template_dir / "data" / "consolidated_rna_seq_report.md").read_text() == "AI finding"
    with pytest.raises(ValueError, match="ai.model is required"):
        run_ai_pipeline({"ai": {"provider": "aliyun"}}, "report.json", str(tmp_path), template_dir)


def test_pipeline_rejects_missing_custom_prompt(tmp_path):
    template_dir = tmp_path / "templates"
    with pytest.raises(FileNotFoundError, match="AI prompt file is missing"):
        run_ai_pipeline(
            {"ai": {"prompt_file": str(tmp_path / "missing.txt")}},
            "report.json", str(tmp_path), template_dir,
        )


def test_report_uses_selected_provider(tmp_path, monkeypatch):
    input_path = tmp_path / "input.txt"
    input_path.write_text("Analysis data", encoding="utf-8")
    initialized = []

    class Interpreter:
        def __init__(self, **kwargs):
            initialized.append(kwargs)

        def execute_inference(self, **kwargs):
            return SimpleNamespace(content="<bio_report>Finding</bio_report>")

        def _verify_and_extract_content(self, content):
            return content.removeprefix("<bio_report>").removesuffix("</bio_report>")

    monkeypatch.setattr(ai, "AIInterpreter", Interpreter)
    monkeypatch.setattr("bioreport.utils.consolidate_rna_seq_data.setup_logging", lambda verbose: None)

    run_report(input_path, tmp_path / "output", "qwen-example", 0.2, "aliyun", False)

    assert initialized == [{"model": "qwen-example", "provider": "aliyun"}]
    assert (tmp_path / "output" / "AI_Interpretation_Report.md").read_text() == "Finding"


def test_ai_input_includes_each_comparison(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    deg_dir = data_dir / "deg"
    enrichment_dir = data_dir / "enrichment"
    deg_dir.mkdir(parents=True)
    enrichment_dir.mkdir()
    for name in ("B_vs_A", "C_vs_A"):
        (deg_dir / f"{name}_DEG.csv").write_text("gene,pvalue\nG1,0.01\n", encoding="utf-8")
        (enrichment_dir / f"{name}_UP.csv").write_text("Description,Count\nPathway,3\n", encoding="utf-8")
    config_path = tmp_path / "report.json"
    config_path.write_text(
        '{"input_files": {"data_dir": "data", "deg_dir": "deg", "enrichment_dir": "enrichment"}}',
        encoding="utf-8",
    )
    monkeypatch.setattr("bioreport.utils.consolidate_rna_seq_data.setup_logging", lambda verbose: None)
    output_path = tmp_path / "summary.txt"

    run_generate(output_path, 5, 5, tmp_path / "no-prompt.txt", config_path, False)

    summary = output_path.read_text(encoding="utf-8")
    assert summary.count("Differential Expression (") == 2
    assert "B_vs_A_DEG" in summary and "C_vs_A_DEG" in summary
    assert "B_vs_A_UP" in summary and "C_vs_A_UP" in summary


def test_ai_input_follows_contrasts_and_explicit_files(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    deg_dir = data_dir / "deg"
    enrichment_dir = data_dir / "enrichment"
    deg_dir.mkdir(parents=True)
    enrichment_dir.mkdir()
    (data_dir / "contrasts.csv").write_text("Control,Treat\nA,B\nA,C\n", encoding="utf-8")
    for name in ("B_vs_A", "C_vs_A", "D_vs_A"):
        (deg_dir / f"{name}_DEG.csv").write_text(f"gene,pvalue\n{name},0.01\n", encoding="utf-8")
        (enrichment_dir / f"{name}_UP.csv").write_text(f"Description,Count\n{name},3\n", encoding="utf-8")
    preferred = data_dir / "preferred.csv"
    preferred.write_text("gene,pvalue\nPreferredGene,0.001\n", encoding="utf-8")
    config_path = tmp_path / "report.json"
    config_path.write_text(json.dumps({
        "input_files": {
            "data_dir": "data",
            "deg_dir": "deg",
            "enrichment_dir": "enrichment",
            "contrasts_file": "contrasts.csv",
        },
        "files": {"B_vs_A_DEG.csv": "preferred.csv"},
    }), encoding="utf-8")
    monkeypatch.setattr("bioreport.utils.consolidate_rna_seq_data.setup_logging", lambda verbose: None)
    output_path = tmp_path / "summary.txt"

    run_generate(output_path, 5, 5, tmp_path / "no-prompt.txt", config_path, False)

    summary = output_path.read_text(encoding="utf-8")
    assert "PreferredGene" in summary
    assert "C_vs_A_DEG" in summary and "C_vs_A_UP" in summary
    assert "B_vs_A_UP" in summary
    assert "D_vs_A" not in summary
    assert "| B_vs_A | 0.01 |" not in summary
