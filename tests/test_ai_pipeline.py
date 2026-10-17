import json
from types import SimpleNamespace

import pytest

from bioreport import ai
from bioreport.pipeline import run_ai_pipeline, _clean_ai_markdown
from bioreport.utils.consolidate_rna_seq_data import run_generate, run_report
from bioreport.ai.engine import AIInterpreter


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
    config = {"ai": {"enabled": True, "scope": "global", "provider": "aliyun", "model": "qwen-example"}}

    run_ai_pipeline(config, "report.json", str(tmp_path), template_dir)

    report_call = calls["report"]
    assert report_call[4] == "aliyun"
    assert report_call[2] == "qwen-example"
    assert (template_dir / "data" / "consolidated_rna_seq_report.md").read_text() == "AI finding"
    with pytest.raises(ValueError, match="ai.model is required"):
        run_ai_pipeline({"ai": {"scope": "global", "provider": "aliyun"}}, "report.json", str(tmp_path), template_dir)


def test_ai_engine_vision_fallback_and_attachment_limits(tmp_path):
    image = tmp_path / "figure.png"
    image.write_bytes(b"not really an image")
    interpreter = AIInterpreter(provider="mock", config={"vision": False})
    assert interpreter._vision_enabled() is False
    # The encoder remains bounded independently of the provider capability.
    assert interpreter._encode_file(str(image)).startswith("data:image/png;base64,")
    link = tmp_path / "link.png"
    link.symlink_to(image)
    assert interpreter._encode_file(str(link)) is None


def test_all_compatible_providers_use_openai_sdk(monkeypatch):
    from bioreport.ai import engine

    created = []

    class FakeOpenAI:
        def __init__(self, **kwargs):
            created.append(kwargs)

    monkeypatch.setattr(engine, "OpenAI", FakeOpenAI)
    monkeypatch.setenv("ARK_API_KEY", "ark-test-key")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dashscope-test-key")
    monkeypatch.setenv("CUSTOM_LLM_TOKEN", "custom-test-key")

    AIInterpreter(provider="volcengine")
    AIInterpreter(provider="aliyun")
    AIInterpreter(
        provider="openai-compatible",
        config={"base_url": "https://llm.example/v1", "api_key_env": "CUSTOM_LLM_TOKEN"},
    )

    assert created == [
        {"api_key": "ark-test-key", "base_url": "https://ark.cn-beijing.volces.com/api/v3", "timeout": 120},
        {"api_key": "dashscope-test-key", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "timeout": 120},
        {"api_key": "custom-test-key", "base_url": "https://llm.example/v1", "timeout": 120},
    ]


def test_openai_compatible_provider_reports_missing_key(monkeypatch):
    from bioreport.ai.engine import AIInterpretationError

    monkeypatch.delenv("CUSTOM_LLM_TOKEN", raising=False)
    with pytest.raises(AIInterpretationError, match="CUSTOM_LLM_TOKEN"):
        AIInterpreter(provider="openai-compatible", config={"api_key_env": "CUSTOM_LLM_TOKEN", "base_url": "https://llm.example/v1"})


def test_pipeline_passes_complete_ai_config_when_supported(tmp_path, monkeypatch):
    template_dir = tmp_path / "templates"
    (template_dir / "data").mkdir(parents=True)
    captured = {}

    monkeypatch.setattr("bioreport.pipeline.run_generate", lambda output_path, *args: output_path.write_text("data", encoding="utf-8"))
    def fake_report(*args, config=None):
        captured["config"] = config
        output_dir = args[1]
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "AI_Interpretation_Report.md").write_text("ok", encoding="utf-8")
    monkeypatch.setattr("bioreport.pipeline.run_report", fake_report)
    ai_config = {"enabled": True, "scope": "global", "provider": "volcengine", "fallback_providers": ["aliyun"], "max_input_tokens": 123, "pricing": {"default": {"input": 1}}}
    run_ai_pipeline({"ai": ai_config}, "report.json", str(tmp_path), template_dir)
    assert captured["config"] == ai_config


def test_run_report_wrapper_forwards_complete_config(monkeypatch):
    captured = {}

    def implementation(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs

    monkeypatch.setattr("bioreport.utils.consolidate_rna_seq_data.run_report", implementation)
    from bioreport.pipeline import run_report

    run_report("input", "output", None, 0.7, "volcengine", True, config={"vision": False, "max_input_tokens": 12})
    assert captured["kwargs"]["config"] == {"vision": False, "max_input_tokens": 12}


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
        '{"project": {"project_id": "PRJ-AI-TEST"}, '
        '"input_files": {"data_dir": "data", "deg_dir": "deg", "enrichment_dir": "enrichment"}}',
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
        "project": {"project_id": "PRJ-AI-TEST"},
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


def test_pipeline_generates_per_result_interpretations_by_default(tmp_path, monkeypatch):
    template_dir = tmp_path / "templates"
    data_dir = tmp_path / "data"
    deg_dir = data_dir / "deg"
    enrichment_dir = data_dir / "enrichment"
    deg_dir.mkdir(parents=True)
    enrichment_dir.mkdir()
    (deg_dir / "B_vs_A_DEG.csv").write_text("gene,pvalue\nG1,0.01\n", encoding="utf-8")
    (enrichment_dir / "B_vs_A_UP.csv").write_text("Description,Count\nPathway,3\n", encoding="utf-8")
    calls = []

    class FakeInterpreter:
        def __init__(self, **kwargs):
            calls.append(("init", kwargs))

        def execute_inference(self, **kwargs):
            calls.append(("infer", kwargs))
            return SimpleNamespace(content="<bio_report>Finding</bio_report>")

        def _verify_and_extract_content(self, content):
            return content.removeprefix("<bio_report>").removesuffix("</bio_report>")

    monkeypatch.setattr("bioreport.ai.AIInterpreter", FakeInterpreter)
    run_ai_pipeline({
        "input_files": {"data_dir": str(data_dir), "deg_dir": "deg", "enrichment_dir": "enrichment"},
        "ai": {"enabled": True, "provider": "mock", "model": "test-model"},
    }, str(tmp_path / "report.json"), str(tmp_path), template_dir)

    staged = sorted((template_dir / "data" / "ai_interpretations").glob("*.md"))
    assert [path.name for path in staged] == [
        "rna.results.deg__B_vs_A.md", "rna.results.enrichment__B_vs_A_UP.md"
    ]
    assert all("Finding" in path.read_text(encoding="utf-8") for path in staged)
    assert len([call for call in calls if call[0] == "infer"]) == 2


def test_clean_ai_markdown_removes_embedded_yaml_front_matter():
    assert _clean_ai_markdown("---\ntitle: model output\n---\n## Finding") == "**Finding**"


def test_clean_ai_markdown_removes_unmatched_wrappers_and_callout_fences():
    cleaned = _clean_ai_markdown("<bio_report>\n::: {.callout-note}\nFinding\n:::")
    assert cleaned == "Finding"


def test_clean_ai_markdown_removes_raw_html_wrappers():
    assert _clean_ai_markdown("<bio_report><p>Finding</p></bio_report>") == "Finding"
