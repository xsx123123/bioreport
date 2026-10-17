# Workspace v1 baseline

The repository uses native SQLite in `bioreport/utils/run_db.py`; writes remain owned by the existing CLI and reads for Workspace use `bioreport.report_service.SQLiteReportRepository`. The current `runs` schema has no migration metadata before Workspace migration is explicitly invoked.

Current implementation evidence:

- Existing report generation, provenance, Quarto templates, and Registry remain in place.
- Workspace additions are isolated in `report_service.py`, `artifacts.py`, `ai/`, `db/`, `api.py`, `sse.py`, and `frontend/`.
- No production database or output directory was modified during tests.
- Base Python dependency metadata does not yet include FastAPI or frontend packages; FastAPI is optional at import time and the frontend declares its own npm dependencies.

Known environment gaps: no real LLM key was used, no Quarto-backed AI report was claimed, and browser automation could not complete in the restricted Chromium/Firefox/WebKit sandbox. The frontend typecheck and production build were run successfully with the repository's installed dependency cache.
