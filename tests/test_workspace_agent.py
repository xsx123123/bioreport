import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from bioreport.ai.evidence import EvidenceBuilder
from bioreport.ai.interpreter import InterpretationOrchestrator
from bioreport.ai.persistence import InterpretationRepository
from bioreport.db.migrations import migrate_workspace, restore_workspace_backup


def make_runs_db(path):
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE runs (id INTEGER PRIMARY KEY, project_id TEXT, run_at TEXT, engine_version TEXT, pipeline_version TEXT, layout TEXT, output_format TEXT, modules TEXT, config_path TEXT, output_dir TEXT, status TEXT, input_checksums TEXT, created_at TEXT)")
    connection.execute("INSERT INTO runs VALUES (1,'demo','2026-10-17','2','p1','single','[]','[]','','','success','{}','now')")
    connection.commit()
    connection.close()


def test_deg_evidence_and_mock_interpretation_are_consistent(tmp_path):
    source = tmp_path / "2_vs_1_DEG.csv"
    source.write_text("Gene,log2FoldChange,pvalue,padj\nA,2,.01,.02\nB,-2,.01,.03\nC,4,.2,.4\n", encoding="utf-8")
    evidence = EvidenceBuilder(tmp_path).build_deg(project_id="demo", comparison="2_vs_1", run_id=1)
    assert evidence.statistics["up"] == 1
    assert evidence.statistics["down"] == 1
    result = InterpretationOrchestrator().interpret(evidence.to_dict())
    assert result.validation.valid is True
    assert result.output["module_id"] == "rna.results.deg"


def test_invalid_numeric_claim_is_rejected(tmp_path):
    source = tmp_path / "2_vs_1_DEG.csv"
    source.write_text("Gene,log2FoldChange,pvalue,padj\nA,2,.01,.02\n", encoding="utf-8")
    evidence = EvidenceBuilder(tmp_path).build_deg(project_id="demo", comparison="2_vs_1")
    result = InterpretationOrchestrator().interpret(evidence.to_dict(), generator=lambda _: {"module_id": "rna.results.deg", "comparison": "2_vs_1", "observations": [{"text": "999 genes", "evidence_refs": ["source:deg_2_vs_1"]}], "interpretations": [], "hypotheses": [], "limitations": []})
    assert result.validation.valid is False
    assert "UNSUPPORTED_NUMERIC_CLAIM" in result.validation.errors


def test_numeric_claim_in_summary_is_rejected(tmp_path):
    source = tmp_path / "2_vs_1_DEG.csv"
    source.write_text("Gene,log2FoldChange,pvalue,padj\nA,2,.01,.02\n", encoding="utf-8")
    evidence = EvidenceBuilder(tmp_path).build_deg(project_id="demo", comparison="2_vs_1")
    result = InterpretationOrchestrator().interpret(
        evidence.to_dict(),
        generator=lambda _: {
            "module_id": "rna.results.deg", "comparison": "2_vs_1",
            "observations": [], "interpretations": [], "hypotheses": [],
            "limitations": [], "summary": "999 genes were measured.",
        },
    )
    assert result.validation.valid is False
    assert "UNSUPPORTED_NUMERIC_CLAIM" in result.validation.errors


def test_registered_non_deg_evidence_gets_a_matching_draft_reference(tmp_path):
    source = tmp_path / "enrichment.csv"
    source.write_text("term,pvalue\npathway-a,0.01\n", encoding="utf-8")
    evidence = EvidenceBuilder(tmp_path).build_registered(project_id="demo", module_id="rna.results.enrichment")
    result = InterpretationOrchestrator().interpret(evidence.to_dict())
    assert result.validation.valid is True
    assert result.output["observations"][0]["evidence_refs"] == ["source:rna.results.enrichment:preview"]


