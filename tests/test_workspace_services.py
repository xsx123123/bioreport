import hashlib
import json
import sqlite3

import pytest

from bioreport.artifacts import ArtifactError, ArtifactResolver
from bioreport.report_service import DatabaseUnavailable, ReportNotFound, SQLiteReportRepository


def make_db(path):
    connection = sqlite3.connect(path)
    connection.execute(
        """CREATE TABLE runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL,
            run_at TEXT NOT NULL, engine_version TEXT, pipeline_version TEXT,
            layout TEXT, output_format TEXT, modules TEXT, config_path TEXT,
            output_dir TEXT, status TEXT NOT NULL, input_checksums TEXT,
            created_at TEXT NOT NULL)"""
    )
    connection.executemany(
        "INSERT INTO runs(project_id, run_at, engine_version, pipeline_version, layout, output_format, modules, output_dir, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        [
            ("demo", "2026-10-17T10:00:00", "2", "p1", "single", '["html"]', '["rna.deg", "future.module"]', "", "success", "now"),
            ("demo", "2026-10-16T10:00:00", "2", "p1", "single", "not-json", "[]", "", "failed", "now"),
        ],
    )
    connection.commit()
    connection.close()


def test_repository_is_read_only_and_paginates(tmp_path):
    db = tmp_path / "runs.db"
    make_db(db)
    repository = SQLiteReportRepository(db)
    page = repository.list_reports(limit=1)
    assert len(page.items) == 1
    assert page.next_cursor == "2"
    assert page.items[0].artifact_availability == "PATH_UNAVAILABLE"
    assert page.items[0].manifest_status == "MISSING"
    assert repository.get_report(1).modules[1]["status"] == "unknown"
    assert repository.get_report(2).warnings == ["INVALID_OUTPUT_FORMATS"]
    with pytest.raises(ReportNotFound):
        repository.get_report(99)
    with pytest.raises(sqlite3.OperationalError):
        with repository._connect() as connection:
            connection.execute("CREATE TABLE should_not_exist(x)")


def test_repository_can_apply_exact_project_scope(tmp_path):
    db = tmp_path / "runs.db"
    make_db(db)
    page = SQLiteReportRepository(db).list_reports(projects=["missing"])
    assert page.items == []
    page = SQLiteReportRepository(db).list_reports(projects=["demo"])
    assert [item.project_id for item in page.items] == ["demo", "demo"]


def test_missing_database_is_explicit(tmp_path):
    with pytest.raises(DatabaseUnavailable):
        SQLiteReportRepository(tmp_path / "missing.db").list_reports()


def test_artifact_resolver_verifies_manifest_and_rejects_escape(tmp_path):
    report = tmp_path / "report"
    report.mkdir()
    data = report / "blocks.jsonl"
    data.write_text('{"block_id":"b1"}\n', encoding="utf-8")
    digest = hashlib.sha256(data.read_bytes()).hexdigest()
    (report / "artifact-manifest.json").write_text(
        json.dumps({"artifacts": [
            {"artifact_id": "blocks", "role": "report_blocks", "path": "blocks.jsonl", "sha256": digest},
            {"artifact_id": "escape", "role": "bad", "path": "../secret.txt"},
        ]}), encoding="utf-8"
    )
    resolver = ArtifactResolver(report)
    assert resolver.records()[0].integrity == "verified"
    assert resolver.records(verify=False)[0].integrity == "unverified"
    snapshot = resolver.manifest_snapshot()
    assert snapshot["artifact"]["availability"] == "available"
    assert "path" not in snapshot["artifact"]["artifacts"][0]
    assert "path" not in resolver.records()[0].to_dict()
    assert resolver.get("blocks").integrity == "verified"
    assert resolver.get("blocks").content_type == "application/x-ndjson"
    assert list(resolver.read_jsonl("blocks")) == [{"block_id": "b1"}]
    assert resolver.get("escape").integrity == "forbidden"
    symlink = report / "linked.jsonl"
    symlink.symlink_to(data)
    (report / "artifact-manifest.json").write_text(json.dumps({"artifacts": [{"artifact_id": "linked", "role": "bad", "path": "linked.jsonl"}]}), encoding="utf-8")
    assert ArtifactResolver(report).get("linked").integrity == "forbidden"
    (report / "blocks.jsonl").write_text('{"block_id":"tampered"}\n', encoding="utf-8")
    assert resolver.get("blocks").integrity == "mismatch"
    with pytest.raises(ArtifactError):
        list(resolver.read_jsonl("blocks"))


