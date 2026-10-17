"""Optional FastAPI adapter for the read-only Workspace report service."""

from __future__ import annotations

import sqlite3
import hmac
import json
import os
import re
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any, Iterable

from .artifacts import ArtifactResolver, ArtifactError
from .ai.evidence import EvidenceBuilder
from .ai.interpreter import InterpretationOrchestrator
from .ai.persistence import InterpretationRepository
from .sse import operation_events
from .report_service import DatabaseUnavailable, ReportNotFound, ReportServiceError, SQLiteReportRepository

try:  # FastAPI remains optional for the CLI/report-generation installation.
    from fastapi import Body, FastAPI, Header, HTTPException, Query, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
    from pydantic import BaseModel, Field
except ImportError:  # pragma: no cover - exercised only in minimal installs
    FastAPI = None  # type: ignore[assignment]

    class BaseModel:  # type: ignore[no-redef]
        pass

    def Field(default: Any = None, **_: Any) -> Any:  # type: ignore[no-redef]
        return default


class InterpretationRequest(BaseModel):
    module_id: str = Field(min_length=1, max_length=160)
    comparison: str | None = Field(default=None, max_length=160)
    top_n: int = Field(default=10, ge=1, le=100)


class ConversationRequest(BaseModel):
    run_id: int
    module_id: str | None = Field(default=None, max_length=160)
    evidence_hash: str | None = Field(default=None, max_length=128)


class ConversationMessageRequest(BaseModel):
    role: str
    content: str = Field(min_length=1, max_length=100_000)


def _dto_data(value: Any) -> dict[str, Any]:
    """Accept FastAPI's validated model and the direct-call test adapter."""
    if isinstance(value, dict):
        return value
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return dump()
    return dict(value)


