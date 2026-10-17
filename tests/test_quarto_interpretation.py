import json
from pathlib import Path

import pytest

from bioreport.modules import _module_ai_slot, stage_module_interpretations


def test_ai_qmd_has_optional_module_interpretation_include():
    content = Path("templates/shared/AI.qmd").read_text(encoding="utf-8")
    assert "module_interpretations.md" in content
    assert "is_file()" in content


def test_module_ai_slot_is_optional_and_path_is_server_generated():
    slot = _module_ai_slot("rna.results.deg")
    assert 'glob("rna.results.deg__*.md")' in slot
    assert '_BioReportPath("../data/ai_interpretations")' in slot
    assert "is_symlink()" in slot
    assert "{module_id}" not in slot


def test_stage_module_interpretations_uses_logical_ids_and_rejects_symlinks(tmp_path):
    written = stage_module_interpretations(
        tmp_path,
        {"rna.results.deg__2_vs_1": "## Findings\n- one"},
    )
    assert written[0].relative_to(tmp_path) == Path("data/ai_interpretations/rna.results.deg__2_vs_1.md")
    assert written[0].read_text(encoding="utf-8").startswith("## Findings")
    manifest = tmp_path / "data" / "ai_reports" / "ai-interpretation-manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["artifacts"][0]["sha256"]
    assert payload["artifacts"][0]["path"] == "ai_interpretations/rna.results.deg__2_vs_1.md"

    execution_manifest = stage_module_interpretations(
        tmp_path, {"rna.results.deg": "x"}, execution_id="exec-1"
    )
    assert execution_manifest
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["execution_id"] == "exec-1"

    target = tmp_path / "symlinked"
    target.mkdir()
    (tmp_path / "data" / "ai_interpretations").rename(target / "ai_interpretations")
    (tmp_path / "data" / "ai_reports").rename(target / "ai_reports")
    (tmp_path / "data").rmdir()
    (tmp_path / "data").symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="AI_INTERPRETATION_DIR_SYMLINK"):
        stage_module_interpretations(tmp_path, {"rna.results.deg": "x"})


@pytest.mark.parametrize("content", ["<script>alert(1)</script>", "{{< include ../secret >}}", "```{python}\nprint(1)\n```"])
def test_stage_module_interpretations_rejects_executable_or_include_markup(tmp_path, content):
    with pytest.raises(ValueError, match="AI_INTERPRETATION_UNSAFE_MARKUP"):
        stage_module_interpretations(tmp_path, {"rna.results.deg": content})


def test_stage_module_interpretations_rejects_safe_id_collisions(tmp_path):
    with pytest.raises(ValueError, match="AI_INTERPRETATION_MODULE_ID_COLLISION"):
        stage_module_interpretations(tmp_path, {"a/b": "one", "a-b": "two"})


def test_stage_module_interpretations_clears_reused_staging_tree(tmp_path):
    stage_module_interpretations(tmp_path, {"rna.results.deg": "old"})
    assert (tmp_path / "data" / "ai_interpretations" / "rna.results.deg.md").is_file()
    assert stage_module_interpretations(tmp_path, None) == []
    assert list((tmp_path / "data" / "ai_interpretations").glob("*.md")) == []
    payload = json.loads((tmp_path / "data" / "ai_reports" / "ai-interpretation-manifest.json").read_text(encoding="utf-8"))
    assert payload["artifacts"] == []
