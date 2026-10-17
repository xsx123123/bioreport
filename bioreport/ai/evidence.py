"""Deterministic, privacy-minimised evidence builders for RNA modules."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class EvidencePackage:
    schema_version: str
    project_id: str
    run_id: int | None
    execution_id: str | None
    module_id: str
    comparison: str | None
    metadata: dict[str, Any]
    statistics: dict[str, Any]
    tables: list[dict[str, Any]]
    figures: list[dict[str, Any]]
    source_artifacts: list[dict[str, Any]]
    evidence_hash: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _number(row: dict[str, str], names: tuple[str, ...]) -> float | None:
    for name in names:
        value = row.get(name)
        if value in (None, "", "NA", "NaN", "nan"):
            continue
        try:
            return float(value)
        except ValueError:
            continue
    return None


class EvidenceBuilder:
    """Build evidence from a bounded result table below a trusted directory."""

    def __init__(self, trusted_root: str | Path, *, top_n: int = 10, max_rows: int = 100_000):
        raw_root = Path(trusted_root).expanduser()
        self._root_was_symlink = raw_root.is_symlink()
        self.root = raw_root.resolve()
        self.top_n = max(1, min(int(top_n), 100))
        self.max_rows = max(1, min(int(max_rows), 1_000_000))

    def _safe_candidate(self, candidate: Path) -> Path | None:
        if self._root_was_symlink:
            return None
        raw = Path(os.path.abspath(str(candidate)))
        try:
            raw_relative = raw.relative_to(self.root)
        except ValueError:
            return None
        current = self.root
        for component in raw_relative.parts:
            current = current / component
            if current.is_symlink():
                return None
        resolved = raw.resolve()
        if resolved != self.root and self.root not in resolved.parents:
            return None
        return resolved

    def _source(self, comparison: str) -> Path:
        candidates = tuple(
            directory / filename
            for directory in (self.root, self.root / "res" / "DEG", self.root / "DEG", self.root / "results" / "DEG")
            for filename in (f"{comparison}_DEG.csv", f"{comparison}.csv", f"{comparison}_deg.csv")
        ) + (self.root / comparison / "DEG.csv",)
        for candidate in candidates:
            resolved = self._safe_candidate(candidate)
            if resolved is not None and resolved.is_file():
                return resolved
        raise FileNotFoundError(f"DEG evidence source unavailable for comparison {comparison}")

    def _figure_records(self, comparison: str) -> tuple[list[dict[str, Any]], list[str]]:
        """Register only convention-based report figures, without exposing paths."""
        safe_comparison = str(comparison).replace("/", "-").replace("\\", "-")
        names = (
            f"{safe_comparison}_volcano.png", f"{safe_comparison}_volcano.svg",
            f"volcano_{safe_comparison}.png", f"volcano_{safe_comparison}.svg",
            f"figures/{safe_comparison}_volcano.png", f"figures/{safe_comparison}_volcano.svg",
            f"supplementary/{safe_comparison}_volcano.png", f"supplementary/{safe_comparison}_volcano.svg",
        )
        records: list[dict[str, Any]] = []
        warnings: list[str] = []
        seen: set[Path] = set()
        for relative in names:
            candidate = self._safe_candidate(self.root / relative)
            if candidate is None or candidate in seen or not candidate.is_file():
                continue
            seen.add(candidate)
            size = candidate.stat().st_size
            if size > 50 * 1024 * 1024:
                warnings.append("FIGURE_TOO_LARGE")
                continue
            suffix = candidate.suffix.lower()
            records.append({
                "figure_id": f"deg_{safe_comparison}_volcano",
                "content_type": "image/svg+xml" if suffix == ".svg" else "image/png",
                "sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
                "size": size,
            })
        if not records:
            warnings.append("FIGURE_UNAVAILABLE")
        return records, sorted(set(warnings))

    def build_deg(
        self,
        *,
        project_id: str,
        comparison: str,
        run_id: int | None = None,
        execution_id: str | None = None,
        pvalue_threshold: float = 0.05,
        log2fc_threshold: float = 1.0,
    ) -> EvidencePackage:
        source = self._source(comparison)
        rows: list[dict[str, Any]] = []
        warnings: list[str] = []
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for index, raw in enumerate(reader):
                if index >= self.max_rows:
                    warnings.append("ROW_LIMIT_REACHED")
                    break
                logfc = _number(raw, ("log2FoldChange", "log2FC", "logFC"))
                pvalue = _number(raw, ("pvalue", "p_value", "PValue"))
                padj = _number(raw, ("padj", "p.adjust", "FDR", "fdr"))
                symbol = next((raw.get(name) for name in ("symbol", "Symbol", "gene", "Gene", "GeneID") if raw.get(name)), None)
                if logfc is None or pvalue is None:
                    continue
                rows.append({"symbol": str(symbol or f"row_{index + 1}"), "log2FC": logfc, "pvalue": pvalue, "padj": padj})
        up = sum(row["log2FC"] > log2fc_threshold and row["pvalue"] < pvalue_threshold for row in rows)
        down = sum(row["log2FC"] < -log2fc_threshold and row["pvalue"] < pvalue_threshold for row in rows)
        top = sorted(rows, key=lambda row: (row["pvalue"], -abs(row["log2FC"])))[: self.top_n]
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        figures, figure_warnings = self._figure_records(comparison)
        warnings.extend(figure_warnings)
        payload = {
            "schema_version": "1.0",
            "project_id": project_id,
            "run_id": run_id,
            "execution_id": execution_id,
            "module_id": "rna.results.deg",
            "comparison": comparison,
            "metadata": {},
            "statistics": {"total_rows": len(rows), "up": up, "down": down, "thresholds": {"pvalue_type": "raw", "pvalue_lt": pvalue_threshold, "abs_log2fc_gt": log2fc_threshold}},
            "tables": [{"source_id": f"deg_{comparison}", "columns": ["symbol", "log2FC", "pvalue", "padj"], "rows": top, "row_limit": self.top_n}],
            "figures": figures,
            "source_artifacts": [{"source_id": f"deg_{comparison}", "sha256": source_hash}],
            "warnings": warnings,
        }
        evidence_hash = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
        return EvidencePackage(**payload, evidence_hash=evidence_hash)

    def build_table_preview(
        self,
        *,
        project_id: str,
        module_id: str,
        source: str | Path,
        run_id: int | None = None,
        columns: tuple[str, ...] = (),
        row_limit: int = 20,
    ) -> EvidencePackage:
        """Build a bounded preview for non-DEG modules without accepting matrix dumps."""
        if module_id == "rna.results.matrix":
            raise ValueError("FULL_MATRIX_EVIDENCE_FORBIDDEN")
        allowed = {"rna.results.samples", "rna.results.enrichment", "rna.qc.fastp", "rna.qc.screen", "rna.qc.qualimap", "rna.qc.star"}
        if module_id not in allowed:
            raise ValueError("UNSUPPORTED_EVIDENCE_MODULE")
        candidate = self._safe_candidate(Path(source).expanduser())
        if candidate is None:
            raise PermissionError("EVIDENCE_SOURCE_OUTSIDE_TRUSTED_ROOT")
        if not candidate.is_file():
            raise FileNotFoundError(candidate)
        selected: list[dict[str, Any]] = []
        with candidate.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            available = tuple(reader.fieldnames or ())
            requested = tuple(column for column in columns if column in available) or available[:12]
            for index, raw in enumerate(reader):
                if index >= max(1, min(int(row_limit), 100)):
                    break
                selected.append({column: raw.get(column) for column in requested})
        payload = {
            "schema_version": "1.0", "project_id": project_id, "run_id": run_id, "execution_id": None,
            "module_id": module_id, "comparison": None, "metadata": {},
            "statistics": {"row_count_preview": len(selected), "source_row_limit": max(1, min(int(row_limit), 100))},
            "tables": [{"source_id": f"{module_id}:preview", "columns": list(requested), "rows": selected, "row_limit": len(selected)}],
            "figures": [], "source_artifacts": [{"source_id": f"{module_id}:preview", "sha256": hashlib.sha256(candidate.read_bytes()).hexdigest()}], "warnings": [],
        }
        digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
        return EvidencePackage(**payload, evidence_hash=digest)

    def build_registered(
        self,
        *,
        project_id: str,
        module_id: str,
        run_id: int | None = None,
        row_limit: int = 20,
    ) -> EvidencePackage:
        """Build a bounded preview from a module-specific, fixed filename allowlist.

        The caller never supplies a path. Missing source files remain an explicit
        unavailable state at the API boundary rather than being inferred from a
        similarly named artifact.
        """
        candidates = {
            "rna.results.samples": ("samples.csv", "sample_metadata.csv", "results/samples.csv", "res/samples.csv"),
            "rna.results.heatmap": ("heatmap.csv", "hvg.csv", "results/heatmap.csv", "res/hvg.csv"),
            "rna.results.enrichment": ("enrichment.csv", "go.csv", "results/enrichment.csv", "res/enrichment.csv"),
            "rna.qc.fastp": ("fastp.csv", "qc/fastp.csv", "results/fastp.csv"),
            "rna.qc.screen": ("fastq_screen.csv", "qc/fastq_screen.csv", "results/fastq_screen.csv"),
            "rna.qc.qualimap": ("qualimap.csv", "qc/qualimap.csv", "results/qualimap.csv"),
            "rna.qc.star": ("star.csv", "qc/star.csv", "results/star.csv"),
        }
        if module_id not in candidates:
            if module_id == "rna.results.matrix":
                raise ValueError("FULL_MATRIX_EVIDENCE_FORBIDDEN")
            raise ValueError("UNSUPPORTED_EVIDENCE_MODULE")
        for relative in candidates[module_id]:
            source = self.root / relative
            if source.is_file() and not source.is_symlink():
                return self.build_table_preview(project_id=project_id, module_id=module_id, source=source, run_id=run_id, row_limit=row_limit)
        raise FileNotFoundError(f"Evidence source unavailable for module {module_id}")
