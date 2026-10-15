#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
报告溯源信息（Provenance）构建模块。

自动记录报告的生成引擎版本、生成时间、渲染模块、输出布局/格式、
分析流程版本以及输入文件 SHA256 指纹，服务科研可复现与合规审计。
所有字段均为运行时自动采集，禁止手填。
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import bioreport

# 大文件分块读取的块大小（64 KiB），避免整文件载入内存。
_CHUNK_SIZE = 64 * 1024


def _sha256_file(path: Path) -> str:
    """分块读取文件并计算 SHA256，避免大文件占用过多内存。"""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def input_checksums(config: dict) -> dict:
    """对 input_files 中真实存在的文件计算 SHA256 指纹。

    返回 {逻辑字段名: sha256}；目录（如 *_dir 结尾的键）与缺失文件自动跳过。
    """
    checksums = {}
    input_files = config.get("input_files", {})
    data_dir = input_files.get("data_dir")
    for key, value in input_files.items():
        if key == "data_dir" or not isinstance(value, str):
            continue
        path = Path(value)
        if not path.is_file() and data_dir and not path.is_absolute():
            # 未经过 load_config 解析的相对路径，回退到 data_dir 定位。
            candidate = Path(data_dir) / value
            if candidate.is_file():
                path = candidate
        if path.is_file():
            checksums[key] = _sha256_file(path)
    return checksums


def build_provenance(config: dict, sections: list) -> dict:
    """组装报告溯源信息字典，字段全部自动生成。"""
    report = config.get("report", {})
    project = config.get("project", {})

    output_format = report.get("output_format", "html")
    if isinstance(output_format, str):
        output_format = [output_format]

    provenance = {
        "project_id": project["project_id"],
        "bioreport_version": bioreport.__version__,
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "rendered_modules": list(sections),
        "layout": report.get("layout", "single"),
        "output_format": list(output_format),
        "input_checksums": input_checksums(config),
    }
    pipeline_version = project.get("pipeline_version")
    if pipeline_version:
        provenance["pipeline_version"] = pipeline_version
    return provenance


def write_provenance(provenance: dict, qmd_dir: Path) -> Path:
    """将溯源信息写入临时项目的 qmd/provenance.json，供 QMD 页面读取。"""
    qmd_dir.mkdir(parents=True, exist_ok=True)
    target = qmd_dir / "provenance.json"
    target.write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return target