def test_prompt_injection_markup_is_rejected(tmp_path):
    source = tmp_path / "2_vs_1_DEG.csv"
    source.write_text("Gene,log2FoldChange,pvalue,padj\nA,2,.01,.02\n", encoding="utf-8")
    evidence = EvidenceBuilder(tmp_path).build_deg(project_id="demo", comparison="2_vs_1")
    result = InterpretationOrchestrator().interpret(evidence.to_dict(), generator=lambda _: {"module_id": "rna.results.deg", "comparison": "2_vs_1", "observations": [{"text": "<script>alert(1)</script>", "evidence_refs": ["source:deg_2_vs_1"]}], "interpretations": [], "hypotheses": [], "limitations": [], "summary": "safe"})
    assert result.validation.valid is False
    assert "UNSAFE_MARKUP" in result.validation.errors


def test_malformed_evidence_reference_is_rejected(tmp_path):
    source = tmp_path / "2_vs_1_DEG.csv"
    source.write_text("Gene,log2FoldChange,pvalue,padj\nA,2,.01,.02\n", encoding="utf-8")
    evidence = EvidenceBuilder(tmp_path).build_deg(project_id="demo", comparison="2_vs_1")
    result = InterpretationOrchestrator().interpret(
        evidence.to_dict(),
        generator=lambda _: {
            "module_id": "rna.results.deg", "comparison": "2_vs_1",
            "observations": [{"text": "A finding", "evidence_refs": [None]}],
            "interpretations": [], "hypotheses": [], "limitations": [], "summary": "safe",
        },
    )
    assert result.validation.valid is False
    assert "UNKNOWN_EVIDENCE_REF" in result.validation.errors


def test_interpretation_and_chat_text_redact_local_paths(tmp_path):
    source = tmp_path / "2_vs_1_DEG.csv"
    source.write_text("Gene,log2FoldChange,pvalue,padj\nA,2,.01,.02\n", encoding="utf-8")
    evidence = EvidenceBuilder(tmp_path).build_deg(project_id="demo", comparison="2_vs_1")
    result = InterpretationOrchestrator().interpret(
        evidence.to_dict(),
        generator=lambda _: {
            "module_id": "rna.results.deg", "comparison": "2_vs_1",
            "observations": [{"text": "See /home/user/private/result.csv", "evidence_refs": ["source:deg_2_vs_1"]}],
            "interpretations": [], "hypotheses": [], "limitations": [], "summary": "ok",
        },
    )
    assert "private" not in result.output["observations"][0]["text"]


def test_migration_backup_and_interpretation_round_trip(tmp_path):
    db = tmp_path / "runs.db"
    make_runs_db(db)
    backup = migrate_workspace(db)
    assert backup and backup.is_file()
    repository = InterpretationRepository(db)
    interpretation_id = repository.save_interpretation(run_id=1, project_id="demo", module_id="rna.results.deg", evidence_hash="abc", output={"summary": "ok"}, validation={"valid": True}, provider="mock", model="deterministic-v1")
    second_id = repository.save_interpretation(run_id=1, project_id="demo", module_id="rna.results.deg", comparison="2_vs_1", evidence_hash="abc", output={"summary": "second"}, validation={"valid": True}, provider="mock", model="deterministic-v1")
    loaded = repository.get_interpretation(interpretation_id)
    assert loaded["status"] == "validated"
    assert loaded["output"] == {"summary": "ok"}
    assert loaded["output_hash"]
    assert repository.get_interpretation(second_id)["version"] == 1
    assert any(item["id"] == second_id and item["comparison"] == "2_vs_1" for item in repository.list_interpretations(run_id=1))
    third_id = repository.save_interpretation(run_id=1, project_id="demo", module_id="rna.results.deg", comparison="2_vs_1", evidence_hash="abc", output={"summary": "third"}, validation={"valid": True}, provider="mock", model="deterministic-v1")
    assert repository.get_interpretation(third_id)["version"] == 2
    session_id = repository.create_session(run_id=1, module_id="rna.results.deg", evidence_hash="abc")
    repository.add_message(session_id, role="user", content="See /tmp/private/result.csv")
    assert "private" not in repository.get_session(session_id)["messages"][0]["content"]
    execution_id = repository.create_execution(project_id="demo")
    assert repository.get_execution(execution_id)["run_id"] is None
    staged_id = repository.save_interpretation(execution_id=execution_id, project_id="demo", module_id="rna.results.deg", comparison="2_vs_1", evidence_hash="staged", output={"summary": "staged"}, validation={"valid": True}, provider="mock", model="deterministic-v1")
    assert repository.get_interpretation(staged_id)["run_id"] is None
    existing_id = repository.save_interpretation(run_id=1, project_id="demo", module_id="rna.results.deg", comparison="2_vs_1", evidence_hash="existing", output={"summary": "existing"}, validation={"valid": True}, provider="mock", model="deterministic-v1")
    repository.bind_execution(execution_id, run_id=1)
    assert repository.get_execution(execution_id)["status"] == "completed"
    assert repository.get_interpretation(staged_id)["run_id"] == 1
    assert repository.get_interpretation(staged_id)["version"] == 4
    assert repository.get_interpretation(existing_id)["version"] == 3
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT value FROM schema_meta WHERE key='workspace_schema_version'").fetchone()[0] == "2"
    restore_workspace_backup(db)
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1


