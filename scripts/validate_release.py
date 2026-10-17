#!/usr/bin/env python3
"""Validate that a release tag and the project version refer to the same release."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path


TAG_PATTERN = re.compile(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$")


def project_version() -> str:
    with Path("pyproject.toml").open("rb") as stream:
        return tomllib.load(stream)["project"]["version"]


def release_tag() -> str | None:
    ref_name = os.environ.get("RELEASE_TAG") or os.environ.get("GITHUB_REF_NAME")
    if ref_name and ref_name.startswith("v"):
        return ref_name
    result = subprocess.run(
        ["git", "tag", "--points-at", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    tags = [tag for tag in result.stdout.splitlines() if tag.startswith("v")]
    if len(tags) > 1:
        raise ValueError(f"HEAD has multiple v* tags: {', '.join(tags)}")
    return tags[0] if tags else None


def main() -> int:
    version = project_version()
    tag = release_tag()
    if tag is None:
        print(f"No release tag at HEAD; project version is {version}.")
        return 0
    if not TAG_PATTERN.fullmatch(tag) or tag[1:] != version:
        print(f"Release mismatch: tag={tag!r}, pyproject={version!r}", file=sys.stderr)
        return 1
    print(f"OK: {tag} matches pyproject.toml version {version}.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, ValueError) as exc:
        print(f"Release validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
