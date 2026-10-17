# BioReport Workspace v1 implementation

This repository now contains the first backend slice of Workspace v1:

- `bioreport.report_service.SQLiteReportRepository` reads the existing `runs` ledger with SQLite `mode=ro` and `PRAGMA query_only=ON`.
- `bioreport.artifacts.ArtifactResolver` exposes only artifact IDs declared by the generic artifact manifest or generated report manifest below a configured trusted root.
- Historical malformed JSON and unknown module IDs remain visible as warnings/statuses instead of making the history page unusable.

`bioreport.api.create_app` provides an optional FastAPI adapter when FastAPI is installed. The write endpoints use explicit Pydantic request DTOs for interpretation and conversation payloads; the base CLI remains independent of that optional web dependency.

## Query contract

`list_reports` supports `project`, `status`, `since`, `until`, bounded `limit` (1-200), and an integer cursor. Results are newest first; the cursor is the last returned run ID. Report DTOs expose separate artifact and Manifest status axes without returning local paths. `get_report` raises `REPORT_NOT_FOUND` for an unknown ID and `DATABASE_UNAVAILABLE` when the database is absent or cannot be opened read-only.

## Artifact contract

Manifest entries contain `artifact_id`/`artifact`, `role`, `path`, and optionally `sha256`, `size`/`size_bytes`, and `content_type`. The resolver merges the generic `artifact-manifest.json` with the generated HTML/PDF registrations in `report-manifest.json`; input manifests are not exposed as browser downloads. Listing reads only bounded Manifest metadata (`unverified`); the content endpoint performs the on-demand SHA-256 check before streaming. Paths are resolved beneath the trusted root, symlinks are rejected, and reads are bounded by `max_bytes`. Integrity is `verified`, `mismatch`, `too_large`, `forbidden`, `unverified`, or `missing`.

## Current v1 adapters and remaining validation

The current deliverable includes a real API-backed React shell in `frontend/`, deterministic DEG and allowlisted multi-module evidence builders, Scientific Validator, mock-ready Interpretation Orchestrator, migration/backup support, immutable interpretation versions, execution-id late binding, persisted conversation drafts, SSE event/cancel endpoints, and optional Quarto module-level slots. The browser consumes API DTOs rather than opening SQLite or filesystem paths directly. The AI engine now supports explicit provider vision capability fallback to text-only mode, complete config forwarding through the CLI wrapper, and bounded, non-symlink attachments. The API supports bearer tokens, exact project allowlists, explicit CORS origins, and configurable per-client rate limits. The local frontend typecheck and production build pass; real-provider validation, browser screenshots, and identity-aware production authentication remain open acceptance items.

When AI is enabled, registered HTML/PDF modules receive a generated optional AI slot that reads only server-staged `../data/ai_interpretations/<safe-module-id>*.md` files. `stage_module_interpretations()` is the bounded deterministic writer used by the pipeline when `ai.module_interpretations` is supplied; missing files produce no output, and symlinked files are rejected/ignored. With AI disabled no slots are added, preserving the legacy report structure. `tests/run_workspace_browser_e2e.py` contains the repeatable Playwright smoke flow for a fixture-backed API/Vite server.
The same writer emits `data/ai_reports/ai-interpretation-manifest.json` with per-module relative paths, byte sizes, and SHA-256 hashes for provenance.

Schema v2 migration/backup is explicit and tested on temporary databases; the first pre-migration `.bak` is preserved across idempotent reruns. The supported `workspace-migrate` and `workspace-restore` CLI commands require an operator action and are never invoked by API reads. Formal interpretation POST uses the same bounded builder for DEG, samples, heatmap, enrichment, and QC modules, while the full expression matrix remains forbidden. Report DTOs distinguish path availability from Manifest/artifact completeness.

The CLI wraps AI preparation and Quarto rendering in one failure boundary, so an AI setup/provider error records a failed run before exiting instead of leaving an untracked attempt.

Local API startup: install `bioreport[web]`, then run `BIOREPORT_DB=/path/to/runs.db BIOREPORT_TRUSTED_ROOT=/approved/report/root python -m bioreport.api_server` when reports are outside `~/.bioreport`. The default host is `127.0.0.1`; public or LAN binding is refused unless `BIOREPORT_API_TOKEN` is configured, and token validation is applied to `/api/*` routes. Use this controlled module entry point instead of invoking uvicorn directly so the bind policy cannot be bypassed.

## Release acceptance status

The local implementation gate is **CONDITIONAL GO**. The following evidence is current:

| Area | Status | Evidence or boundary |
| --- | --- | --- |
| Python services, API contracts, migrations, artifact and evidence security | PASS | `pytest -q`: 165 passed, 3 skipped; compileall and `git diff --check` pass |
| Frontend type safety and production bundle | PASS | `npm run typecheck` and `npm run build` pass |
| Browser interaction and screenshots | BLOCKED | Playwright browsers crash in the restricted sandbox before page load |
| Deterministic mock interpretation, persistence, SSE, cancellation | PASS | Covered by workspace API, service, agent, persistence, and SSE tests |
| Real provider and vision fallback | UNVERIFIED | No provider key or billable remote call was used |
| Quarto AI-on render with a real kernel | UNVERIFIED | Render path and optional slots are implemented; a full Quarto/kernel run was not available |
| Production identity-aware authentication and project mapping | UNVERIFIED | Static bearer token plus exact project allowlist are implemented; enterprise identity integration remains deployment work |

The conditional gate means the local code and deterministic contracts are ready for review, while browser, provider, Quarto-kernel, and production identity checks must be completed in an environment that supplies those capabilities. Until then, keep the API loopback-bound and treat external-provider results as unverified. On a database that has been explicitly migrated to Workspace schema v2, the CLI now stages an `execution_id` before AI/Quarto work, records the terminal `runs.id`, and binds the execution atomically; legacy databases continue without implicit migration. The frontend aborts stalled interpretation streams after 30 seconds and reports cancellation separately from timeout. Evidence cards expose registered figure metadata (logical ID, MIME, size, and shortened digest) without exposing local paths.
