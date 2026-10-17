"""Safe, manifest-backed artifact resolution for report consumers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterator


class ArtifactError(RuntimeError):
    code = "ARTIFACT_ERROR"


class ArtifactNotFound(ArtifactError):
    code = "ARTIFACT_NOT_FOUND"


class ArtifactForbidden(ArtifactError):
    code = "ARTIFACT_FORBIDDEN"


_ALLOWED_TYPES = {
    ".html": {"text/html"},
    ".htm": {"text/html"},
    ".pdf": {"application/pdf"},
    ".json": {"application/json", "text/json"},
    ".jsonl": {"application/json", "application/x-ndjson", "text/plain"},
    ".csv": {"text/csv", "text/plain"},
    ".tsv": {"text/tab-separated-values", "text/plain"},
    ".txt": {"text/plain"},
    ".png": {"image/png"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".svg": {"image/svg+xml"},
}

_DEFAULT_TYPES = {
    ".html": "text/html",
    ".htm": "text/html",
    ".pdf": "application/pdf",
    ".json": "application/json",
    ".jsonl": "application/x-ndjson",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".txt": "text/plain",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
}


def _allowed_type(path: Path, content_type: Any) -> bool:
    allowed = _ALLOWED_TYPES.get(path.suffix.lower())
    if not allowed:
        return False
    if content_type in (None, ""):
        return True
    declared = str(content_type).split(";", 1)[0].strip().lower()
    return declared in allowed


def _content_type(path: Path, declared: Any) -> str | None:
    if declared not in (None, ""):
        return str(declared).split(";", 1)[0].strip().lower()
    return _DEFAULT_TYPES.get(path.suffix.lower())


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: str
    role: str
    path: Path
    size_bytes: int | None
    sha256: str | None
    available: bool
    integrity: str
    content_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        # Filesystem paths are an internal resolver detail. API consumers use
        # the logical artifact_id and never receive local path disclosure.
        value.pop("path", None)
        return value


class ArtifactResolver:
    """Resolve only files declared by a report manifest under trusted roots."""

    def __init__(self, output_dir: str | Path, *, trusted_roots: list[str | Path] | None = None, max_bytes: int = 250_000_000):
        raw_output_dir = Path(output_dir).expanduser()
        self._output_was_symlink = raw_output_dir.is_symlink()
        self.output_dir = raw_output_dir.resolve()
        roots = trusted_roots if trusted_roots is not None else [self.output_dir]
        self.trusted_roots = tuple(Path(root).expanduser().resolve() for root in roots)
        self.max_bytes = max(1, min(int(max_bytes), 500_000_000))
        self._records: dict[str, ArtifactRecord] | None = None

    def _under_trusted_root(self, path: Path) -> bool:
        return any(path == root or root in path.parents for root in self.trusted_roots)

    def _manifest_records(self) -> dict[str, ArtifactRecord]:
        if self._output_was_symlink:
            return {}
        result: dict[str, ArtifactRecord] = {}
        # ``artifact-manifest`` is the generic registry; the report manifest is
        # the authoritative registration for the generated HTML/PDF itself.
        # Input manifests are intentionally excluded from browser downloads.
        manifest_names = ("artifact-manifest.json", "report-manifest.json")
        for manifest_name in manifest_names:
            manifest = self.output_dir / manifest_name
            try:
                if not manifest.is_file() or manifest.is_symlink() or manifest.stat().st_size > self.max_bytes:
                    continue
            except OSError:
                continue
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            entries = data.get("artifacts", data) if isinstance(data, dict) else data
            if not isinstance(entries, list) or len(entries) > 100_000:
                continue
            for index, entry in enumerate(entries):
                if not isinstance(entry, dict) or not entry.get("path"):
                    continue
                raw = Path(str(entry["path"]))
                base_id = str(entry.get("artifact_id") or entry.get("id") or entry.get("artifact") or f"artifact-{index}")
                artifact_id = base_id if base_id not in result else f"{manifest_name.removesuffix('.json')}:{base_id}"
                unresolved = self.output_dir / raw
                has_symlink_component = raw.is_absolute()
                if not has_symlink_component:
                    current = self.output_dir
                    for component in raw.parts:
                        current = current / component
                        if current.is_symlink():
                            has_symlink_component = True
                            break
                candidate = unresolved.resolve()
                if has_symlink_component or not self._under_trusted_root(candidate):
                    result[artifact_id] = ArtifactRecord(artifact_id, str(entry.get("role", "unknown")), candidate, None, None, False, "forbidden", entry.get("content_type"))
                    continue
                content_type = _content_type(raw, entry.get("content_type"))
                if not _allowed_type(raw, content_type):
                    result[artifact_id] = ArtifactRecord(artifact_id, str(entry.get("role", "unknown")), candidate, entry.get("size_bytes", entry.get("size")), entry.get("sha256"), False, "forbidden", content_type)
                    continue
                exists = candidate.is_file()
                declared_size = entry.get("size_bytes", entry.get("size"))
                result[artifact_id] = ArtifactRecord(artifact_id, str(entry.get("role", "unknown")), candidate, declared_size, entry.get("sha256"), exists, "unverified" if exists else "missing", content_type)
        return result

    def records(self, *, verify: bool = True) -> list[ArtifactRecord]:
        if self._records is None:
            self._records = self._manifest_records()
        if not verify:
            return list(self._records.values())
        return [self.get(artifact_id) for artifact_id in self._records]

    def manifest_snapshot(self) -> dict[str, Any]:
        """Read known delivery manifests and redact filesystem paths."""
        result: dict[str, Any] = {}
        if self._output_was_symlink:
            return {name: {"availability": "forbidden"} for name in ("report", "input", "artifact", "reproduction", "provenance-validation")}
        for name in ("report", "input", "artifact", "reproduction", "provenance-validation"):
            manifest = self.output_dir / f"{name}-manifest.json" if name != "provenance-validation" else self.output_dir / "provenance-validation.json"
            try:
                unavailable = not manifest.is_file() or manifest.is_symlink() or manifest.stat().st_size > self.max_bytes
            except OSError:
                unavailable = True
            if unavailable:
                result[name] = {"availability": "missing"}
                continue
            try:
                value = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                result[name] = {"availability": "invalid"}
                continue
            if not isinstance(value, dict):
                result[name] = {"availability": "invalid"}
                continue
            safe = {key: value[key] for key in ("project_id", "generated_at", "report_version", "status", "checked_artifacts", "errors", "python", "quarto", "typst", "packages", "bioreport") if key in value}
            entries = value.get("artifacts")
            if isinstance(entries, list) and len(entries) <= 100_000:
                safe["artifacts"] = [{key: entry.get(key) for key in ("artifact", "artifact_id", "role", "sha256", "size", "content_type") if entry.get(key) is not None} for entry in entries if isinstance(entry, dict)]
            elif entries is not None:
                result[name] = {"availability": "invalid", "warnings": ["MANIFEST_ENTRY_LIMIT_REACHED"]}
                continue
            safe["availability"] = "available"
            result[name] = safe
        return result

    def get(self, artifact_id: str) -> ArtifactRecord:
        if self._records is None:
            self._records = self._manifest_records()
        try:
            record = self._records[artifact_id]
        except KeyError as exc:
            raise ArtifactNotFound(artifact_id) from exc
        if record.integrity == "forbidden":
            return record
        if not self._under_trusted_root(record.path) or record.path.is_symlink():
            return ArtifactRecord(**{**asdict(record), "available": False, "integrity": "forbidden"})
        if not record.path.is_file():
            return record
        if record.path.stat().st_size > self.max_bytes:
            return ArtifactRecord(**{**asdict(record), "integrity": "too_large"})
        actual_size = record.path.stat().st_size
        declared_size = record.size_bytes
        if declared_size is not None:
            try:
                if int(declared_size) != actual_size:
                    return ArtifactRecord(**{**asdict(record), "available": True, "integrity": "mismatch", "size_bytes": actual_size})
            except (TypeError, ValueError):
                return ArtifactRecord(**{**asdict(record), "available": True, "integrity": "mismatch", "size_bytes": actual_size})
        digest_builder = hashlib.sha256()
        with record.path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest_builder.update(chunk)
        digest = digest_builder.hexdigest()
        integrity = "verified" if not record.sha256 or digest == record.sha256 else "mismatch"
        return ArtifactRecord(**{**asdict(record), "available": True, "integrity": integrity, "size_bytes": actual_size, "sha256": record.sha256 or digest})

    def read_jsonl(self, artifact_id: str, *, max_lines: int = 100_000) -> Iterator[dict[str, Any]]:
        record = self.get(artifact_id)
        if record.integrity in {"mismatch", "forbidden", "too_large"} or not record.available:
            raise ArtifactError(f"Artifact {artifact_id} is not readable: {record.integrity}")
        try:
            with record.path.open("r", encoding="utf-8") as handle:
                for index, line in enumerate(handle):
                    if index >= max_lines:
                        raise ArtifactError(f"Artifact {artifact_id} exceeds line limit")
                    value = json.loads(line)
                    if isinstance(value, dict):
                        yield value
        except (OSError, ValueError) as exc:
            raise ArtifactError(f"Invalid JSONL artifact {artifact_id}") from exc
