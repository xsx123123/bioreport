#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
离线运行数据库：将每次报告生成的溯源记录写入本地 SQLite。

所有信息自动提取自报告配置与 provenance 字典，无需人工填写；
数据库失败只告警、不阻断报告生成。可用环境变量 BIOREPORT_DB 覆盖库文件位置。
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    run_at TEXT NOT NULL,
    engine_version TEXT,
    pipeline_version TEXT,
    layout TEXT,
    output_format TEXT,
    modules TEXT,
    config_path TEXT,
    output_dir TEXT,
    status TEXT NOT NULL,
    input_checksums TEXT,
    created_at TEXT NOT NULL
)
"""


def default_db_path() -> Path:
    """本地数据库默认位置（可用 BIOREPORT_DB 环境变量覆盖）。"""
    override = os.environ.get("BIOREPORT_DB")
    if override:
        return Path(override)
    return Path.home() / ".bioreport" / "runs.db"


def record_run(
    db_path: Path,
    *,
    project_id: str,
    provenance: Dict[str, Any],
    config_path: str,
    output_dir: str,
    status: str,
) -> Optional[int]:
    """写入一条运行记录，返回行 id；任何异常由调用方决定是否上抛。"""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path))
    try:
        connection.execute(_SCHEMA)
        cursor = connection.execute(
            """
            INSERT INTO runs (
                project_id, run_at, engine_version, pipeline_version, layout,
                output_format, modules, config_path, output_dir, status,
                input_checksums, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                provenance.get("generated_at", ""),
                provenance.get("bioreport_version", ""),
                provenance.get("pipeline_version"),
                provenance.get("layout", ""),
                json.dumps(provenance.get("output_format", []), ensure_ascii=False),
                json.dumps(provenance.get("rendered_modules", []), ensure_ascii=False),
                config_path,
                output_dir,
                status,
                json.dumps(provenance.get("input_checksums", {}), ensure_ascii=False),
                datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            ),
        )
        connection.commit()
        return cursor.lastrowid
    finally:
        connection.close()


def fetch_runs(db_path: Path, project_id: Optional[str] = None) -> list:
    """读取运行记录（可按 project_id 过滤），供审计与测试使用。"""
    db_path = Path(db_path)
    if not db_path.is_file():
        return []
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    try:
        if project_id:
            cursor = connection.execute(
                "SELECT * FROM runs WHERE project_id = ? ORDER BY id", (project_id,)
            )
        else:
            cursor = connection.execute("SELECT * FROM runs ORDER BY id")
        return [dict(row) for row in cursor.fetchall()]
    finally:
        connection.close()
