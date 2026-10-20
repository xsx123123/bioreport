from pathlib import Path
import shutil

import pytest
from jinja2 import Environment, FileSystemLoader

from bioreport.renderer import render_templates
from bioreport.utils.report_pet import build_pet_context, stage_pet_template


ROOT = Path(__file__).resolve().parents[1]


def test_pet_is_disabled_by_default_and_for_pdf():
    config = {"report": {}}

    assert build_pet_context(config, ROOT / "templates", ["html"]) == {"enabled": False}
    assert build_pet_context({"report": {"pet": {"enabled": True}}}, ROOT / "templates", ["pdf"]) == {
        "enabled": False
    }


def test_enabled_pet_embeds_taotao_assets_and_stages_include(tmp_path):
    config = {"report": {"pet": {"enabled": True, "size": 160}}}
    pet = build_pet_context(config, ROOT / "templates", ["html"])

    assert pet["enabled"] is True
    assert pet["size"] == 160
    assert pet["assets"]["idle"].startswith("data:image/gif;base64,")
    assert pet["assets"]["still"].startswith("data:image/png;base64,")

    environment = Environment(loader=FileSystemLoader(ROOT / "templates"))
    template_dir = tmp_path / "templates"
    (template_dir / "theme").mkdir(parents=True)
    stage_pet_template(environment, template_dir, pet)
    rendered = (template_dir / "theme/report-pet.html").read_text(encoding="utf-8")
    assert 'id="bioreport-pet"' in rendered
    assert "data:image/gif;base64," in rendered
    assert "pointerdown" in rendered
    pointerdown = rendered.split("root.addEventListener('pointerdown'", 1)[1].split("root.addEventListener('pointermove'", 1)[0]
    assert "setPointerCapture" not in pointerdown
    assert "setPointerCapture" in rendered.split("root.addEventListener('pointermove'", 1)[1]


def test_pet_settings_reject_invalid_values():
    with pytest.raises(ValueError, match="enabled"):
        build_pet_context({"report": {"pet": {"enabled": "yes"}}}, ROOT / "templates", ["html"])
    with pytest.raises(ValueError, match="size"):
        build_pet_context({"report": {"pet": {"enabled": True, "size": 80}}}, ROOT / "templates", ["html"])


def _staged_templates(tmp_path):
    staged = tmp_path / "templates"
    shutil.copytree(ROOT / "templates", staged)
    shutil.copytree(ROOT / "templates/shared", staged / "qmd")
    return staged


def test_renderer_includes_pet_only_when_explicitly_enabled(tmp_path):
    disabled = _staged_templates(tmp_path / "disabled")
    base = {"report": {"layout": "single", "modules": ["about"], "output_format": "html"}}
    render_templates(base, str(tmp_path / "disabled-output"), str(disabled))
    disabled_quarto = (disabled / "_quarto.yml").read_text(encoding="utf-8")
    assert "report-pet.html" not in disabled_quarto
    assert not (disabled / "theme/report-pet.html").exists()

    enabled = _staged_templates(tmp_path / "enabled")
    enabled_config = {
        **base,
        "report": {**base["report"], "pet": {"enabled": True, "size": 160}},
    }
    render_templates(enabled_config, str(tmp_path / "enabled-output"), str(enabled))
    enabled_quarto = (enabled / "_quarto.yml").read_text(encoding="utf-8")
    assert "report-pet.html" in enabled_quarto
    assert 'id="bioreport-pet"' in (enabled / "theme/report-pet.html").read_text(encoding="utf-8")
