"""Conservative local server entry point; no public bind by default."""

from __future__ import annotations

import ipaddress
import argparse
import os
from pathlib import Path
from typing import Any

from .api import create_app


def main(argv: list[str] | None = None) -> None:
    """Start the Workspace API through the controlled bind policy."""
    parser = argparse.ArgumentParser(description="Run the BioReport Workspace API")
    parser.add_argument("--db", default=None, help="SQLite runs database (defaults to BIOREPORT_DB)")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (non-loopback requires BIOREPORT_API_TOKEN)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port")
    args = parser.parse_args(argv)
    serve(db_path=args.db, host=args.host, port=args.port)


def build_app(db_path: str | Path | None = None) -> Any:
    return create_app(str(db_path or os.environ.get("BIOREPORT_DB", Path.home() / ".bioreport" / "runs.db")))


def serve(*, db_path: str | Path | None = None, host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run uvicorn only after enforcing the local/authenticated bind policy."""
    token = os.environ.get("BIOREPORT_API_TOKEN", "")
    address = ipaddress.ip_address(host)
    if not address.is_loopback and not token:
        raise RuntimeError("Non-loopback API binding requires BIOREPORT_API_TOKEN")
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Install uvicorn to run the Workspace API") from exc
    uvicorn.run(build_app(db_path), host=host, port=int(port), log_level="info")


if __name__ == "__main__":  # pragma: no cover - exercised by the runtime command
    main()

