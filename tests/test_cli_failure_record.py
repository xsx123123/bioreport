import pytest
import sys

from bioreport import cli
from bioreport.ai.persistence import InterpretationRepository
from bioreport.db.migrations import migrate_workspace
from bioreport.utils.run_db import record_run


def test_ai_failure_is_recorded_before_cli_exits(tmp_path, monkeypatch):
    source_template = tmp_path / "templates"
    (source_template / "shared").mkdir(parents=True)
    config = {
        "_config_path": str(tmp_path / "report.json"),
        "project": {"project_id": "demo"},
        "report": {"layout": "single", "output_format": "html"},
    }
    statuses = []
    monkeypatch.setattr(cli, "print_banner", lambda: None)
    monkeypatch.setattr(cli, "setup_logging", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli, "load_config_with_fallback", lambda _: config)
    monkeypatch.setattr(cli, "selected_modules", lambda _: ["ai"])
    monkeypatch.setattr(cli, "output_formats", lambda _: ["html"])
    monkeypatch.setattr(cli, "resolve_template_candidates", lambda: [source_template])
    monkeypatch.setattr(cli, "build_provenance", lambda *_: {"output_format": ["html"], "rendered_modules": ["ai"], "generated_at": "now", "input_checksums": {}})
    monkeypatch.setattr(cli, "write_provenance", lambda *_: tmp_path / "provenance.json")
    monkeypatch.setattr(cli, "check_input_files", lambda *_: None)
    monkeypatch.setattr(cli, "print_task_overview", lambda *_: None)
    monkeypatch.setattr(cli, "check_quarto_env", lambda: None)
    monkeypatch.setattr(cli, "render_templates", lambda *_: None)
    monkeypatch.setattr(cli, "run_ai_pipeline", lambda *_: (_ for _ in ()).throw(RuntimeError("AI failed")))
    monkeypatch.setattr(cli, "render_report", lambda *_: None)
    monkeypatch.setattr(cli, "record_run", lambda *args, **kwargs: statuses.append(kwargs["status"]) or 1)
    monkeypatch.setattr(cli, "default_db_path", lambda: tmp_path / "runs.db")
    monkeypatch.setattr(sys, "argv", ["bioreport", "run", "-c", str(tmp_path / "report.json"), "-o", str(tmp_path / "output")])

    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 1
    assert statuses == ["failed"]


def test_workspace_execution_is_bound_after_legacy_run_row(tmp_path, monkeypatch):
    db_path = tmp_path / "runs.db"
    record_run(
        db_path,
        project_id="demo",
        provenance={"generated_at": "now", "output_format": ["html"], "rendered_modules": []},
        config_path="report.json",
        output_dir=str(tmp_path),
        status="success",
    )
    migrate_workspace(db_path)
    monkeypatch.setattr(cli, "default_db_path", lambda: db_path)

    execution = cli._workspace_execution("demo")
    assert execution is not None
    repository, execution_id = execution
    assert repository.get_execution(execution_id)["run_id"] is None

    cli._finish_workspace_execution(execution, run_id=1, status="completed")
    bound = InterpretationRepository(db_path).get_execution(execution_id)
    assert bound["run_id"] == 1
    assert bound["status"] == "completed"


def test_workspace_migration_commands_are_explicit_and_reversible(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "runs.db"
    record_run(
        db_path,
        project_id="demo",
        provenance={"generated_at": "now", "output_format": ["html"], "rendered_modules": []},
        config_path="report.json",
        output_dir=str(tmp_path),
        status="success",
    )
    monkeypatch.setattr(sys, "argv", ["bioreport", "workspace-migrate", "--db", str(db_path)])
    cli.main()
    assert (tmp_path / "runs.db.bak").is_file()

    monkeypatch.setattr(sys, "argv", ["bioreport", "workspace-restore", "--db", str(db_path)])
    cli.main()
    assert "Workspace 迁移备份已恢复" in capsys.readouterr().out
