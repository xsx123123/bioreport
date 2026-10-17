"""Scientific consistency checks for structured interpretation output."""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    errors: list[str]
    checked_numbers: list[float]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ScientificValidator:
    def validate(self, output: dict[str, Any], evidence: dict[str, Any]) -> ValidationResult:
        errors: list[str] = []
        refs = {item.get("source_id") for item in evidence.get("tables", []) if isinstance(item, dict)}
        refs.update(item.get("figure_id") for item in evidence.get("figures", []) if isinstance(item, dict))
        if output.get("module_id") != evidence.get("module_id"):
            errors.append("MODULE_MISMATCH")
        if output.get("comparison") != evidence.get("comparison"):
            errors.append("COMPARISON_MISMATCH")
        checked: list[float] = []
        for section in ("observations", "interpretations", "hypotheses"):
            entries = output.get(section, [])
            if not isinstance(entries, list):
                errors.append(f"INVALID_{section.upper()}")
                continue
            for entry in entries:
                if not isinstance(entry, dict) or not isinstance(entry.get("text"), str):
                    errors.append(f"INVALID_{section.upper()}_ENTRY")
                    continue
                if re.search(r"<\s*script\b|javascript\s*:|\{\{<\s*include|<\s*iframe\b", entry["text"], re.IGNORECASE):
                    errors.append("UNSAFE_MARKUP")
                entry_refs = entry.get("evidence_refs", [])
                if (
                    not isinstance(entry_refs, list)
                    or any(
                        not isinstance(ref, str)
                        or ":" not in ref
                        or ref.split(":", 1)[-1] not in refs
                        for ref in entry_refs
                    )
                ):
                    errors.append("UNKNOWN_EVIDENCE_REF")
                for token in re.findall(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", entry["text"]):
                    checked.append(float(token))
        stats = evidence.get("statistics", {})
        allowed: set[float] = set()

        def collect_numbers(value: Any) -> None:
            if isinstance(value, bool):
                return
            if isinstance(value, (int, float)):
                allowed.add(float(value))
            elif isinstance(value, str) and re.fullmatch(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", value.strip()):
                allowed.add(float(value.strip()))
            elif isinstance(value, dict):
                for child in value.values():
                    collect_numbers(child)
            elif isinstance(value, list):
                for child in value:
                    collect_numbers(child)

        collect_numbers(evidence.get("statistics", {}))
        collect_numbers(evidence.get("tables", []))
        collect_numbers(evidence.get("figures", []))
        text_values = [output.get("summary", "")]
        if isinstance(output.get("limitations", []), list):
            text_values.extend(output["limitations"])
        for text in text_values:
            if isinstance(text, str):
                for token in re.findall(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", text):
                    checked.append(float(token))
        if any(number not in allowed for number in checked):
            errors.append("UNSUPPORTED_NUMERIC_CLAIM")
        if not isinstance(output.get("limitations", []), list):
            errors.append("LIMITATIONS_REQUIRED")
        summary = output.get("summary", "")
        if not isinstance(summary, str) or re.search(r"<\s*script\b|javascript\s*:|\{\{<\s*include|<\s*iframe\b", summary, re.IGNORECASE):
            errors.append("UNSAFE_MARKUP")
        return ValidationResult(valid=not errors, errors=sorted(set(errors)), checked_numbers=checked)
