# Workspace v1 runtime acceptance

Current verified acceptance:

1. A temporary SQLite ledger can be paginated and filtered without any write operation.
2. Missing databases return `DATABASE_UNAVAILABLE`.
3. Malformed JSON and unknown module IDs remain inspectable with warnings/statuses.
4. Manifest-backed JSONL artifacts verify SHA-256 and reject path traversal.
5. Tampered artifacts are reported as `mismatch` and cannot be streamed.

6. DEG evidence, deterministic mock interpretation, scientific numeric validation, migration backup, and interpretation round-trip pass local fixtures.
7. API route registration, conversation draft round-trip, operation-cancel idempotency, and SSE JSON/event termination pass local tests.

8. Read-only production ledger check: `~/.bioreport/runs.db` returned 49 records, with 10 output directories currently unavailable; no write or migration was executed against it.

9. Real fixture render without a Jupyter kernel: `python tests/render_report_inprocess.py -c tests/report.rna.local.json -o /tmp/bioreport-workspace-html --format html` produced `PRJ-RNA-LOCAL-001_report.html` (75 MB); the PDF command produced `PRJ-RNA-LOCAL-001_report.pdf` (7 MB). Both completed successfully, and `provenance-validation.json` reported `PASS` (HTML 74 artifacts, PDF 80 artifacts checked). This is a real Quarto/no-execute render, not a full `bioreport run` kernel execution.

10. The same rendered HTML output was resolved through `ArtifactResolver` using its real `report-manifest.json`: listing returned the 78,151,500-byte report as `unverified` metadata, and the on-demand `get()` path returned `verified` after SHA-256 calculation. Input manifests were not exposed as downloadable artifacts.

11. Artifact responses use `Content-Disposition: inline`, `X-Content-Type-Options: nosniff`, and a restrictive `Content-Security-Policy: sandbox` header; the frontend only enables logical artifact links for available Manifest entries.

12. Workspace schema v2 migration tests preserve v1 interpretation rows, allow execution-only staged interpretations, and reassign versions transactionally when an execution is bound to a run. Interpretation POST retries with the same `Idempotency-Key` return the original operation without inserting another version.

13. The API contract now includes an importable OpenAPI 3.1 summary; the executable FastAPI schema remains available from `app.openapi()` and is covered by route/OpenAPI registration tests.

14. Formal interpretation POST now accepts every bounded registered preview module (`samples`, `heatmap`, `enrichment`, and QC) through the same deterministic builder; matrix requests remain explicitly rejected. A fixture test verifies non-DEG persistence with a null comparison.

15. Re-running the schema migration preserves the original adjacent `.bak` rollback snapshot; a regression test restores the pre-v2 database after two migration calls.

16. Report list/detail DTOs expose separate `artifact_availability` and `manifest_status` axes, so an existing directory without a valid Manifest is reported as partial rather than complete.

17. API report views additionally apply the configured trusted-root policy before advertising output availability; an otherwise existing directory outside that root is returned as `PATH_FORBIDDEN/UNVERIFIED`.

18. Evidence Builder fixtures reject symlinked parent components, not only symlinked leaf files, before reading registered module CSVs.

19. The CLI records a failed run when AI preparation raises before Quarto rendering; a regression fixture verifies `status=failed` is written before exit.

20. Report status fixtures distinguish a malformed present Manifest (`PARTIAL/INVALID`) from a missing Manifest (`PARTIAL/MISSING`).

21. API evidence routes map symlinked or out-of-root module sources to `403 PATH_FORBIDDEN` rather than a persistence or generic server error.

22. Interpretation and conversation fixtures redact local absolute paths before persistence, while preserving the evidence/reference structure.

23. Persistence write tests enable SQLite foreign keys and reject binding an execution to a nonexistent run.

24. SSE framing tests verify newline-safe JSON and redact local paths from token/error payloads.

25. API error contract tests verify stable `error.code/message/request_id`, legacy `detail` compatibility, and request ID correlation.

26. A migrated temporary Workspace database exercises the CLI lifecycle helpers: `agent_runs` is staged before report work and bound to the recorded `runs.id` with terminal `completed` status; an AI interpretation manifest carries the same `execution_id`.

27. FastAPI write routes expose Pydantic request schemas for interpretation, conversation, and message payloads; direct-call compatibility remains covered by the API regression tests.

