# Workspace v1 API contract

The running FastAPI application is the executable OpenAPI source (`app.openapi()`); the following 3.1 document is the stable integration summary and uses the same paths and security names.

```yaml
openapi: 3.1.0
info:
  title: BioReport Workspace API
  version: "1"
servers:
  - url: http://127.0.0.1:8000
security:
  - bearerAuth: []
paths:
  /api/v1/reports:
    get:
      parameters:
        - {name: project, in: query, schema: {type: string}}
        - {name: status, in: query, schema: {type: string}}
        - {name: limit, in: query, schema: {type: integer, minimum: 1, maximum: 200, default: 50}}
        - {name: cursor, in: query, schema: {type: integer, minimum: 1}}
      responses: {"200": {description: Report page}, "503": {description: Database unavailable}}
  /api/v1/reports/{run_id}:
    get:
      parameters: [{name: run_id, in: path, required: true, schema: {type: integer}}]
      responses: {"200": {description: Report summary}, "404": {description: Not found}}
  /api/v1/reports/{run_id}/modules/{module_id}/evidence:
    get:
      parameters:
        - {name: run_id, in: path, required: true, schema: {type: integer}}
        - {name: module_id, in: path, required: true, schema: {type: string}}
        - {name: comparison, in: query, schema: {type: string}}
      responses: {"200": {description: Evidence package or explicit unavailable/forbidden state}}
  /api/v1/reports/{run_id}/artifacts/{artifact_id}/content:
    get:
      parameters:
        - {name: run_id, in: path, required: true, schema: {type: integer}}
        - {name: artifact_id, in: path, required: true, schema: {type: string}}
      responses: {"200": {description: Inline verified artifact}, "404": {description: Missing or unverifiable artifact}}
  /api/v1/reports/{run_id}/interpretations:
    get: {responses: {"200": {description: Immutable interpretation versions}}}
    post:
      parameters: [{name: Idempotency-Key, in: header, schema: {type: string, minLength: 1, maxLength: 128}}]
      requestBody: {required: true, content: {application/json: {schema: {$ref: '#/components/schemas/InterpretationRequest'}}}}
      responses: {"200": {description: Validated deterministic interpretation}, "409": {description: Idempotency key conflict}}
  /api/v1/conversations:
    post: {requestBody: {required: true}, responses: {"200": {description: Conversation session}}}
  /api/v1/conversations/{session_id}/messages:
    post: {requestBody: {required: true}, responses: {"200": {description: Stored draft response}}}
  /api/v1/operations/{operation_id}/events:
    get: {responses: {"200": {description: text/event-stream}}}
  /api/v1/operations/{operation_id}/cancel:
    post: {responses: {"200": {description: Idempotent terminal operation state}}}
components:
  securitySchemes:
    bearerAuth: {type: http, scheme: bearer}
  schemas:
    InterpretationRequest:
      type: object
      required: [module_id, comparison]
      properties:
        module_id: {type: string, example: rna.results.deg}
        comparison: {type: string, example: 2_vs_1}
        top_n: {type: integer, minimum: 1, maximum: 100, default: 10}
```

The backend service layer is the source of truth for the optional FastAPI adapter.
The adapter exposes:

## Local HTTP examples

Start the controlled server on loopback. Set `BIOREPORT_API_TOKEN` before using a non-loopback bind; do not expose an unauthenticated instance.

```bash
BIOREPORT_DB=/path/to/runs.db \
BIOREPORT_TRUSTED_ROOT=/approved/report/root \
BIOREPORT_API_TOKEN='local-development-token' \
python -m bioreport.api_server --host 127.0.0.1 --port 8000
```

```bash
TOKEN='local-development-token'

# Browse the history page and select a run ID.
curl -fsS -H "Authorization: Bearer $TOKEN" \
  'http://127.0.0.1:8000/api/v1/reports?limit=20'

# Read bounded evidence; DEG requires a comparison, while registered preview
# modules use their server-side filename allowlist.
curl -fsS -H "Authorization: Bearer $TOKEN" \
  'http://127.0.0.1:8000/api/v1/reports/49/modules/rna.results.deg/evidence?comparison=2_vs_1'

# Generate one immutable interpretation version. The key makes retries safe.
curl -fsS -X POST -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -H 'Idempotency-Key: run49-deg-2-v1' \
  -d '{"module_id":"rna.results.deg","comparison":"2_vs_1","top_n":10}' \
  'http://127.0.0.1:8000/api/v1/reports/49/interpretations'

# Follow the returned operation_id as an SSE stream.
curl -N -H "Authorization: Bearer $TOKEN" \
  'http://127.0.0.1:8000/api/v1/operations/OPERATION_ID/events'
```

Every request can send `X-Request-ID: <safe-client-id>` for correlation. The server returns that ID (or generates one) and never returns the configured API key or local filesystem paths.

