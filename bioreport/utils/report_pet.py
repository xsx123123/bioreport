"""Build the optional Taotao desktop pet for self-contained HTML reports."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any


_PET_STATES = {
    "idle": ("idle.gif", "image/gif"),
    "waiting": ("waiting.gif", "image/gif"),
    "waving": ("waving.gif", "image/gif"),
    "jumping": ("jumping.gif", "image/gif"),
    "running": ("running.gif", "image/gif"),
    "runningLeft": ("running-left.gif", "image/gif"),
    "runningRight": ("running-right.gif", "image/gif"),
    "still": ("still-01.png", "image/png"),
}


def pet_settings(config: dict[str, Any]) -> dict[str, Any]:
    """Return validated report.pet settings, disabled unless explicitly enabled."""
    report = config.get("report", {})
    if report is None:
        report = {}
    if not isinstance(report, dict):
        raise ValueError("report must be an object")
    raw = report.get("pet", {})
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("report.pet must be an object")

    enabled = raw.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ValueError("report.pet.enabled must be a boolean")
    size = raw.get("size", 144)
    if isinstance(size, bool) or not isinstance(size, int) or not 96 <= size <= 240:
        raise ValueError("report.pet.size must be an integer between 96 and 240")
    return {"enabled": enabled, "size": size}


def build_pet_context(config: dict[str, Any], template_dir: Path, formats: list[str]) -> dict[str, Any]:
    """Encode Taotao previews for inline use in a self-contained HTML document."""
    settings = pet_settings(config)
    if not settings["enabled"] or "html" not in formats:
        return {"enabled": False}

    preview_dir = template_dir / "Taotao" / "final" / "previews"
    assets = {}
    for state, (filename, media_type) in _PET_STATES.items():
        path = preview_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"Taotao pet asset is missing: {path}")
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        assets[state] = f"data:{media_type};base64,{encoded}"
    return {
        "enabled": True,
        "name": "桃桃",
        "size": settings["size"],
        "height": round(settings["size"] * 208 / 192),
        "assets": assets,
    }


def stage_pet_template(environment, template_dir: Path, pet: dict[str, Any]) -> None:
    """Render the optional pet include into the temporary Quarto project."""
    if not pet.get("enabled"):
        return
    target = template_dir / "theme" / "report-pet.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        environment.get_template("theme/report-pet.html.j2").render(pet=pet),
        encoding="utf-8",
    )