def test_interpretation_versions_are_serialized_under_concurrent_writes(tmp_path):
    db = tmp_path / "runs.db"
    make_runs_db(db)
    migrate_workspace(db)

    def save(index):
        return InterpretationRepository(db).save_interpretation(
            run_id=1,
            project_id="demo",
            module_id="rna.results.deg",
            comparison="2_vs_1",
            evidence_hash="abc",
            output={"summary": str(index)},
            validation={"valid": True},
            provider="mock",
            model="deterministic-v1",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(save, (1, 2)))
    versions = [item["version"] for item in InterpretationRepository(db).list_interpretations(run_id=1)]
    assert sorted(versions) == [1, 2]


def test_migration_is_idempotent_and_keeps_v1_interpretations(tmp_path):
    db = tmp_path / "legacy.db"
    make_runs_db(db)
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE interpretations (id TEXT PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES runs(id), project_id TEXT NOT NULL, module_id TEXT NOT NULL, comparison TEXT, version INTEGER NOT NULL DEFAULT 1, evidence_hash TEXT NOT NULL, output_hash TEXT NOT NULL DEFAULT '', provider TEXT NOT NULL, model TEXT NOT NULL, prompt_version TEXT NOT NULL, validator_version TEXT NOT NULL DEFAULT 'v1', output_json TEXT NOT NULL, validation_json TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL)")
        connection.execute("INSERT INTO interpretations VALUES ('legacy',1,'demo','rna.results.deg',NULL,1,'hash','','mock','model','v1','v1','{}','{\"valid\":true}','validated','now')")
    migrate_workspace(db)
    migrate_workspace(db)
    with sqlite3.connect(db) as connection:
        columns = {row[1]: row for row in connection.execute("PRAGMA table_info(interpretations)")}
        assert columns["run_id"][3] == 0
        assert "execution_id" in columns
        assert connection.execute("SELECT id FROM interpretations").fetchone()[0] == "legacy"


def test_repeated_migration_preserves_original_rollback_snapshot(tmp_path):
    db = tmp_path / "runs.db"
    make_runs_db(db)
    original_backup = migrate_workspace(db)
    migrate_workspace(db)
    restore_workspace_backup(db)
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_meta'").fetchone() is None
        assert connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1
    assert original_backup and original_backup.is_file()


def test_execution_binding_enforces_existing_run_foreign_key(tmp_path):
    db = tmp_path / "runs.db"
    make_runs_db(db)
    migrate_workspace(db)
    repository = InterpretationRepository(db)
    execution_id = repository.create_execution(project_id="demo")
    with pytest.raises(sqlite3.IntegrityError):
        repository.bind_execution(execution_id, run_id=999)
    assert repository.get_execution(execution_id)["run_id"] is None
