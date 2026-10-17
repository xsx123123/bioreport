# BioReport Workspace v1 architecture

```mermaid
flowchart LR
  CLI[BioReport CLI] --> SVC[Shared Python services]
  DB[(SQLite runs)] --> SVC
  FS[Manifest and report files] --> AR[ArtifactResolver]
  SVC --> AR
  AR --> EV[EvidenceBuilder]
  EV --> AG[InterpretationOrchestrator]
  AG --> VAL[ScientificValidator]
  VAL --> IR[(Interpretation tables)]
  API[FastAPI loopback API] --> SVC
  UI[React Workspace] --> API
```

```mermaid
erDiagram
  RUNS ||--o{ INTERPRETATIONS : contains
  RUNS ||--o{ CONVERSATION_SESSIONS : opens
  CONVERSATION_SESSIONS ||--o{ CONVERSATION_MESSAGES : contains
  RUNS { integer id string project_id string status }
  INTERPRETATIONS { string id integer run_id string module_id string evidence_hash string status }
  CONVERSATION_SESSIONS { string id integer run_id string evidence_hash }
  CONVERSATION_MESSAGES { integer id string session_id string role }
```

```mermaid
sequenceDiagram
  participant U as Workspace
  participant A as API
  participant R as ReportRepository
  participant E as EvidenceBuilder
  participant I as Agent
  U->>A: GET reports
  A->>R: read-only query
  U->>A: request module interpretation
  A->>E: build bounded evidence
  E-->>I: canonical evidence + hashes
  I-->>A: structured output
  A-->>U: SSE draft/validated events
```

The database stores identity, status, hashes, and versioned interpretation metadata. Large report content remains in trusted filesystem roots and is accessed by logical artifact IDs.
