"""Single-agent orchestration with a deterministic mock path for local E2E."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Callable

from .validator import ScientificValidator, ValidationResult


_POSIX_LOCAL_PATH = re.compile(r"(?<![\w:])/(?:home|tmp|workspace|data|var|mnt|opt)/[^\s<>\"']+")
_WINDOWS_LOCAL_PATH = re.compile(r"(?<!\w)[A-Za-z]:\\[^\s<>\"']+")


def redact_local_paths(value: Any) -> Any:
    """Redact common local absolute paths before text reaches persistence/UI."""
    if isinstance(value, str):
        value = _POSIX_LOCAL_PATH.sub("<local-path-redacted>", value)
        return _WINDOWS_LOCAL_PATH.sub("<local-path-redacted>", value)
    if isinstance(value, list):
        return [redact_local_paths(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_local_paths(item) for key, item in value.items()}
    return value


@dataclass(frozen=True)
class InterpretationResult:
    output: dict[str, Any]
    validation: ValidationResult
    provider: str
    model: str


class InterpretationOrchestrator:
    def __init__(self, *, validator: ScientificValidator | None = None):
        self.validator = validator or ScientificValidator()

    def interpret(self, evidence: dict[str, Any], *, provider: str = "mock", model: str = "deterministic-v1", generator: Callable[[dict[str, Any]], dict[str, Any]] | None = None) -> InterpretationResult:
        stats = evidence.get("statistics", {})
        source_refs = [
            item.get("source_id") for item in evidence.get("tables", [])
            if isinstance(item, dict) and isinstance(item.get("source_id"), str)
        ]
        source_refs.extend(
            item.get("figure_id") for item in evidence.get("figures", [])
            if isinstance(item, dict) and isinstance(item.get("figure_id"), str)
        )
        primary_ref = source_refs[0] if source_refs else None
        module_id = evidence.get("module_id")
        if module_id == "rna.results.deg":
            observation = f"Detected {stats.get('up', 0)} up-regulated and {stats.get('down', 0)} down-regulated genes under the configured raw P threshold."
        else:
            observation = "Evidence was prepared from the registered module source; this deterministic draft does not infer biological significance."
        output = generator(evidence) if generator else {
            "module_id": module_id,
            "comparison": evidence.get("comparison"),
            "observations": [{"text": observation, "evidence_refs": [f"source:{primary_ref}"] if primary_ref else []}],
            "interpretations": [],
            "hypotheses": [],
            "limitations": ["This deterministic result is a statistical summary, not a causal biological conclusion."],
            "summary": "Deterministic evidence summary.",
        }
        output = redact_local_paths(output)
        validation = self.validator.validate(output, evidence)
        return InterpretationResult(output=output, validation=validation, provider=provider, model=model)