28. Explicit `bioreport workspace-migrate --db ...` and `bioreport workspace-restore --db ...` commands were exercised against a temporary ledger; migration created the adjacent backup and restore returned the database to the pre-migration snapshot.

29. Formal interpretation operations emit the complete ordered mock sequence including `started`, `evidence_ready`, `tool_status`, `token`, `validated`, and terminal `completed`; SSE framing tests also cover newline-safe payloads and local-path redaction.

30. DEG evidence scans only fixed, trusted-root-relative volcano figure names, records MIME/size/SHA-256 without returning a local path, and emits `FIGURE_UNAVAILABLE` when no registered figure exists.

31. The React workspace applies a 30-second AbortController deadline to interpretation SSE, distinguishes timeout from client cancellation, and typechecks/builds successfully.

32. The React SSE consumer parses each JSON `data` frame and incrementally renders `token.text` in the Agent pane; the production bundle includes the streaming output state and responsive styling.

33. Scientific Validator rejects malformed, non-string, and unknown evidence references instead of silently skipping them; a negative fixture covers the non-string case.

34. Artifact Resolver validates declared size on content access and enforces a conservative extension/MIME allowlist; mismatches are unreadable and unknown types are `forbidden` while remaining metadata-visible.

35. The React three-pane workspace includes keyboard-labelled collapse controls and pointer-drag separators for the module and Agent panes; responsive CSS hides separators and uses a single-column layout on narrow screens. Typecheck/build pass; pixel-level browser verification remains environment-blocked.

36. Artifact downloads infer a safe MIME type from an allowlisted extension when the Manifest omits `content_type`, so verified JSONL/HTML/PDF/image responses do not fall back to an ambiguous octet-stream type.

37. The React Evidence card renders registered figure IDs with MIME type, byte size, and a shortened SHA-256 digest; local filesystem paths remain absent from the UI contract.

Python command: `pytest -q` -> `165 passed, 3 skipped in about 30 seconds`; `python -m compileall -q bioreport` passed. Frontend `npm run typecheck` and `npm run build` both passed using the existing local npm cache (Vite 8.1.3, TypeScript, React, and lucide-react were linked into an ignored local `node_modules` for validation).

The final local regression also covers exact project-scope filtering, rate-limit/CORS configuration wiring, complete AI config forwarding through the lazy report wrapper, stale staging cleanup, multi-module evidence references, and numeric claims in summaries/limitations.

Browser screenshots remain unverified. Playwright and Chromium were present, but both the cached Chromium executable and `/usr/bin/chromium-browser` exited during launch with `TargetClosedError`/`SIGTRAP`; browser logs reported crashpad `setsockopt: Operation not permitted (1)` even with `--no-sandbox`, `--disable-crash-reporter`, `--disable-breakpad`, and `--disable-gpu`. A Firefox/WebKit smoke launch was also attempted and did not complete in the sandbox. This is an environment-level browser-process restriction, so no page interaction or screenshot is claimed as PASS. `npm install --no-audit --no-fund` was also attempted and produced no output for 100 seconds under the restricted network, then was stopped; the build itself was verified from pre-existing local cache packages. Real LLM, Quarto AI-on, and production authentication remain unverified and are not claimed as PASS. `RUN_REPORT_INTEGRATION=1 pytest -q tests/test_integration_render.py` was executed and both cases were BLOCKED by the sandbox's Jupyter kernel socket restriction (`PermissionError: [Errno 1] Operation not permitted`).

The reproducible browser command is `python tests/run_workspace_browser_e2e.py --base-url http://127.0.0.1:5174`; it expects a fixture-backed API on the Vite proxy target and writes desktop/mobile screenshots to `/tmp`. It remains BLOCKED only at browser process launch in this environment.

The Starlette/ASGI HTTP client probe was not retained as a test because it hangs in this sandbox dependency combination; route registration and deterministic token/bind policy tests remain covered. Re-run the HTTP probe with a normal network-capable test runner before deployment.

A second loopback probe attempted the supported `python -m bioreport.api_server --host 127.0.0.1 --port 8766` entry point with a temporary fixture, but the sandbox did not expose the bound socket to `curl` (`curl: (7) Failed to connect`); the process was stopped and no production data was touched. Direct uvicorn invocation is not the deployment path because it can bypass the bind policy.
