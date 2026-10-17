# BioReport Workspace frontend

This is the real API-backed React workspace shell for v1. It does not ship report fixtures or fake runs. Start the API on `127.0.0.1:8000`, then run:

```bash
npm install
npm run dev
```

The package versions are pinned in `package.json` for reproducible installs; the restricted validation environment uses its existing local npm cache.

The local API entry point is `python -m bioreport.api_server`; set `BIOREPORT_DB` to a copy or authorized local runs database and `BIOREPORT_TRUSTED_ROOT` to the approved report root when reports are outside `~/.bioreport`. Before enabling interpretation or conversation persistence, explicitly migrate the authorized database and retain its backup:

```bash
bioreport workspace-migrate --db /path/to/runs.db
```

It defaults to loopback and refuses a non-loopback bind unless `BIOREPORT_API_TOKEN` is configured. Use `--host` and `--port` to override the bind settings; this controlled entry point must be used for public or LAN deployment.

For a team deployment, set `BIOREPORT_ALLOWED_PROJECTS` to a comma-separated exact allowlist, `BIOREPORT_RATE_LIMIT_PER_MINUTE` to a positive per-client limit, and `BIOREPORT_CORS_ORIGINS` to explicit browser origins. These settings are server-side controls; a project query parameter is never an authorization grant.

`/api` is proxied to the local API in `vite.config.ts`. The screen intentionally shows unavailable evidence and missing output states rather than inventing content.

Selecting a registered module loads bounded evidence through its allowlisted API builder; DEG uses an explicit comparison, while samples/heatmap/enrichment/QC modules use their registered table preview. The detail view also lists Manifest-backed HTML/PDF artifacts and only enables links for available, hash-verified files. Unknown modules remain visible as unavailable.

The Agent panel also persists scoped conversation drafts through the conversation API. Interpretation generation follows the operation SSE stream and exposes its terminal status; the browser never receives provider credentials.
