"""Read-only report history service for the Workspace UI/API.

The report generator owns writes to ``runs``.  This module deliberately opens
the database in SQLite read-only mode so browsing history can never mutate a
production database or create a missing database file.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote


class ReportServiceError(RuntimeError):
    """Base error with a stable API-facing code."""

    code = "REPORT_SERVICE_ERROR"


class DatabaseUnavailable(ReportServiceError):
    code = "DATABASE_UNAVAILABLE"


class ReportNotFound(ReportServiceError):
    code = "REPORT_NOT_FOUND"


@dataclass(frozen=True)
class ReportSummary:
    id: int
    project_id: str
    run_at: str
    status: str
    engine_version: str | None
    pipeline_version: str | None
    layout: str | None
    output_formats: list[str]
    modules: list[dict[str, Any]]
    output_available: bool
    artifact_availability: str
    manifest_status: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReportPage:
    items: list[ReportSummary]
    next_cursor: str | None

    def to_dict(self) -> dict[str, Any]:
        return {"items": [item.to_dict() for item in self.items], "next_cursor": self.next_cursor}


def _json_list(value: Any, warning: str, warnings: list[str]) -> list[Any]:
    if value in (None, ""):
        return []
    try:
        decoded = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        warnings.append(warning)
        return []
    if not isinstance(decoded, list):
        warnings.append(warning)
        return []
    return decoded


def _delivery_status(raw_output_dir: Any) -> tuple[bool, str, str]:
    """Return availability axes without exposing the stored filesystem path."""
    if not raw_output_dir:
        return False, "PATH_UNAVAILABLE", "MISSING"
    output_dir = Path(str(raw_output_dir)).expanduser()
    try:
        if output_dir.is_symlink() or not output_dir.is_dir():
            return False, "PATH_UNAVAILABLE", "MISSING"
        manifest_paths = (output_dir / "report-manifest.json", output_dir / "artifact-manifest.json")
        valid = 0
        present = 0
        for manifest in manifest_paths:
            if manifest.is_symlink():
                present += 1
                continue
            if not manifest.is_file():
                continue
            present += 1
            try:
                value = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(value, dict):
                valid += 1
        if valid == 0:
            return True, "PARTIAL", "INVALID" if present else "MISSING"
        return True, "AVAILABLE", "AVAILABLE"
    except OSError:
        return False, "PERMISSION_DENIED", "UNVERIFIED"


class SQLiteReportRepository:
    """Read-only repository over the existing BioReport run ledger."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path).expanduser()

    def _connect(self) -> sqlite3.Connection:
        if not self.db_path.is_file():
            raise DatabaseUnavailable(f"Database does not exist: {self.db_path}")
        # quote keeps spaces and unicode safe while preserving the absolute path.
        uri = f"file:{quote(str(self.db_path.resolve()), safe='/')}?mode=ro"
        try:
            connection = sqlite3.connect(uri, uri=True, timeout=5.0)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute("PRAGMA query_only = ON")
            return connection
        except sqlite3.Error as exc:
            raise DatabaseUnavailable(str(exc)) from exc

    @staticmethod
    def _summary(row: sqlite3.Row) -> ReportSummary:
        warnings: list[str] = []
        formats = [str(item) for item in _json_list(row["output_format"], "INVALID_OUTPUT_FORMATS", warnings)]
        modules_raw = _json_list(row["modules"], "INVALID_MODULES", warnings)
        modules: list[dict[str, Any]] = []
        for item in modules_raw:
            if isinstance(item, str):
                modules.append({"id": item, "title": item, "status": "unknown"})
            elif isinstance(item, dict) and item.get("id"):
                modules.append(dict(item))
            else:
                warnings.append("INVALID_MODULE_ENTRY")
        try:
            from .registry import get_registry
            modules = merge_module_metadata(modules, get_registry())
        except Exception:
            # History browsing must remain available even when an optional
            # analysis registry cannot be imported in a minimal installation.
            pass
        output_available, artifact_availability, manifest_status = _delivery_status(row["output_dir"])
        return ReportSummary(
            id=int(row["id"]),
            project_id=str(row["project_id"]),
            run_at=str(row["run_at"]),
            status=str(row["status"]),
            engine_version=row["engine_version"],
            pipeline_version=row["pipeline_version"],
            layout=row["layout"],
            output_formats=formats,
            modules=modules,
            output_available=output_available,
            artifact_availability=artifact_availability,
            manifest_status=manifest_status,
            warnings=warnings,
        )

    def list_reports(
        self,
        *,
        project: str | None = None,
        projects: Iterable[str] | None = None,
        status: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = 50,
        cursor: int | None = None,
    ) -> ReportPage:
        limit = max(1, min(int(limit), 200))
        clauses: list[str] = []
        params: list[Any] = []
        if projects is not None:
            project_values = tuple(dict.fromkeys(str(value) for value in projects if str(value)))
            if not project_values:
                return ReportPage(items=[], next_cursor=None)
            placeholders = ", ".join("?" for _ in project_values)
            clauses.append(f"project_id IN ({placeholders})")
            params.extend(project_values)
        if project:
            clauses.append("project_id LIKE ?")
            params.append(f"%{project}%")
        if status:
            clauses.append("status = ?")
            params.append(status)
        if since:
            clauses.append("run_at >= ?")
            params.append(f"{since}T00:00:00" if len(since) == 10 else since)
        if until:
            clauses.append("run_at <= ?")
            params.append(f"{until}T23:59:59" if len(until) == 10 else until)
        if cursor is not None:
            clauses.append("id < ?")
            params.append(int(cursor))
        query = "SELECT * FROM runs"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit + 1)
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        has_more = len(rows) > limit
        rows = rows[:limit]
        items = [self._summary(row) for row in rows]
        return ReportPage(items=items, next_cursor=str(items[-1].id) if has_more and items else None)

    def get_report(self, report_id: int) -> ReportSummary:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM runs WHERE id = ?", (int(report_id),)).fetchone()
        if row is None:
            raise ReportNotFound(f"Report {report_id} was not found")
        return self._summary(row)

    def get_output_dir(self, report_id: int) -> Path | None:
        """Return an internal path for server-side resolver composition only."""
        with self._connect() as connection:
            row = connection.execute("SELECT output_dir FROM runs WHERE id = ?", (int(report_id),)).fetchone()
        if row is None:
            raise ReportNotFound(f"Report {report_id} was not found")
        return Path(row["output_dir"]).expanduser() if row["output_dir"] else None


def merge_module_metadata(modules: Iterable[dict[str, Any]], registry: Any) -> list[dict[str, Any]]:
    """Add registry titles/categories without rejecting unknown historical IDs."""
    result = []
    for module in modules:
        item = dict(module)
        module_id = item.get("id")
        try:
            definition = registry.resolve(module_id)
        except (KeyError, TypeError, ValueError):
            item.setdefault("status", "unknown")
        else:
            item.setdefault("title", definition.title)
            item.setdefault("category", definition.category)
            item["status"] = "available"
        result.append(item)
    return result
