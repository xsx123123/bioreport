# Workspace v1 database migrations

The existing `runs` table is preserved for backward compatibility. The new read path does not run migrations and does not create tables. This is deliberate: a history viewer must work against an old or missing ledger without mutating it.

The migration (schema version 2) creates separate tables for `interpretations`, `conversation_sessions/messages`, and `agent_runs`, with foreign keys to `runs.id`, timestamps, model/provider metadata, prompt version, evidence references, and status/error fields. `interpretations` also records the comparison, per-run/module version, canonical output hash, validator version, and nullable `execution_id`; an interpretation can be staged before the run row exists and is bound transactionally when `agent_runs.execution_id` is finalized. Existing v1 interpretation tables are rebuilt once to remove the old `run_id NOT NULL` constraint while preserving rows. Migrations must run only from the report-generation or explicit administration command, never from a GET request.

`migrate_workspace(path)` creates an adjacent `path.bak` before the first transaction and preserves that pre-migration snapshot on idempotent re-runs; it never overwrites the rollback point with an already-upgraded database. `restore_workspace_backup(path)` is an explicit operator action that restores that backup; neither operation is called by API reads.

The supported operator commands are:

```bash
bioreport workspace-migrate --db /path/to/runs.db
bioreport workspace-restore --db /path/to/runs.db
```

Migration is intentionally opt-in and creates the backup by default. The restore command is also opt-in and should be run only after stopping writers and confirming the adjacent backup is the intended snapshot.

Interpretation version assignment uses a SQLite `BEGIN IMMEDIATE` transaction while reading the current maximum, so concurrent saves for one run/module/comparison cannot receive the same next version.

Workspace read/write connections use a five-second SQLite timeout, `PRAGMA busy_timeout=5000`, and explicitly enable `PRAGMA foreign_keys=ON`; this bounds transient lock waits and prevents execution/session rows from referencing nonexistent runs without enabling WAL or mutating the production ledger implicitly.
