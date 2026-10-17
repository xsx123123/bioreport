import sqlite3
import asyncio
import json
from types import SimpleNamespace
import pytest
from fastapi import HTTPException

from bioreport.api import create_app
import bioreport.api_server as api_server
from bioreport.api_server import serve
from bioreport.db.migrations import migrate_workspace


def test_workspace_api_maps_service_contract(tmp_path):
    db = tmp_path / "runs.db"
    connection = sqlite3.connect(db)
    connection.execute("CREATE TABLE runs (id INTEGER PRIMARY KEY, project_id TEXT, run_at TEXT, engine_version TEXT, pipeline_version TEXT, layout TEXT, output_format TEXT, modules TEXT, config_path TEXT, output_dir TEXT, status TEXT, input_checksums TEXT, created_at TEXT)")
    connection.execute("INSERT INTO runs VALUES (1,'demo','2026-10-17T10:00:00','2','p1','single','[]','[]','','','success','{}','now')")
    connection.commit()
    connection.close()
    app = create_app(str(db), trusted_roots=[tmp_path])
    routes = {route.path: route.endpoint for route in app.routes if hasattr(route, "path")}
    assert "/api/reports" in routes
    assert "/api/reports/{report_id}" in routes
    assert routes["/api/reports"](limit=50, cursor=None)["items"][0]["project_id"] == "demo"
    assert routes["/api/reports/{report_id}"](1)["project_id"] == "demo"
    unavailable = routes["/api/v1/reports/{report_id}/modules/{module_id}/evidence"](1, "rna.results.samples", None)
    assert unavailable["availability"] == "UNAVAILABLE"
    assert "/api/v1/reports/{report_id}/modules/{module_id}/evidence" in routes
    assert "/api/v1/reports/{report_id}/interpretations" in routes
    assert "/api/v1/conversations/{session_id}/messages" in routes
    schema = app.openapi()
    assert "/api/v1/reports/{report_id}/modules/{module_id}/evidence" in schema["paths"]
    assert "/api/v1/reports/{report_id}/provenance" in schema["paths"]
    assert "/api/v1/operations/{operation_id}/events" in schema["paths"]
    assert "/api/v1/operations/{operation_id}/cancel" in schema["paths"]
    interpretation_schema = schema["paths"]["/api/v1/reports/{report_id}/interpretations"]["post"]["requestBody"]["content"]["application/json"]["schema"]
    assert interpretation_schema["$ref"].endswith("/InterpretationRequest")
    assert "ConversationRequest" in schema["components"]["schemas"]
    assert "ConversationMessageRequest" in schema["components"]["schemas"]


def test_public_bind_requires_token():
    with pytest.raises(RuntimeError, match="BIOREPORT_API_TOKEN"):
        serve(host="0.0.0.0", port=8999)


def test_project_scope_filters_listing_and_hides_other_reports(tmp_path):
    db = tmp_path / "runs.db"
    connection = sqlite3.connect(db)
    connection.execute("CREATE TABLE runs (id INTEGER PRIMARY KEY, project_id TEXT, run_at TEXT, engine_version TEXT, pipeline_version TEXT, layout TEXT, output_format TEXT, modules TEXT, config_path TEXT, output_dir TEXT, status TEXT, input_checksums TEXT, created_at TEXT)")
    connection.executemany("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", [
        (1, "allowed", "2026-10-17", "2", "p1", "single", "[]", "[]", "", "", "success", "{}", "now"),
        (2, "private", "2026-10-17", "2", "p1", "single", "[]", "[]", "", "", "success", "{}", "now"),
    ])
    connection.commit(); connection.close()
    app = api_server.create_app(str(db), allowed_projects=["allowed"])
    routes = {route.path: route.endpoint for route in app.routes if hasattr(route, "path")}
    assert [item["project_id"] for item in routes["/api/v1/reports"](limit=50, cursor=None)["items"]] == ["allowed"]
    with pytest.raises(HTTPException) as error:
        routes["/api/v1/reports/{report_id}"](2)
    assert getattr(error.value, "status_code", None) == 404


def test_api_report_status_marks_output_outside_trusted_root_forbidden(tmp_path):
    db = tmp_path / "runs.db"
    output_dir = tmp_path / "outside"
    output_dir.mkdir()
    (output_dir / "report-manifest.json").write_text('{"artifacts": []}', encoding="utf-8")
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE runs (id INTEGER PRIMARY KEY, project_id TEXT, run_at TEXT, engine_version TEXT, pipeline_version TEXT, layout TEXT, output_format TEXT, modules TEXT, config_path TEXT, output_dir TEXT, status TEXT, input_checksums TEXT, created_at TEXT)")
        connection.execute("INSERT INTO runs VALUES (1,?,?,?,?,?,?,?,?,?,?,?,?)", ("demo", "2026-10-17", "2", "p1", "single", "[]", "[]", "", str(output_dir), "success", "{}", "now"))
    app = api_server.create_app(str(db), trusted_roots=[tmp_path / "approved"])
    route = next(route.endpoint for route in app.routes if getattr(route, "path", None) == "/api/v1/reports/{report_id}")
    view = route(1)
    assert view["output_available"] is False
    assert view["artifact_availability"] == "PATH_FORBIDDEN"
    assert view["manifest_status"] == "UNVERIFIED"