def create_app(
    db_path: str,
    *,
    trusted_roots: list[str] | None = None,
    api_token: str | None = None,
    allowed_projects: Iterable[str] | None = None,
    rate_limit_per_minute: int | None = None,
    cors_origins: Iterable[str] | None = None,
) -> Any:
    if FastAPI is None:
        raise RuntimeError("FastAPI is required for the Workspace API; install the web extra")

    app = FastAPI(title="BioReport Workspace API", version="1")
    repository = SQLiteReportRepository(db_path)
    interpretations = InterpretationRepository(db_path)
    operations: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    idempotent_interpretations: dict[tuple[int, str], tuple[str, dict[str, Any]]] = {}
    required_token = api_token if api_token is not None else os.environ.get("BIOREPORT_API_TOKEN")
    configured_projects = allowed_projects
    if configured_projects is None and os.environ.get("BIOREPORT_ALLOWED_PROJECTS") is not None:
        configured_projects = os.environ.get("BIOREPORT_ALLOWED_PROJECTS", "").split(",")
    project_scope = frozenset(str(value).strip() for value in (configured_projects or ()) if str(value).strip())
    if rate_limit_per_minute is None:
        raw_rate_limit = os.environ.get("BIOREPORT_RATE_LIMIT_PER_MINUTE")
        rate_limit_per_minute = int(raw_rate_limit) if raw_rate_limit else 0
    rate_limit_per_minute = max(0, int(rate_limit_per_minute))
    request_windows: dict[str, deque[float]] = {}
    if cors_origins is None:
        raw_origins = os.environ.get("BIOREPORT_CORS_ORIGINS", "")
        cors_origins = [item.strip() for item in raw_origins.split(",") if item.strip()]
    if cors_origins:
        if "*" in cors_origins:
            raise ValueError("BIOREPORT_CORS_ORIGINS must be an explicit origin allowlist")
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(cors_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
        )

    @app.exception_handler(HTTPException)
    async def workspace_http_error(request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, dict) else {"code": "HTTP_ERROR", "message": str(exc.detail)}
        error = dict(detail)
        error.setdefault("request_id", getattr(request.state, "workspace_request_id", "unknown"))
        # Keep `detail` for the existing local frontend while exposing the
        # stable contract under `error` for integrations.
        return JSONResponse(status_code=exc.status_code, content={"detail": detail, "error": error}, headers=exc.headers or {})

    @app.exception_handler(Exception)
    async def workspace_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "workspace_request_id", "unknown")
        error = {"code": "INTERNAL_ERROR", "message": "Workspace request failed", "request_id": request_id}
        return JSONResponse(status_code=500, content={"detail": error, "error": error})

    def ensure_project(project_id: str) -> None:
        if project_scope and project_id not in project_scope:
            # Keep authorization failures indistinguishable from an unknown
            # report to avoid project enumeration.
            raise HTTPException(status_code=404, detail={"code": "REPORT_NOT_FOUND", "message": "Report was not found"})

    def authorized_report(report_id: int) -> Any:
        report = repository.get_report(report_id)
        ensure_project(report.project_id)
        return report

    def report_view(report: Any) -> dict[str, Any]:
        value = report.to_dict()
        if not report.output_available:
            return value
        try:
            output_dir = repository.get_output_dir(report.id)
            if output_dir is not None:
                trusted_output_dir(output_dir)
        except HTTPException as exc:
            if exc.status_code == 403:
                value["output_available"] = False
                value["artifact_availability"] = "PATH_FORBIDDEN"
                value["manifest_status"] = "UNVERIFIED"
        except ReportServiceError:
            value["output_available"] = False
            value["artifact_availability"] = "PATH_UNAVAILABLE"
            value["manifest_status"] = "UNVERIFIED"
        return value

    def authorize_operation(events: list[tuple[str, dict[str, Any]]] | None) -> None:
        if events is None:
            return
        run_ids = {int(payload["run_id"]) for _, payload in events if payload.get("run_id") is not None}
        for run_id in run_ids:
            authorized_report(run_id)

    def trusted_output_dir(output_dir: Any) -> tuple[Path, list[str]]:
        raw = Path(output_dir).expanduser()
        roots = trusted_roots if trusted_roots is not None else [str(os.environ.get("BIOREPORT_TRUSTED_ROOT", Path.home() / ".bioreport"))]
        resolved = raw.resolve()
        trusted = any(resolved == Path(root).expanduser().resolve() or Path(root).expanduser().resolve() in resolved.parents for root in roots)
        if raw.is_symlink() or not trusted:
            raise HTTPException(status_code=403, detail={"code": "PATH_FORBIDDEN", "message": "Report output is outside the configured trusted root"})
        return resolved, roots

    @app.middleware("http")
    async def require_token(request: Request, call_next: Any) -> Any:
        supplied_request_id = request.headers.get("x-request-id", "")
        request_id = supplied_request_id if re.fullmatch(r"[A-Za-z0-9._-]{1,128}", supplied_request_id) else str(uuid.uuid4())
        request.state.workspace_request_id = request_id
        if rate_limit_per_minute and request.url.path.startswith("/api/"):
            client = request.client.host if request.client else "unknown"
            now = time.monotonic()
            window = request_windows.setdefault(client, deque())
            while window and now - window[0] >= 60:
                window.popleft()
            if len(window) >= rate_limit_per_minute:
                return JSONResponse(status_code=429, content={"detail": {"code": "RATE_LIMITED", "message": "Too many requests", "request_id": request_id}, "error": {"code": "RATE_LIMITED", "message": "Too many requests", "request_id": request_id}}, headers={"Retry-After": "60", "X-Request-ID": request_id})
            window.append(now)
        if required_token and request.url.path.startswith("/api/"):
            supplied = request.headers.get("authorization", "")
            candidate = supplied[7:] if supplied.lower().startswith("bearer ") else ""
            if not hmac.compare_digest(candidate, required_token):
                return JSONResponse(status_code=401, content={"detail": {"code": "UNAUTHORIZED", "message": "Bearer token required", "request_id": request_id}, "error": {"code": "UNAUTHORIZED", "message": "Bearer token required", "request_id": request_id}}, headers={"WWW-Authenticate": "Bearer", "X-Request-ID": request_id})
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    def error_response(error: ReportServiceError) -> HTTPException:
        status = 404 if isinstance(error, ReportNotFound) else 503 if isinstance(error, DatabaseUnavailable) else 500
        messages = {
            "REPORT_NOT_FOUND": "Report was not found",
            "DATABASE_UNAVAILABLE": "Report history is unavailable",
        }
        return HTTPException(status_code=status, detail={"code": error.code, "message": messages.get(error.code, "Workspace service error")})

    @app.get("/api/reports")
    def list_reports(
        project: str | None = None,
        project_id: str | None = None,
        status: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = Query(default=50, ge=1, le=200),
        cursor: int | None = Query(default=None, ge=1),
    ) -> dict[str, Any]:
        try:
            page = repository.list_reports(project=project_id or project, projects=project_scope or None, status=status, since=since, until=until, limit=limit, cursor=cursor)
            return {"items": [report_view(item) for item in page.items], "next_cursor": page.next_cursor}
        except ReportServiceError as exc:
            raise error_response(exc) from exc

    @app.get("/api/reports/{report_id}")
    def get_report(report_id: int) -> dict[str, Any]:
        try:
            return report_view(authorized_report(report_id))
        except ReportServiceError as exc:
            raise error_response(exc) from exc

    # Versioned aliases are kept alongside the short local URLs during rollout.
    app.add_api_route("/api/v1/reports", list_reports, methods=["GET"])
    app.add_api_route("/api/v1/reports/{report_id}", get_report, methods=["GET"])

    @app.get("/api/v1/reports/{report_id}/modules")
    def list_modules(report_id: int) -> dict[str, Any]:
        try:
            report = authorized_report(report_id)
            return {"run_id": report.id, "modules": report.modules, "warnings": report.warnings}
        except ReportServiceError as exc:
            raise error_response(exc) from exc

    @app.get("/api/v1/reports/{report_id}/modules/{module_id}/evidence")
    def module_evidence(report_id: int, module_id: str, comparison: str | None = None) -> dict[str, Any]:
        try:
            report = authorized_report(report_id)
            supported_preview = {"rna.results.samples", "rna.results.heatmap", "rna.results.enrichment", "rna.qc.fastp", "rna.qc.screen", "rna.qc.qualimap", "rna.qc.star"}
            if module_id in supported_preview:
                output_dir = repository.get_output_dir(report_id)
                if output_dir is None:
                    return {"module_id": module_id, "run_id": report_id, "availability": "UNAVAILABLE", "integrity": "UNVERIFIED", "warnings": ["REPORT_OUTPUT_UNAVAILABLE"]}
                output_dir, _ = trusted_output_dir(output_dir)
                try:
                    package = EvidenceBuilder(output_dir).build_registered(project_id=report.project_id, module_id=module_id, run_id=report_id)
                except FileNotFoundError:
                    return {"module_id": module_id, "run_id": report_id, "availability": "UNAVAILABLE", "integrity": "UNVERIFIED", "warnings": ["EVIDENCE_SOURCE_MISSING"]}
                except PermissionError as exc:
                    raise HTTPException(status_code=403, detail={"code": "PATH_FORBIDDEN", "message": "Evidence source is outside the trusted root"}) from exc
                return {**package.to_dict(), "availability": "AVAILABLE", "integrity": "verified"}
            if module_id == "rna.results.matrix":
                return {"module_id": module_id, "run_id": report_id, "availability": "FORBIDDEN", "integrity": "UNVERIFIED", "warnings": ["FULL_MATRIX_EVIDENCE_FORBIDDEN"]}
            if module_id != "rna.results.deg" or not comparison:
                raise HTTPException(status_code=422, detail={"code": "UNSUPPORTED_EVIDENCE_REQUEST", "message": "v1 evidence endpoint currently supports rna.results.deg and registered unavailable states"})
            output_dir = repository.get_output_dir(report_id)
            if output_dir is None:
                raise HTTPException(status_code=404, detail={"code": "PATH_UNAVAILABLE", "message": "Report output is unavailable"})
            output_dir, _ = trusted_output_dir(output_dir)
            package = EvidenceBuilder(output_dir).build_deg(project_id=report.project_id, comparison=comparison, run_id=report_id)
            return package.to_dict()
        except HTTPException:
            raise
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail={"code": "EVIDENCE_SOURCE_MISSING", "message": "Evidence source is unavailable"}) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail={"code": "PATH_FORBIDDEN", "message": "Evidence source is outside the trusted root"}) from exc
        except ReportServiceError as exc:
            raise error_response(exc) from exc

    @app.get("/api/v1/reports/{report_id}/artifacts")
    def list_artifacts(report_id: int) -> dict[str, Any]:
        try:
            authorized_report(report_id)
            output_dir = repository.get_output_dir(report_id)
            if output_dir is None:
                return {"run_id": report_id, "artifacts": [], "availability": "PATH_UNAVAILABLE"}
            output_dir, roots = trusted_output_dir(output_dir)
            resolver = ArtifactResolver(output_dir, trusted_roots=roots)
            return {"run_id": report_id, "artifacts": [item.to_dict() for item in resolver.records(verify=False)]}
        except ReportServiceError as exc:
            raise error_response(exc) from exc
        except ArtifactError as exc:
            raise HTTPException(status_code=403, detail={"code": exc.code, "message": str(exc)}) from exc

    @app.get("/api/v1/reports/{report_id}/provenance")
    def report_provenance(report_id: int) -> dict[str, Any]:
        try:
            report = authorized_report(report_id)
            output_dir = repository.get_output_dir(report_id)
            if output_dir is None:
                return {"run_id": report_id, "availability": "PATH_UNAVAILABLE", "manifests": {}}
            output_dir, roots = trusted_output_dir(output_dir)
            resolver = ArtifactResolver(output_dir, trusted_roots=roots)
            return {"run_id": report_id, "project_id": report.project_id, "manifests": resolver.manifest_snapshot()}
        except ReportServiceError as exc:
            raise error_response(exc) from exc

    @app.get("/api/v1/reports/{report_id}/artifacts/{artifact_id}/content")
    def artifact_content(report_id: int, artifact_id: str) -> Any:
        try:
            authorized_report(report_id)
            output_dir = repository.get_output_dir(report_id)
            if output_dir is None:
                raise HTTPException(status_code=404, detail={"code": "PATH_UNAVAILABLE", "message": "Report output is unavailable"})
            output_dir, roots = trusted_output_dir(output_dir)
            record = ArtifactResolver(output_dir, trusted_roots=roots).get(artifact_id)
            if not record.available or record.integrity != "verified":
                raise HTTPException(status_code=404, detail={"code": record.integrity.upper(), "message": "Artifact is not readable"})
            return FileResponse(record.path, media_type=record.content_type or "application/octet-stream", filename=record.path.name, content_disposition_type="inline", headers={"Content-Security-Policy": "sandbox; default-src 'none'; img-src data: blob:; style-src 'unsafe-inline'", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"})
        except HTTPException:
            raise
        except ReportServiceError as exc:
            raise error_response(exc) from exc
        except ArtifactError as exc:
            raise HTTPException(status_code=404, detail={"code": exc.code, "message": "Artifact is unavailable"}) from exc

    @app.post("/api/v1/reports/{report_id}/interpretations")
    def create_interpretation(report_id: int, request: InterpretationRequest, idempotency_key: str | None = Header(default=None)) -> dict[str, Any]:
        try:
            request_data = _dto_data(request)
            if not isinstance(idempotency_key, str):
                idempotency_key = None
            if idempotency_key is not None:
                if not idempotency_key or len(idempotency_key) > 128:
                    raise HTTPException(status_code=422, detail={"code": "INVALID_IDEMPOTENCY_KEY", "message": "Idempotency-Key must be 1-128 characters"})
                cache_key = (int(report_id), idempotency_key)
                fingerprint = json.dumps(request_data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                cached = idempotent_interpretations.get(cache_key)
                if cached is not None:
                    if cached[0] != fingerprint:
                        raise HTTPException(status_code=409, detail={"code": "IDEMPOTENCY_KEY_REUSED", "message": "Idempotency-Key was used with a different request"})
                    return cached[1]
            report = authorized_report(report_id)
            module_id = request_data.get("module_id")
            comparison = request_data.get("comparison")
            registered_preview_modules = {"rna.results.samples", "rna.results.heatmap", "rna.results.enrichment", "rna.qc.fastp", "rna.qc.screen", "rna.qc.qualimap", "rna.qc.star"}
            if module_id == "rna.results.deg":
                if not isinstance(comparison, str) or not comparison:
                    raise HTTPException(status_code=422, detail={"code": "UNSUPPORTED_EVIDENCE_REQUEST", "message": "rna.results.deg requires a comparison"})
            elif module_id not in registered_preview_modules:
                raise HTTPException(status_code=422, detail={"code": "UNSUPPORTED_EVIDENCE_REQUEST", "message": "The requested module has no safe evidence builder"})
            output_dir = repository.get_output_dir(report_id)
            if output_dir is None:
                raise HTTPException(status_code=422, detail={"code": "EVIDENCE_SOURCE_MISSING", "message": "Report output directory is unavailable"})
            output_dir, _ = trusted_output_dir(output_dir)
            try:
                top_n = int(request_data.get("top_n", 10))
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=422, detail={"code": "INVALID_TOP_N", "message": "top_n must be an integer between 1 and 100"}) from exc
            if not 1 <= top_n <= 100:
                raise HTTPException(status_code=422, detail={"code": "INVALID_TOP_N", "message": "top_n must be an integer between 1 and 100"})
            if module_id == "rna.results.deg":
                evidence = EvidenceBuilder(output_dir, top_n=top_n).build_deg(project_id=report.project_id, comparison=comparison, run_id=report_id)
            else:
                evidence = EvidenceBuilder(output_dir, top_n=top_n).build_registered(project_id=report.project_id, module_id=module_id, run_id=report_id)
            effective_comparison = evidence.comparison
            result = InterpretationOrchestrator().interpret(evidence.to_dict())
            if not result.validation.valid:
                raise HTTPException(status_code=422, detail={"code": "INTERPRETATION_VALIDATION_FAILED", "errors": result.validation.errors})
            interpretation_id = interpretations.save_interpretation(run_id=report_id, project_id=report.project_id, module_id=module_id, comparison=effective_comparison, evidence_hash=evidence.evidence_hash, output=result.output, validation=result.validation.to_dict(), provider=result.provider, model=result.model)
            operation_id = str(uuid.uuid4())
            operations[operation_id] = [
                ("started", {"operation_id": operation_id, "run_id": report_id, "module_id": module_id}),
                ("evidence_ready", {"evidence_hash": evidence.evidence_hash, "module_id": module_id}),
                ("tool_status", {"tool": "get_module_evidence", "status": "completed", "module_id": module_id}),
                ("token", {"text": result.output.get("summary", "")}),
                ("validated", {"interpretation_id": interpretation_id, "status": "validated"}),
                ("completed", {"interpretation_id": interpretation_id, "status": "completed"}),
            ]
            # Bound in-memory operation history; durable interpretation data is
            # already stored in SQLite and remains the source of truth.
            if len(operations) > 100:
                del operations[next(iter(operations))]
            response = {"operation_id": operation_id, "interpretation_id": interpretation_id, "evidence_hash": evidence.evidence_hash, "status": "validated", "output": result.output}
            if idempotency_key is not None:
                idempotent_interpretations[cache_key] = (fingerprint, response)
                if len(idempotent_interpretations) > 200:
                    del idempotent_interpretations[next(iter(idempotent_interpretations))]
            return response
        except HTTPException:
            raise
        except FileNotFoundError as exc:
            raise HTTPException(status_code=422, detail={"code": "EVIDENCE_SOURCE_MISSING", "message": "Evidence source is unavailable"}) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail={"code": "PATH_FORBIDDEN", "message": "Evidence source is outside the trusted root"}) from exc
        except (sqlite3.Error, OSError) as exc:
            raise HTTPException(status_code=503, detail={"code": "PERSISTENCE_UNAVAILABLE", "message": "Workspace persistence is not migrated"}) from exc
        except ReportServiceError as exc:
            raise error_response(exc) from exc

    @app.get("/api/v1/reports/{report_id}/interpretations")
    def list_interpretations(report_id: int, module_id: str | None = None) -> dict[str, Any]:
        try:
            authorized_report(report_id)
            return {"run_id": report_id, "items": interpretations.list_interpretations(run_id=report_id, module_id=module_id)}
        except ReportServiceError as exc:
            raise error_response(exc) from exc
        except sqlite3.Error as exc:
            raise HTTPException(status_code=503, detail={"code": "PERSISTENCE_UNAVAILABLE", "message": "Workspace persistence is not migrated"}) from exc

    @app.get("/api/v1/interpretations/{interpretation_id}")
    def get_interpretation(interpretation_id: str) -> dict[str, Any]:
        try:
            value = interpretations.get_interpretation(interpretation_id)
        except sqlite3.Error as exc:
            raise HTTPException(status_code=503, detail={"code": "PERSISTENCE_UNAVAILABLE", "message": "Workspace persistence is not migrated"}) from exc
        if value is None:
            raise HTTPException(status_code=404, detail={"code": "INTERPRETATION_NOT_FOUND", "message": interpretation_id})
        ensure_project(str(value.get("project_id", "")))
        return value

    @app.post("/api/v1/conversations")
    def create_conversation(request: ConversationRequest) -> dict[str, Any]:
        try:
            request_data = _dto_data(request)
            run_id = int(request_data["run_id"])
            authorized_report(run_id)
            session_id = interpretations.create_session(run_id=run_id, module_id=request_data.get("module_id"), evidence_hash=request_data.get("evidence_hash"))
            return {"session_id": session_id, "status": "active"}
        except (KeyError, ValueError):
            raise HTTPException(status_code=422, detail={"code": "INVALID_CONVERSATION_REQUEST", "message": "run_id is required"})
        except ReportServiceError as exc:
            raise error_response(exc) from exc
        except sqlite3.Error as exc:
            raise HTTPException(status_code=503, detail={"code": "PERSISTENCE_UNAVAILABLE", "message": "Workspace persistence is not migrated"}) from exc

    @app.get("/api/v1/conversations/{session_id}")
    def get_conversation(session_id: str) -> dict[str, Any]:
        try:
            value = interpretations.get_session(session_id)
        except sqlite3.Error as exc:
            raise HTTPException(status_code=503, detail={"code": "PERSISTENCE_UNAVAILABLE", "message": "Workspace persistence is not migrated"}) from exc
        if value is None:
            raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": session_id})
        authorized_report(int(value["run_id"]))
        return value

    @app.post("/api/v1/conversations/{session_id}/messages")
    def add_conversation_message(session_id: str, request: ConversationMessageRequest) -> dict[str, Any]:
        request_data = _dto_data(request)
        role, content = request_data.get("role"), request_data.get("content")
        if not content.strip() or role not in {"user", "assistant", "system"}:
            raise HTTPException(status_code=422, detail={"code": "INVALID_MESSAGE", "message": "role and non-empty content are required"})
        try:
            session = interpretations.get_session(session_id)
            if session is None:
                raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": session_id})
            authorized_report(int(session["run_id"]))
            message_id = interpretations.add_message(session_id, role=role, content=content)
            response: dict[str, Any] = {"message_id": message_id, "session_id": session_id, "status": "stored"}
            if role == "user":
                module_id = session.get("module_id") or "unknown module"
                evidence_hash = session.get("evidence_hash")
                evidence_label = evidence_hash[:12] if isinstance(evidence_hash, str) else "unavailable"
                assistant_content = (
                    f"This conversation is scoped to {module_id}. "
                    f"The answer must use evidence snapshot {evidence_label}; "
                    "generate a new validated interpretation when a formal report statement is required."
                )
                assistant_id = interpretations.add_message(session_id, role="assistant", content=assistant_content)
                response["assistant"] = {"message_id": assistant_id, "content": assistant_content, "status": "draft"}
            return response
        except HTTPException:
            raise
        except sqlite3.Error as exc:
            raise HTTPException(status_code=503, detail={"code": "PERSISTENCE_UNAVAILABLE", "message": "Workspace persistence is not migrated"}) from exc

    @app.post("/api/v1/operations/{operation_id}/cancel")
    def cancel_operation(operation_id: str) -> dict[str, Any]:
        events = operations.get(operation_id)
        if events is None:
            raise HTTPException(status_code=404, detail={"code": "OPERATION_NOT_FOUND", "message": "No active operation"})
        authorize_operation(events)
        terminal = next((event for event, _ in reversed(events) if event in {"completed", "error", "cancelled"}), None)
        if terminal is None:
            operations[operation_id] = events[:2] + [("cancelled", {"operation_id": operation_id, "reason": "client_cancelled"})]
            terminal = "cancelled"
        return {"operation_id": operation_id, "status": terminal}

    @app.get("/api/v1/operations/{operation_id}/events")
    async def operation_event_stream(operation_id: str) -> Any:
        authorize_operation(operations.get(operation_id))

        async def stream():
            events = operations.get(operation_id)
            if events is None:
                events = [("started", {"operation_id": operation_id}), ("error", {"code": "OPERATION_NOT_FOUND", "message": "No active operation"})]
            async for event in operation_events(events):
                yield event
        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return app
