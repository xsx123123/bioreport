# Workspace v1 UI handoff

The UI should consume the report query contract and render three states for each artifact: available, missing, and integrity failure. Unknown historical module IDs remain visible with an `unknown` badge and do not block the report detail view.

The first screen is the report history table with project, run time, status, module count, and output availability. Selecting a row opens report detail; module evidence and Agent actions must be driven by logical IDs returned by the API.

The current React shell implements this flow for `rna.results.deg`: selecting the module requests bounded evidence with an explicit comparison, displays the evidence hash/top table, loads saved interpretation versions, and triggers a deterministic validated interpretation. It exposes unavailable evidence as an explicit state rather than synthesizing a chart.

The provenance API supplies a redacted manifest snapshot for a provenance panel; the browser never receives `output_dir`, input absolute paths, or arbitrary manifest fields.