def test_oversized_manifest_is_not_loaded(tmp_path):
    report = tmp_path / "report"
    report.mkdir()
    (report / "artifact-manifest.json").write_text("x" * 128, encoding="utf-8")
    assert ArtifactResolver(report, max_bytes=32).records() == []


def test_artifact_manifest_validates_declared_size_and_content_type(tmp_path):
    report = tmp_path / "report"
    report.mkdir()
    artifact = report / "summary.json"
    artifact.write_text('{"ok":true}', encoding="utf-8")
    (report / "artifact-manifest.json").write_text(json.dumps({"artifacts": [
        {"artifact_id": "bad-size", "path": artifact.name, "size": 1, "content_type": "application/json"},
        {"artifact_id": "bad-type", "path": artifact.name, "size": artifact.stat().st_size, "content_type": "text/html"},
        {"artifact_id": "bad-extension", "path": "notes.bin"},
    ]}), encoding="utf-8")
    records = {record.artifact_id: record for record in ArtifactResolver(report).records(verify=False)}
    assert records["bad-size"].integrity == "unverified"
    assert ArtifactResolver(report).get("bad-size").integrity == "mismatch"
    assert records["bad-type"].integrity == "forbidden"
    assert records["bad-extension"].integrity == "forbidden"


def test_provenance_manifest_entry_limit_is_bounded(tmp_path):
    report = tmp_path / "report"
    report.mkdir()
    (report / "report-manifest.json").write_text(json.dumps({"artifacts": [{}] * 100_001}), encoding="utf-8")
    snapshot = ArtifactResolver(report).manifest_snapshot()
    assert snapshot["report"]["availability"] == "invalid"
    assert snapshot["report"]["warnings"] == ["MANIFEST_ENTRY_LIMIT_REACHED"]


def test_report_status_distinguishes_invalid_manifest(tmp_path):
    db = tmp_path / "runs.db"
    report = tmp_path / "report"
    report.mkdir()
    (report / "report-manifest.json").write_text("not-json", encoding="utf-8")
    make_db(db)
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE runs SET output_dir = ? WHERE id = 1", (str(report),))
    item = SQLiteReportRepository(db).get_report(1)
    assert item.artifact_availability == "PARTIAL"
    assert item.manifest_status == "INVALID"


def test_report_manifest_registers_html_or_pdf_artifact(tmp_path):
    report = tmp_path / "report"
    report.mkdir()
    html = report / "demo_report.html"
    html.write_text("<html>fixture</html>", encoding="utf-8")
    digest = hashlib.sha256(html.read_bytes()).hexdigest()
    (report / "artifact-manifest.json").write_text('{"artifacts": []}', encoding="utf-8")
    (report / "report-manifest.json").write_text(
        json.dumps({"artifacts": [{"artifact": html.name, "role": "report", "path": html.name, "sha256": digest, "size": html.stat().st_size}]}),
        encoding="utf-8",
    )
    records = ArtifactResolver(report).records()
    assert len(records) == 1
    assert records[0].artifact_id == html.name
    assert records[0].integrity == "verified"


def test_symlinked_output_directory_is_forbidden(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (real / "artifact-manifest.json").write_text('{"artifacts": []}', encoding="utf-8")
    linked = tmp_path / "linked"
    linked.symlink_to(real, target_is_directory=True)
    resolver = ArtifactResolver(linked, trusted_roots=[tmp_path])
    assert resolver.records() == []
    assert resolver.manifest_snapshot()["artifact"]["availability"] == "forbidden"