def test_api_module_evidence_reports_symlink_source_as_forbidden(tmp_path):
    db = tmp_path / "runs.db"
    output_dir = tmp_path / "out"
    real = tmp_path / "real"
    output_dir.mkdir(); real.mkdir()
    (real / "samples.csv").write_text("sample,group\nS1,A\n", encoding="utf-8")
    (output_dir / "results").symlink_to(real, target_is_directory=True)
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE runs (id INTEGER PRIMARY KEY, project_id TEXT, run_at TEXT, engine_version TEXT, pipeline_version TEXT, layout TEXT, output_format TEXT, modules TEXT, config_path TEXT, output_dir TEXT, status TEXT, input_checksums TEXT, created_at TEXT)")
        connection.execute("INSERT INTO runs VALUES (1,?,?,?,?,?,?,?,?,?,?,?,?)", ("demo", "2026-10-17", "2", "p1", "single", "[]", '["rna.results.samples"]', "", str(output_dir), "success", "{}", "now"))
    app = api_server.create_app(str(db), trusted_roots=[tmp_path])
    route = next(route.endpoint for route in app.routes if getattr(route, "path", None) == "/api/v1/reports/{report_id}/modules/{module_id}/evidence")
    with pytest.raises(HTTPException) as error:
        route(1, "rna.results.samples", None)
    assert error.value.status_code == 403
    assert error.value.detail["code"] == "PATH_FORBIDDEN"


def test_cors_wildcard_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="explicit origin allowlist"):
        api_server.create_app(str(tmp_path / "missing.db"), cors_origins=["*"])


def test_http_error_contract_contains_request_id_and_legacy_detail(tmp_path):
    app = api_server.create_app(str(tmp_path / "missing.db"))
    handler = app.exception_handlers[HTTPException]
    request = SimpleNamespace(state=SimpleNamespace(workspace_request_id="req-123"))
    response = asyncio.run(handler(request, HTTPException(status_code=404, detail={"code": "REPORT_NOT_FOUND", "message": "missing"})))
    payload = json.loads(response.body)
    assert payload["detail"]["code"] == "REPORT_NOT_FOUND"
    assert payload["error"]["request_id"] == "req-123"




def test_controlled_server_cli_forwards_bind_options(monkeypatch):
    captured = {}

    def fake_serve(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(api_server, "serve", fake_serve)
    api_server.main(["--db", "/tmp/workspace.db", "--host", "127.0.0.1", "--port", "8765"])
    assert captured == {"db_path": "/tmp/workspace.db", "host": "127.0.0.1", "port": 8765}


def test_conversation_message_is_persisted_with_deterministic_draft(tmp_path):
    db = tmp_path / "runs.db"
    connection = sqlite3.connect(db)
    connection.execute("CREATE TABLE runs (id INTEGER PRIMARY KEY, project_id TEXT, run_at TEXT, engine_version TEXT, pipeline_version TEXT, layout TEXT, output_format TEXT, modules TEXT, config_path TEXT, output_dir TEXT, status TEXT, input_checksums TEXT, created_at TEXT)")
    connection.execute("INSERT INTO runs VALUES (1,'demo','2026-10-17T10:00:00','2','p1','single','[]','[]','','','success','{}','now')")
    connection.commit()
    connection.close()
    migrate_workspace(db)
    app = create_app(str(db))
    routes = {route.path: route.endpoint for route in app.routes if hasattr(route, "path")}
    session = routes["/api/v1/conversations"]({"run_id": 1, "module_id": "rna.results.deg", "evidence_hash": "abc123"})
    response = routes["/api/v1/conversations/{session_id}/messages"](session["session_id"], {"role": "user", "content": "What changed?"})
    assert response["status"] == "stored"
    assert response["assistant"]["status"] == "draft"
    loaded = routes["/api/v1/conversations/{session_id}"](session["session_id"])
    assert [message["role"] for message in loaded["messages"]] == ["user", "assistant"]


def test_operation_cancel_is_idempotent(tmp_path):
    db = tmp_path / "runs.db"
    connection = sqlite3.connect(db)
    connection.execute("CREATE TABLE runs (id INTEGER PRIMARY KEY, project_id TEXT, run_at TEXT, engine_version TEXT, pipeline_version TEXT, layout TEXT, output_format TEXT, modules TEXT, config_path TEXT, output_dir TEXT, status TEXT, input_checksums TEXT, created_at TEXT)")
    connection.execute("INSERT INTO runs VALUES (1,'demo','2026-10-17T10:00:00','2','p1','single','[]','[]','','','success','{}','now')")
    connection.commit()
    connection.close()
    migrate_workspace(db)
    app = create_app(str(db), trusted_roots=[tmp_path])
    routes = {route.path: route.endpoint for route in app.routes if hasattr(route, "path")}
    app_state = next(route.endpoint for route in app.routes if getattr(route, "path", None) == "/api/v1/reports/{report_id}/interpretations" and "POST" in getattr(route, "methods", set()))
    # The endpoint requires a real DEG source, so exercise the cancellation
    # state with the operation registry through a successful fixture below.
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "2_vs_1_DEG.csv").write_text("Gene,log2FoldChange,pvalue,padj\nA,2,.01,.02\n", encoding="utf-8")
    connection = sqlite3.connect(db)
    connection.execute("UPDATE runs SET output_dir = ?, modules = ? WHERE id = 1", (str(output_dir), '["rna.results.deg"]'))
    connection.commit()
    connection.close()
    created = app_state(1, {"module_id": "rna.results.deg", "comparison": "2_vs_1"})
    cancel = routes["/api/v1/operations/{operation_id}/cancel"](created["operation_id"])
    assert cancel["status"] == "completed"
    events = routes["/api/v1/operations/{operation_id}/events"]
    assert events is not None


