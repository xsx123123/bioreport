"""Built-in font stack, staging and PDF protection contracts."""
import json
from pathlib import Path

import pandas as pd
import pytest

from bioreport.utils import render_output
from bioreport.utils.fonts import font_dir, font_families, typst_font_paths
from bioreport.utils.font_stage import stage_fonts
from bioreport.utils.pdf_security import protect_report_pdf, resolve_owner_password

ROOT = Path(__file__).resolve().parents[1]


def test_builtin_fonts_ship_inside_the_package():
    files = list(font_dir().rglob("*"))
    assert any(f.suffix.lower() in {".ttf", ".otf"} for f in files)
    families = font_families()
    # The built-in stack resolves to families actually shipped, not fallbacks.
    assert any("Sans" in name for name in families)
    assert typst_font_paths() == str(font_dir().resolve())


def test_stage_fonts_copies_weights_and_declares_font_face(tmp_path):
    css = stage_fonts(tmp_path)
    assert css is not None
    staged = {f.name for f in (tmp_path / "fonts").iterdir()}
    assert "HarmonyOS_Sans_SC_Regular.ttf" in staged
    assert "SourceSans3-Regular.ttf" in staged
    text = css.read_text(encoding="utf-8")
    assert "@font-face" in text and "BioReport-Latin" in text and "BioReport-CN" in text
    assert "url('fonts/" in text  # relative URLs keep the folder portable


def test_typst_context_declares_built_in_font_stacks(tmp_path):
    import shutil

    from bioreport.modules import compose_report

    shutil.copytree(ROOT / "templates", tmp_path, dirs_exist_ok=True)
    shutil.copytree(ROOT / "templates/shared", tmp_path / "qmd")
    shutil.copytree(ROOT / "omics/rna/qmd", tmp_path / "qmd", dirs_exist_ok=True)
    cfg = json.loads((ROOT / "tests/report.rna.pdf.json").read_text())
    compose_report(cfg, tmp_path, pdf=True)
    context = (tmp_path / "pdf/print-context.typ").read_text(encoding="utf-8")
    assert "#let report-fonts = (" in context
    assert "Source Han Sans SC" in context or "HarmonyOS Sans SC" in context
    assert "#let report-mono-fonts = (" in context
    style = (tmp_path / "pdf/print-style.typ").read_text(encoding="utf-8")
    assert "report-mono-fonts" in style  # raw blocks use the mono stack


def test_breakable_hash_wraps_long_hex_without_changing_short_text():
    from bioreport.utils.fonts import breakable_hash, breakable_path

    digest = "a" * 64
    wrapped = breakable_hash(digest)
    assert wrapped.replace("​", "") == digest
    assert "​" in wrapped
    assert breakable_path("/home/data/results") == "/​home/​data/​results"


def test_print_table_inserts_zero_width_spaces_into_sha256(monkeypatch):
    outputs = []
    monkeypatch.setattr(render_output, "display", outputs.append)
    frame = pd.DataFrame({"输入文件": ["fastq/sample.fastq.gz"], "SHA256": ["b" * 64]})
    render_output.show_print_table(frame, limit=None)
    text = outputs[0].data
    assert "​" in text
    assert text.replace("​", "").count("b" * 64) == 1


def test_owner_password_prefers_config_and_env_indirection(monkeypatch):
    monkeypatch.delenv("BIOREPORT_OWNER_SECRET", raising=False)
    assert resolve_owner_password({"owner_password": "cfg-secret"}) == "cfg-secret"
    assert resolve_owner_password({"owner_password_env": "BIOREPORT_OWNER_SECRET"}) is None
    monkeypatch.setenv("BIOREPORT_OWNER_SECRET", "env-secret")
    assert resolve_owner_password({"owner_password_env": "BIOREPORT_OWNER_SECRET"}) == "env-secret"
    assert resolve_owner_password(None) is None


def test_protection_is_optional_and_survives_missing_pikepdf(tmp_path, monkeypatch):
    cfg = {"report": {"security": {"enable_read_only_lock": True, "owner_password": "s"}}}
    missing = tmp_path / "missing.pdf"
    assert protect_report_pdf(missing, cfg) is False  # missing file, no crash
    disabled = {"report": {}}
    assert protect_report_pdf(missing, disabled) is False  # not requested


def test_quarto_templates_reference_staged_fonts():
    single = (ROOT / "templates/_quarto-single.yml.j2").read_text(encoding="utf-8")
    website = (ROOT / "templates/_quarto.yml.j2").read_text(encoding="utf-8")
    # Both layouts list the staged fonts.css first, before the theme styles.
    assert "{% if staged_fonts %}" in single and "{% if staged_fonts %}" in website
    single_css = single.split("css:")[1]
    assert single_css.index("{{ staged_fonts }}") < single_css.index("theme/styles.css")
    website_css = website.split("css:")[1]
    assert website_css.index("{{ staged_fonts }}") < website_css.index("theme/styles.css")
