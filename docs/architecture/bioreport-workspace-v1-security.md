# Workspace v1 security

- SQLite is opened with `mode=ro` and `PRAGMA query_only=ON`.
- Artifact access is manifest-backed; callers cannot submit a filesystem path.
- API artifact DTOs expose only logical IDs and integrity metadata; local absolute paths are removed before serialization.
- Resolved paths must remain below configured trusted roots. Symlinks are rejected.
- The resolver rejects a symlinked report output directory before reading its manifest, not only symlinked artifact entries.
- The API defaults its trusted root to `~/.bioreport` (or `BIOREPORT_TRUSTED_ROOT`); a database `output_dir` is never trusted automatically. Custom fixture/report roots must be passed explicitly to `create_app(..., trusted_roots=[...])`.
- Evidence generation uses the same output-directory trusted-root check as artifact streaming and provenance; a malicious `runs.output_dir` cannot cause CSV reads outside the configured root.
- Evidence source discovery rejects a symlinked trusted root and symlinked parent path components before reading a CSV, even when the final file itself is not a symlink.
- Artifact listings are metadata-only; content reads enforce a bounded byte limit (250 MB default, 500 MB hard cap) and verify SHA-256 when the manifest supplies one before streaming.
- Manifest content types and file extensions use a conservative allowlist; declared byte sizes are checked during content resolution and mismatches are not readable.
- Malformed historical metadata becomes a warning/status, not executable content.
- CORS is disabled unless `BIOREPORT_CORS_ORIGINS` is explicitly set to a comma-separated allowlist. `BIOREPORT_RATE_LIMIT_PER_MINUTE` enables a bounded per-client in-memory request window for `/api/*`; a production proxy should add distributed limits as needed.
- The current API adapter accepts an optional `BIOREPORT_API_TOKEN`; configured tokens are required on `/api/*`, and the server helper refuses non-loopback binds without one.
- `BIOREPORT_ALLOWED_PROJECTS` can restrict the API to exact project IDs. Unauthorized reports use the same not-found response as unknown reports to reduce enumeration; a project query parameter is only a filter and never grants access.
- Scientific validation rejects script/iframe markup, `javascript:` URLs, and Quarto include directives before interpretation persistence.
- Interpretation and conversation persistence redact common POSIX/Windows local absolute paths before storing or returning text.
- SSE event payloads apply the same local-path redaction, including exception messages, before JSON framing.
