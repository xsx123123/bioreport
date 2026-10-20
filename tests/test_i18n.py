from pathlib import Path
import base64
import gzip
import json


def test_rna_reports_default_to_both_languages_and_distinct_names():
    from bioreport.i18n import languages
    from bioreport.config import report_artifact_name
    config = {"report": {"type": "rna-seq", "output_format": ["html", "pdf"]}, "project": {"project_id": "P 1"}}
    assert languages(config) == ["zh", "en"]
    assert report_artifact_name(config, "pdf", "zh") == "P-1_report.pdf"
    assert report_artifact_name(config, "pdf", "en") == "P-1_report.en.pdf"


def test_language_switch_preserves_page_fragment_and_links_edition(tmp_path):
    from bs4 import BeautifulSoup
    from bioreport.i18n import add_language_switch
    config = {"report": {"type": "rna-seq"}, "project": {"project_id": "P1"}}
    page = tmp_path / "P1_report.html"
    page.write_text("<html><head></head><body><nav class='navbar'></nav></body></html>")
    add_language_switch(page, config, "zh")
    soup = BeautifulSoup(page.read_text(), "html.parser")
    link = soup.select_one("[data-language-target]")
    assert link["data-language-target"] == "P1_report.en.html"
    assert link["data-language"] == "en"
    assert link["aria-pressed"] == "false"
    assert soup.select_one('[data-language="zh"]')["aria-pressed"] == "true"
    assert "location.hash" in soup.script.text
    assert link.text == "EN"
    assert soup.select_one("[data-report-language]")["role"] == "group"


def test_single_html_contains_both_language_editions(tmp_path):
    from bioreport.i18n import combine_language_editions
    from bioreport.utils.provenance import expected_report_paths
    config = {"report": {"type": "rna-seq", "output_format": "html"}, "project": {"project_id": "P1"}}
    chinese = tmp_path / "zh.html"
    english = tmp_path / "en.html"
    combined = tmp_path / "P1_report.html"
    chinese.write_text("<html lang='zh-CN'><body>中文内容</body></html>", encoding="utf-8")
    english.write_text("<html lang='en'><body>English edition</body></html>", encoding="utf-8")
    combine_language_editions(chinese, english, combined, "P1 双语报告")
    source = combined.read_text(encoding="utf-8")
    for language, expected in (("zh", "中文内容"), ("en", "English edition")):
        encoded = source.split(f'id="edition-{language}" type="application/octet-stream">\n', 1)[1].split("</script>", 1)[0]
        restored = gzip.decompress(base64.b64decode(encoded)).decode("utf-8")
        assert expected in restored
    assert "DecompressionStream('gzip')" in source
    assert '.loading[hidden]{display:none}' in source
    assert expected_report_paths(config) == ["P1_report.html"]


def test_bilingual_loading_script_hides_overlay_and_switches_languages(tmp_path):
    import shutil
    import subprocess
    import pytest
    from bioreport.i18n import combine_language_editions
    if not shutil.which('node'):
        pytest.skip('Node.js is required to execute the report loading script')
    for lang in ('zh', 'en'):
        (tmp_path / f'{lang}.html').write_text(f'<html lang="{lang}"><body>{lang}</body></html>')
    combined = tmp_path / 'report.html'
    combine_language_editions(tmp_path / 'zh.html', tmp_path / 'en.html', combined)
    subprocess.run(['node', str(Path(__file__).with_name('report_editions.cjs')), str(combined)],
                   check=True, capture_output=True, text=True, timeout=15)


def test_delivery_manifest_records_one_bilingual_html(tmp_path):
    from bioreport.utils.provenance import build_provenance, write_delivery_manifests, validate_delivery_manifests
    config = {"report": {"type": "rna-seq", "output_format": "html"}, "project": {"project_id": "P1"}, "input_files": {}}
    (tmp_path / "P1_report.html").write_text("bilingual report", encoding="utf-8")
    provenance = build_provenance(config, [])
    write_delivery_manifests(config, provenance, tmp_path)
    assert validate_delivery_manifests(config, tmp_path)["status"] == "PASS"
    record = json.loads((tmp_path / "report-manifest.json").read_text())["artifacts"][0]
    assert record["path"] == "P1_report.html"
    assert record["language"] == "zh+en"


def test_expected_delivery_manifest_requires_every_rna_format_and_language(tmp_path):
    from bioreport.utils.provenance import build_provenance, write_delivery_manifests, validate_delivery_manifests
    config = {"report": {"type": "rna-seq", "output_format": "pdf"}, "project": {"project_id": "P1"}, "input_files": {}}
    for name in ("P1_report.pdf", "P1_report.en.pdf"):
        (tmp_path / name).write_bytes(name.encode())
    provenance = build_provenance(config, [])
    write_delivery_manifests(config, provenance, tmp_path)
    assert validate_delivery_manifests(config, tmp_path)["status"] == "PASS"
    (tmp_path / "P1_report.en.pdf").unlink()
    write_delivery_manifests(config, provenance, tmp_path)
    assert "report_language_coverage" in {e["error"] for e in validate_delivery_manifests(config, tmp_path)["errors"]}


def test_website_language_segments_match_the_current_page(tmp_path):
    from bs4 import BeautifulSoup
    from bioreport.website import finalize_website
    qmd = tmp_path / 'qmd'
    qmd.mkdir()
    for lang in ('zh', 'en'):
        (qmd / f'site-{lang}-index.html').write_text(
            '<html><head></head><body><nav class="report-navbar">'
            '<button data-report-language>English</button>'
            '</nav></body></html>', encoding='utf-8')
    finalize_website(tmp_path, {'report': {'type': 'rna-seq'}})
    for lang, other in [('zh', 'en'), ('en', 'zh')]:
        soup = BeautifulSoup((qmd / f'site-{lang}-index.html').read_text(), 'html.parser')
        group = soup.select_one('[data-report-language]')
        assert group['role'] == 'group'
        assert len(group.select('button')) == 2
        assert group.select_one('[aria-pressed="true"]')['data-language'] == lang
        assert group.select_one('[aria-pressed="false"]')['data-language-target'] == f'site-{other}-index.html'