`GET /api/reports`

Query parameters: `project`, `status`, `since`, `until`, `limit` (bounded to 200), and `cursor` (last report ID). The response is `{ "items": [...], "next_cursor": "..." | null }`.

Each report item includes `output_available` plus the non-path status axes `artifact_availability` (`AVAILABLE`, `PARTIAL`, `PATH_UNAVAILABLE`, `PERMISSION_DENIED`) and `manifest_status` (`AVAILABLE`, `MISSING`, `INVALID`, `UNVERIFIED`). A present output directory without a valid delivery Manifest is explicitly `PARTIAL/MISSING`; a present but malformed Manifest is `PARTIAL/INVALID`.

`GET /api/reports/{id}`

Returns one `ReportSummary`. Unknown IDs map to HTTP 404 with `{ "error": { "code": "REPORT_NOT_FOUND", "message": "..." } }`.

Database absence or read failure maps to HTTP 503 with code `DATABASE_UNAVAILABLE`. The adapter must not expose `output_dir`, `config_path`, or arbitrary filesystem paths as download targets. Artifact downloads must use a server-issued logical artifact ID.

Errors expose a stable `{code, message, request_id}` object under `error` and retain the same object under `detail` for the local frontend. Every response carries `X-Request-ID`; a valid incoming `X-Request-ID` is propagated, otherwise the server generates one. Unexpected exceptions return `INTERNAL_ERROR` without filesystem/provider details.

Team deployments may set `BIOREPORT_ALLOWED_PROJECTS` (exact comma-separated IDs), `BIOREPORT_RATE_LIMIT_PER_MINUTE`, and `BIOREPORT_CORS_ORIGINS`. The project allowlist is applied to every report, artifact, evidence, interpretation, conversation, and operation route; an incoming `project` query is only a filter. Rate limiting returns HTTP 429 with `RATE_LIMITED` and `Retry-After`.

`GET /api/v1/reports/{id}/artifacts/{artifact_id}/content`

Resolves the ID through `ArtifactResolver`, checks the manifest and integrity state, and streams only a trusted file. `forbidden`, `mismatch`, and `too_large` artifacts are metadata-visible but not readable.

`GET /api/v1/reports/{id}/artifacts` returns Manifest metadata without eagerly hashing large files; such entries are marked `unverified` until the content endpoint performs the bounded SHA-256 check. Generated HTML/PDF entries come from `report-manifest.json`; input manifests are not download sources.

`POST /api/v1/reports/{id}/interpretations` accepts an optional `Idempotency-Key` header (1-128 characters). Repeating the same key for the same report returns the original operation and interpretation response without creating another version; the local adapter retains at most 200 recent keys in memory.

`GET /api/v1/reports/{id}/provenance` returns redacted delivery-manifest availability, artifact roles, hashes, sizes, validation status, and runtime versions. Absolute paths and arbitrary manifest fields are omitted.

The module evidence endpoint returns `UNAVAILABLE/UNVERIFIED` for registered modules whose deterministic builder is not present yet, and `FORBIDDEN` for the full expression matrix. The interpretation endpoint accepts DEG comparisons plus the registered bounded preview modules when their source exists; the full expression matrix remains forbidden. These are valid evidence states, not fabricated results.

DEG evidence may include a fixed-name volcano figure reference with `figure_id`, `content_type`, `size`, and `sha256`; the resolver never returns its local path. If no registered figure is present, the evidence package carries `FIGURE_UNAVAILABLE` instead of inventing a figure.

The versioned routes currently implemented are `GET /api/v1/reports`, `GET /api/v1/reports/{id}`, `GET /api/v1/reports/{id}/modules`, `GET /api/v1/reports/{id}/modules/{module_id}/evidence`, `GET /api/v1/reports/{id}/artifacts`, `GET /api/v1/reports/{id}/provenance`, `GET /api/v1/reports/{id}/interpretations`, `POST /api/v1/reports/{id}/interpretations`, `GET /api/v1/interpretations/{interpretation_id}`, `POST/GET /api/v1/conversations`, `POST /api/v1/conversations/{session_id}/messages`, `GET /api/v1/operations/{operation_id}/events`, and `POST /api/v1/operations/{operation_id}/cancel`. They use the shared repository/evidence/persistence services and do not auto-migrate a database during a GET request. Conversation messages are stored separately from formal interpretations; the local deterministic adapter returns a clearly marked draft response and does not publish it as a validated report statement.

SSE uses `event` plus JSON `data` and permits `started`, `evidence_ready`, `token`, `tool_status`, `validated`, `completed`, `error`, and `cancelled`. A stream always has one terminal event. A successful deterministic interpretation stores an in-memory operation sequence keyed by `operation_id`; the durable interpretation row remains the source of truth. Unknown/expired operation IDs return a terminal `error` event.