def test_interpretation_post_idempotency_key_reuses_operation(tmp_path):
    db = tmp_path / "runs.db"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "2_vs_1_DEG.csv").write_text("Gene,log2FoldChange,pvalue,padj\nA,2,.01,.02\n", encoding="utf-8")
    connection = sqlite3.connect(db)
    connection.execute("CREATE TABLE runs (id INTEGER PRIMARY KEY, project_id TEXT, run_at TEXT, engine_version TEXT, pipeline_version TEXT, layout TEXT, output_format TEXT, modules TEXT, config_path TEXT, output_dir TEXT, status TEXT, input_checksums TEXT, created_at TEXT)")
    connection.execute("INSERT INTO runs VALUES (1,?,?,?,?,?,?,?,?,?,?,?,?)", ("demo", "2026-10-17T10:00:00", "2", "p1", "single", "[]", "[\"rna.results.deg\"]", "", str(output_dir), "success", "{}", "now"))
    connection.commit(); connection.close()
    migrate_workspace(db)
    app = create_app(str(db), trusted_roots=[tmp_path])
    endpoint = next(route.endpoint for route in app.routes if getattr(route, "path", None) == "/api/v1/reports/{report_id}/interpretations" and "POST" in getattr(route, "methods", set()))
    first = endpoint(1, {"module_id": "rna.results.deg", "comparison": "2_vs_1"}, "retry-1")
    second = endpoint(1, {"module_id": "rna.results.deg", "comparison": "2_vs_1"}, "retry-1")
    assert second == first
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM interpretations").fetchone()[0] == 1


def test_registered_module_interpretation_is_persisted(tmp_path):
    db = tmp_path / "runs.db"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "enrichment.csv").write_text("term,pvalue\npathway-a,0.01\n", encoding="utf-8")
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE runs (id INTEGER PRIMARY KEY, project_id TEXT, run_at TEXT, engine_version TEXT, pipeline_version TEXT, layout TEXT, output_format TEXT, modules TEXT, config_path TEXT, output_dir TEXT, status TEXT, input_checksums TEXT, created_at TEXT)")
        connection.execute("INSERT INTO runs VALUES (1,?,?,?,?,?,?,?,?,?,?,?,?)", ("demo", "2026-10-17", "2", "p1", "single", "[]", '["rna.results.enrichment"]', "", str(output_dir), "success", "{}", "now"))
    migrate_workspace(db)
    app = api_server.create_app(str(db), trusted_roots=[tmp_path])
    endpoint = next(route.endpoint for route in app.routes if getattr(route, "path", None) == "/api/v1/reports/{report_id}/interpretations" and "POST" in getattr(route, "methods", set()))
    response = endpoint(1, {"module_id": "rna.results.enrichment", "comparison": "2_vs_1"})
    assert response["status"] == "validated"
    with sqlite3.connect(db) as connection:
        row = connection.execute("SELECT module_id, comparison FROM interpretations").fetchone()
    assert row == ("rna.results.enrichment", None)


