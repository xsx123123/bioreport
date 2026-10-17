# CygnusX BioOps integration contract

BioOps calls the authenticated Workspace API and never opens BioReport's SQLite file directly. The service should be bound to loopback for local use; a team deployment must put it behind a trusted proxy and project authorization.

```bash
curl -H "Authorization: Bearer $BIOREPORT_API_TOKEN" \
  'http://127.0.0.1:8000/api/v1/reports?project=PRJ&limit=20'

curl -H "Authorization: Bearer $BIOREPORT_API_TOKEN" \
  'http://127.0.0.1:8000/api/v1/reports/49/modules'

curl -X POST -H "Authorization: Bearer $BIOREPORT_API_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"module_id":"rna.results.deg","comparison":"2_vs_1"}' \
  'http://127.0.0.1:8000/api/v1/reports/49/interpretations'
```

The current local adapter exposes the contract and supports bearer-token validation plus exact project allowlisting through server configuration. A production deployment still needs an identity-aware proxy or JWT verifier to map each caller to its allowed project set; do not treat one shared token as per-user authorization.
