"""Check the report router without requiring a browser or Jupyter sockets."""

from pathlib import Path
import shutil
import subprocess

import pytest


def test_single_file_page_router_handles_nav_clicks_and_history():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required to execute the navigation script")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [node, str(root / "tests/report_navigation.cjs")],
        cwd=root, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "Single-file navigation and visible flowchart checks passed" in result.stdout
