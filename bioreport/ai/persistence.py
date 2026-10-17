"""Persistence for immutable interpretation versions and chat sessions."""

from __future__ import annotations

import json
import hashlib
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .interpreter import redact_local_paths


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class InterpretationRepository:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def save_interpretation(self, *, run_id: int | None = None, execution_id: str | None = None, project_id: str, module_id: str, evidence_hash: str, output: dict[str, Any], validation: dict[str, Any], provider: str, model: str, prompt_version: str = "v1", comparison: str | None = None, validator_version: str = "v1") -> str:
        if run_id is None and execution_id is None:
            raise ValueError("run_id or execution_id is required")
        interpretation_id = str(uuid.uuid4())
        output_json = json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        output_hash = hashlib.sha256(output_json.encode("utf-8")).hexdigest()
        with sqlite3.connect(self.db_path, timeout=5.0) as connection:
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            if run_id is None:
                version_query = "SELECT COALESCE(MAX(version), 0) + 1 FROM interpretations WHERE execution_id = ? AND module_id = ? AND (comparison IS ? OR comparison = ?)"
                version_params = (execution_id, module_id, comparison, comparison)
            else:
                version_query = "SELECT COALESCE(MAX(version), 0) + 1 FROM interpretations WHERE run_id = ? AND module_id = ? AND (comparison IS ? OR comparison = ?)"
                version_params = (run_id, module_id, comparison, comparison)
            version = connection.execute(version_query, version_params).fetchone()[0]
            connection.execute("""INSERT INTO interpretations(id, run_id, execution_id, project_id, module_id, comparison, version, evidence_hash, output_hash, provider, model, prompt_version, validator_version, output_json, validation_json, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (interpretation_id, run_id, execution_id, project_id, module_id, comparison, version, evidence_hash, output_hash, provider, model, prompt_version, validator_version, output_json, json.dumps(validation, ensure_ascii=False, sort_keys=True), "validated" if validation.get("valid") else "rejected", _now()))
        return interpretation_id

    def get_interpretation(self, interpretation_id: str) -> dict[str, Any] | None:
        connection = sqlite3.connect(self.db_path, timeout=5.0)
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute("SELECT * FROM interpretations WHERE id = ?", (interpretation_id,)).fetchone()
            if row is None:
                return None
            value = dict(row)
            value["output"] = json.loads(value.pop("output_json"))
            value["validation"] = json.loads(value.pop("validation_json"))
            return value
        finally:
            connection.close()

    def list_interpretations(self, *, run_id: int, module_id: str | None = None) -> list[dict[str, Any]]:
        connection = sqlite3.connect(self.db_path, timeout=5.0)
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.row_factory = sqlite3.Row
        try:
            query = "SELECT id, run_id, execution_id, project_id, module_id, comparison, version, evidence_hash, output_hash, provider, model, prompt_version, validator_version, validation_json, status, created_at FROM interpretations WHERE run_id = ?"
            params: list[Any] = [int(run_id)]
            if module_id:
                query += " AND module_id = ?"
                params.append(module_id)
            query += " ORDER BY created_at DESC, id DESC"
            rows = connection.execute(query, params).fetchall()
            values = []
            for row in rows:
                item = dict(row)
                item["validation"] = json.loads(item.pop("validation_json"))
                values.append(item)
            return values
        finally:
            connection.close()

    def create_session(self, *, run_id: int, module_id: str | None, evidence_hash: str | None) -> str:
        session_id = str(uuid.uuid4())
        now = _now()
        with sqlite3.connect(self.db_path, timeout=5.0) as connection:
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("INSERT INTO conversation_sessions(id, run_id, module_id, evidence_hash, created_at, updated_at) VALUES(?,?,?,?,?,?)", (session_id, run_id, module_id, evidence_hash, now, now))
        return session_id

    def create_execution(self, *, project_id: str, execution_id: str | None = None) -> str:
        execution_id = execution_id or str(uuid.uuid4())
        with sqlite3.connect(self.db_path, timeout=5.0) as connection:
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("INSERT INTO agent_runs(execution_id, project_id, status, created_at) VALUES(?,?,?,?)", (execution_id, project_id, "staged", _now()))
        return execution_id

    def bind_execution(self, execution_id: str, *, run_id: int, status: str = "completed", error_code: str | None = None) -> None:
        if status not in {"completed", "failed", "cancelled"}:
            raise ValueError("invalid agent execution terminal status")
        with sqlite3.connect(self.db_path, timeout=5.0) as connection:
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute("PRAGMA foreign_keys=ON")
            cursor = connection.execute("UPDATE agent_runs SET run_id = ?, status = ?, error_code = ?, bound_at = ? WHERE execution_id = ?", (int(run_id), status, error_code, _now(), execution_id))
            if cursor.rowcount != 1:
                raise KeyError(execution_id)
            staged = connection.execute("SELECT id, module_id, comparison FROM interpretations WHERE execution_id = ? AND run_id IS NULL ORDER BY created_at, id", (execution_id,)).fetchall()
            for interpretation_id, module_id, comparison in staged:
                next_version = connection.execute(
                    "SELECT COALESCE(MAX(version), 0) + 1 FROM interpretations WHERE run_id = ? AND module_id = ? AND (comparison IS ? OR comparison = ?)",
                    (int(run_id), module_id, comparison, comparison),
                ).fetchone()[0]
                connection.execute("UPDATE interpretations SET version = ?, run_id = ? WHERE id = ?", (next_version, int(run_id), interpretation_id))
            connection.execute("UPDATE interpretations SET run_id = ? WHERE execution_id = ? AND run_id IS NULL", (int(run_id), execution_id))

    def get_execution(self, execution_id: str) -> dict[str, Any] | None:
        connection = sqlite3.connect(self.db_path, timeout=5.0)
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute("SELECT * FROM agent_runs WHERE execution_id = ?", (execution_id,)).fetchone()
            return dict(row) if row else None
        finally:
            connection.close()

    def add_message(self, session_id: str, *, role: str, content: str) -> int:
        if role not in {"user", "assistant", "system"}:
            raise ValueError("unsupported conversation role")
        content = str(redact_local_paths(content))
        with sqlite3.connect(self.db_path, timeout=5.0) as connection:
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute("PRAGMA foreign_keys=ON")
            cursor = connection.execute("INSERT INTO conversation_messages(session_id, role, content, created_at) VALUES(?,?,?,?)", (session_id, role, content, _now()))
            connection.execute("UPDATE conversation_sessions SET updated_at = ? WHERE id = ?", (_now(), session_id))
            return int(cursor.lastrowid)

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        connection = sqlite3.connect(self.db_path, timeout=5.0)
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.row_factory = sqlite3.Row
        try:
            session = connection.execute("SELECT * FROM conversation_sessions WHERE id = ?", (session_id,)).fetchone()
            if session is None:
                return None
            messages = connection.execute("SELECT id, role, content, created_at FROM conversation_messages WHERE session_id = ? ORDER BY id", (session_id,)).fetchall()
            return {**dict(session), "messages": [dict(message) for message in messages]}
        finally:
            connection.close()
