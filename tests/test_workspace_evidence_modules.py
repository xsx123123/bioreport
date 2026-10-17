import pytest

from bioreport.ai.evidence import EvidenceBuilder


def test_bounded_module_preview_and_matrix_privacy_guard(tmp_path):
    sample = tmp_path / "samples.csv"
    sample.write_text("sample,group,private_path,extra\nS1,A,/secret,1\nS2,B,/secret2,2\n", encoding="utf-8")
    package = EvidenceBuilder(tmp_path).build_table_preview(project_id="P", module_id="rna.results.samples", source=sample, columns=("sample", "group"), row_limit=1)
    table = package.tables[0]
    assert table["columns"] == ["sample", "group"]
    assert len(table["rows"]) == 1
    assert "private_path" not in table["rows"][0]
    with pytest.raises(ValueError, match="FULL_MATRIX_EVIDENCE_FORBIDDEN"):
        EvidenceBuilder(tmp_path).build_table_preview(project_id="P", module_id="rna.results.matrix", source=sample)


def test_registered_module_source_discovery_is_allowlisted(tmp_path):
    source = tmp_path / "enrichment.csv"
    source.write_text("term,pvalue\npathway-a,0.01\n", encoding="utf-8")
    package = EvidenceBuilder(tmp_path).build_registered(project_id="P", module_id="rna.results.enrichment", run_id=3)
    assert package.module_id == "rna.results.enrichment"
    assert package.run_id == 3
    assert package.tables[0]["rows"] == [{"term": "pathway-a", "pvalue": "0.01"}]
    with pytest.raises(FileNotFoundError):
        EvidenceBuilder(tmp_path).build_registered(project_id="P", module_id="rna.qc.star")


def test_evidence_builder_rejects_symlinked_parent_component(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (real / "samples.csv").write_text("sample,group\nS1,A\n", encoding="utf-8")
    (tmp_path / "results").symlink_to(real, target_is_directory=True)
    with pytest.raises(PermissionError, match="EVIDENCE_SOURCE_OUTSIDE_TRUSTED_ROOT"):
        EvidenceBuilder(tmp_path).build_registered(project_id="P", module_id="rna.results.samples")


def test_deg_evidence_registers_fixed_name_figure_or_explicit_gap(tmp_path):
    source = tmp_path / "2_vs_1_DEG.csv"
    source.write_text("Gene,log2FoldChange,pvalue,padj\nA,2,.01,.02\n", encoding="utf-8")
    (tmp_path / "2_vs_1_volcano.png").write_bytes(b"png-fixture")
    package = EvidenceBuilder(tmp_path).build_deg(project_id="P", comparison="2_vs_1")
    assert package.figures[0]["figure_id"] == "deg_2_vs_1_volcano"
    assert package.figures[0]["content_type"] == "image/png"
    assert "FIGURE_UNAVAILABLE" not in package.warnings

    (tmp_path / "2_vs_1_volcano.png").unlink()
    without_figure = EvidenceBuilder(tmp_path).build_deg(project_id="P", comparison="2_vs_1")
    assert without_figure.figures == []
    assert "FIGURE_UNAVAILABLE" in without_figure.warnings
