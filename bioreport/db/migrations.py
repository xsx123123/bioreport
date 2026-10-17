"""Small, idempotent SQLite migration with backup and rollback-friendly steps."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path


SCHEMA_VERSION = 2


def _ensure_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _create_interpretations(connection: sqlite3.Connection) -> None:
    connection.execute("""CREATE TABLE IF NOT EXISTS interpretations (
        id TEXT PRIMARY KEY, run_id INTEGER REFERENCES runs(id), execution_id TEXT,
        project_id TEXT NOT NULL, module_id TEXT NOT NULL, comparison TEXT,
        version INTEGER NOT NULL DEFAULT 1, evidence_hash TEXT NOT NULL,
        output_hash TEXT NOT NULL DEFAULT '', provider TEXT NOT NULL, model TEXT NOT NULL,
        prompt_version TEXT NOT NULL, validator_version TEXT NOT NULL DEFAULT 'v1',
        output_json TEXT NOT NULL, validation_json TEXT NOT NULL,
        status TEXT NOT NULL, created_at TEXT NOT NULL,
        CHECK (run_id IS NOT NULL OR execution_id IS NOT NULL))""")


def _upgrade_interpretations(connection: sqlite3.Connection) -> None:
    columns = {row[1]: row for row in connection.execute("PRAGMA table_info(interpretations)")}
    if not columns:
        _create_interpretations(connection)
        return
    # SQLite cannot drop NOT NULL or add the execution check in place. Rebuild
    # once, copying all v1 rows and preserving their existing run binding.
    run_not_null = bool(columns.get("run_id", (None, None, None, 0))[3])
    if run_not_null or "execution_id" not in columns:
        connection.execute("DROP INDEX IF EXISTS idx_interpretations_run_module")
        connection.execute("ALTER TABLE interpretations RENAME TO interpretations_v1")
        _create_interpretations(connection)
        connection.execute("""INSERT INTO interpretations
            (id, run_id, execution_id, project_id, module_id, comparison, version,
             evidence_hash, output_hash, provider, model, prompt_version,
             validator_version, output_json, validation_json, status, created_at)
            SELECT id, run_id, NULL, project_id, module_id, comparison, version,
             evidence_hash, output_hash, provider, model, prompt_version,
             validator_version, output_json, validation_json, status, created_at
            FROM interpretations_v1""")
        connection.execute("DROP TABLE interpretations_v1")


def migrate_workspace(db_path: str | Path, *, backup: bool = True) -> Path | None:
    path = Path(db_path)
    if not path.is_file():
        raise FileNotFoundError(path)
    backup_path = path.with_suffix(path.suffix + ".bak") if backup else None
    # Preserve the first pre-migration snapshot. Re-running an idempotent
    # migration must never replace the rollback point with an already-upgraded
    # database.
    if backup_path and not backup_path.exists():
        shutil.copy2(path, backup_path)
    with sqlite3.connect(path, timeout=5.0) as connection:
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        _create_interpretations(connection)
        _ensure_column(connection, "interpretations", "comparison", "TEXT")
        _ensure_column(connection, "interpretations", "version", "INTEGER NOT NULL DEFAULT 1")
        _ensure_column(connection, "interpretations", "output_hash", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "interpretations", "validator_version", "TEXT NOT NULL DEFAULT 'v1'")
        _ensure_column(connection, "interpretations", "execution_id", "TEXT")
        _upgrade_interpretations(connection)
        connection.execute("CREATE INDEX IF NOT EXISTS idx_interpretations_run_module ON interpretations(run_id, module_id, created_at)")
        connection.execute("""CREATE TABLE IF NOT EXISTS conversation_sessions (
            id TEXT PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES runs(id), module_id TEXT,
            evidence_hash TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
        connection.execute("""CREATE TABLE IF NOT EXISTS conversation_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL REFERENCES conversation_sessions(id),
            role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL)""")
        connection.execute("""CREATE TABLE IF NOT EXISTS agent_runs (
            execution_id TEXT PRIMARY KEY, run_id INTEGER REFERENCES runs(id), project_id TEXT NOT NULL,
            status TEXT NOT NULL, error_code TEXT, created_at TEXT NOT NULL, bound_at TEXT)""")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_agent_runs_run_id ON agent_runs(run_id)")
        connection.execute("INSERT INTO schema_meta(key, value) VALUES('workspace_schema_version', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(SCHEMA_VERSION),))
    return backup_path


def restore_workspace_backup(db_path: str | Path) -> None:
    """Restore the adjacent migration backup; callers must explicitly invoke it."""
    path = Path(db_path)
    backup = path.with_suffix(path.suffix + ".bak")
    if not backup.is_file():
        raise FileNotFoundError(backup)
    shutil.copy2(backup, path)