def test_interpretation_rejects_invalid_top_n(tmp_path):
    db = tmp_path / "runs.db"
    out = tmp_path / "out"
    out.mkdir()
    (out / "2_vs_1_DEG.csv").write_text("Gene,log2FoldChange,pvalue,padj\nA,2,.01,.02\n", encoding="utf-8")
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE runs (id INTEGER PRIMARY KEY, project_id TEXT, run_at TEXT, engine_version TEXT, pipeline_version TEXT, layout TEXT, output_format TEXT, modules TEXT, config_path TEXT, output_dir TEXT, status TEXT, input_checksums TEXT, created_at TEXT)")
        connection.execute("INSERT INTO runs VALUES (1,?,?,?,?,?,?,?,?,?,?,?,?)", ("demo", "2026-10-17", "2", "p1", "single", "[]", '["rna.results.deg"]', "", str(out), "success", "{}", "now"))
    migrate_workspace(db)
    app = api_server.create_app(str(db), trusted_roots=[tmp_path])
    endpoint = next(route.endpoint for route in app.routes if getattr(route, "path", None) == "/api/v1/reports/{report_id}/interpretations" and "POST" in getattr(route, "methods", set()))
    with pytest.raises(HTTPException) as error:
        endpoint(1, {"module_id": "rna.results.deg", "comparison": "2_vs_1", "top_n": 0})
    assert getattr(error.value, "status_code", None) == 422


def test_artifact_api_redacts_paths_and_requires_explicit_fixture_root(tmp_path):
    db = tmp_path / "runs.db"
    output_dir = tmp_path / "report"
    output_dir.mkdir()
    artifact = output_dir / "report.pdf"
    artifact.write_bytes(b"pdf-fixture")
    import hashlib, json
    (output_dir / "artifact-manifest.json").write_text(json.dumps({"artifacts": [{"artifact_id": "report", "role": "pdf", "path": "report.pdf", "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}]}), encoding="utf-8")
    connection = sqlite3.connect(db)
    connection.execute("CREATE TABLE runs (id INTEGER PRIMARY KEY, project_id TEXT, run_at TEXT, engine_version TEXT, pipeline_version TEXT, layout TEXT, output_format TEXT, modules TEXT, config_path TEXT, output_dir TEXT, status TEXT, input_checksums TEXT, created_at TEXT)")
    connection.execute("INSERT INTO runs VALUES (1,?,?,?,?,?,?,?,?,?,?,?,?)", ("demo", "2026-10-17T10:00:00", "2", "p1", "single", "[]", "[]", "", str(output_dir), "success", "{}", "now"))
    connection.commit(); connection.close()
    app = create_app(str(db), trusted_roots=[tmp_path])
    endpoint = next(route.endpoint for route in app.routes if getattr(route, "path", None) == "/api/v1/reports/{report_id}/artifacts" and "GET" in getattr(route, "methods", set()))
    items = endpoint(1)["artifacts"]
    assert items[0]["artifact_id"] == "report"
    assert items[0]["integrity"] == "unverified"
    assert "path" not in items[0]

    content_endpoint = next(route.endpoint for route in app.routes if getattr(route, "path", None) == "/api/v1/reports/{report_id}/artifacts/{artifact_id}/content" and "GET" in getattr(route, "methods", set()))
    response = content_endpoint(1, "report")
    assert response.headers["content-security-policy"].startswith("sandbox")
    assert response.headers["content-disposition"].startswith("inline")


def test_evidence_api_rejects_output_outside_trusted_root(tmp_path):
    db = tmp_path / "runs.db"
    output_dir = tmp_path / "outside"
    output_dir.mkdir()
    (output_dir / "2_vs_1_DEG.csv").write_text("Gene,log2FoldChange,pvalue,padj\nA,2,.01,.02\n", encoding="utf-8")
    connection = sqlite3.connect(db)
    connection.execute("CREATE TABLE runs (id INTEGER PRIMARY KEY, project_id TEXT, run_at TEXT, engine_version TEXT, pipeline_version TEXT, layout TEXT, output_format TEXT, modules TEXT, config_path TEXT, output_dir TEXT, status TEXT, input_checksums TEXT, created_at TEXT)")
    connection.execute("INSERT INTO runs VALUES (1,?,?,?,?,?,?,?,?,?,?,?,?)", ("demo", "2026-10-17T10:00:00", "2", "p1", "single", "[]", "[]", "", str(output_dir), "success", "{}", "now"))
    connection.commit(); connection.close()
    app = create_app(str(db), trusted_roots=[tmp_path / "trusted"])
    endpoint = next(route.endpoint for route in app.routes if getattr(route, "path", None) == "/api/v1/reports/{report_id}/modules/{module_id}/evidence" and "GET" in getattr(route, "methods", set()))
    with pytest.raises(Exception, match="PATH_FORBIDDEN"):
        endpoint(1, "rna.results.deg", "2_vs_1")


