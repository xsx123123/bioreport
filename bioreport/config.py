#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified configuration loader for the RNA report module.

Supports both YAML (recommended) and legacy JSON configs.  The loaded config
is normalized so that downstream code can always access:

    config['report']      # report-level settings (title, sections, theme, ...)
    config['project']     # project metadata (client, species, genome, ...)
    config['stats']       # optional statistics
    config['input_files'] # input data paths
    config['analysis']    # analysis parameters
    config['ai']          # AI interpretation settings

The default config path is taken from the ``REPORT_CONFIG`` environment
variable, falling back to ``/app/configs/report_config.yaml``,
``/app/report_config.yaml`` and then ``/app/project_summary.json`` for backward compatibility.
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Union

import yaml
from jsonschema import Draft202012Validator


DEFAULT_CONFIG_PATHS = [
    os.environ.get("REPORT_CONFIG"),
    "/app/configs/report_config.yaml",
    "/app/report_config.yaml",
    "/app/project_summary.json",
]

SCHEMA_PATH = Path(__file__).with_name("report.schema.json")


def validate_config(data: Dict[str, Any], path: Path) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda error: list(map(str, error.absolute_path)))
    if errors:
        error = errors[0]
        field = ".".join(map(str, error.absolute_path)) or "root"
        raise ValueError(f"Invalid report config {path}, field {field}: {error.message}")


def _find_default_config() -> Optional[Path]:
    """Return the first existing default config path, or None."""
    for p in [os.environ.get("REPORT_CONFIG"), *DEFAULT_CONFIG_PATHS]:
        if not p:
            continue
        path = Path(p)
        if path.exists():
            return path
    return None


def _normalize_legacy_json(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert the old project_summary.json shape into the new unified shape.

    Old keys:
        project_meta -> project
        stats        -> stats
        input_files  -> input_files
    """
    normalized: Dict[str, Any] = {
        "report": {},
        "project": {},
        "stats": {},
        "input_files": {},
        "analysis": {},
        "ai": {},
    }

    if "project_meta" in data:
        normalized["project"] = data.get("project_meta", {})
    else:
        normalized["project"] = data.get("project", {})

    normalized["stats"] = data.get("stats", {})
    normalized["input_files"] = data.get("input_files", {})

    # If the legacy file already contains new unified keys, preserve them.
    for key in ("report", "analysis", "ai", "files"):
        if key in data:
            normalized[key] = data[key]

    return normalized


def load_config(
    config_path: Optional[Union[str, Path]] = None,
    require_exists: bool = True,
) -> Dict[str, Any]:
    """
    Load a unified report configuration from YAML or JSON.

    Args:
        config_path: Path to the config file. If None, use the default search
            order (REPORT_CONFIG env var -> /app/report_config.yaml ->
            /app/project_summary.json).
        require_exists: If True, raise FileNotFoundError when no config is found.

    Returns:
        Normalized config dict.
    """
    if config_path is None:
        path = _find_default_config()
    else:
        path = Path(config_path)

    if path is None:
        if require_exists:
            raise FileNotFoundError(
                "No report config found. Checked: "
                + ", ".join(p for p in DEFAULT_CONFIG_PATHS if p)
            )
        return _empty_config()

    path = Path(path)
    if not path.exists():
        if require_exists:
            raise FileNotFoundError(f"Config file not found: {path}")
        return _empty_config()

    try:
        with open(path, "r", encoding="utf-8") as f:
            if path.suffix.lower() in (".yaml", ".yml"):
                data = yaml.safe_load(f) or {}
            elif path.suffix.lower() == ".json":
                data = json.load(f)
            else:
                # Try YAML first, then JSON.
                content = f.read()
                try:
                    data = yaml.safe_load(content) or {}
                except yaml.YAMLError:
                    data = json.loads(content)
    except Exception as e:
        raise RuntimeError(f"Failed to parse config {path}: {e}") from e

    # Detect legacy JSON shape and normalize.
    if not isinstance(data, dict):
        raise ValueError(f"Report config must be a JSON/YAML object: {path}")
    legacy_format = "project_meta" in data and "report" not in data
    if legacy_format:
        data = _normalize_legacy_json(data)
    else:
        # Ensure all top-level sections exist.
        for key in ("report", "project", "stats", "input_files", "analysis", "ai"):
            data.setdefault(key, {})

    # project.project_id 是必填项：项目唯一标识，贯穿日志、离线数据库与报告溯源。
    # 放在 schema 校验之前，给出更友好的中文报错。
    project = data.get("project", {})
    if not isinstance(project, dict) or not isinstance(project.get("project_id"), str) or not project["project_id"].strip():
        raise ValueError(
            f"project.project_id 必须是非空字符串（项目唯一标识），请在 {path} 的 project 段添加，"
            '例如 "project_id": "PRJ-2026-001"'
        )

    validate_config(data, path)
    data["_legacy_format"] = legacy_format

    # One display count for both renderers. Legacy PDF knobs are accepted only
    # as a fallback when the canonical analysis setting is absent.
    enrichment = data['analysis'].setdefault('enrichment', {})
    pdf_options = data['report'].get('pdf', {})
    enrichment.setdefault('top_n', pdf_options.get('enrichment_top_n',
                                                 pdf_options.get('enrichment_rows', 12)))

    for key in ("report", "project", "stats", "input_files", "analysis", "ai"):
        if not isinstance(data[key], dict):
            raise ValueError(f"{key} must be an object in {path}")

    input_files = data["input_files"]
    if "data_dir" in input_files and (not isinstance(input_files["data_dir"], str) or not input_files["data_dir"]):
        raise ValueError(f"input_files.data_dir must be a nonempty path string in {path}")
    data_dir = Path(input_files["data_dir"]) if "data_dir" in input_files else path.resolve().parent
    if not data_dir.is_absolute():
        data_dir = path.resolve().parent / data_dir
    data_dir = data_dir.resolve()
    if "data_dir" in input_files:
        # 保留配置中书写的数据目录（交付目录），供报告展示；运行态仍用解析后的绝对路径。
        data["_data_dir"] = str(input_files["data_dir"])
        input_files["data_dir"] = str(data_dir)
    for key, value in input_files.items():
        if key == "data_dir":
            continue
        if not isinstance(value, str) or not value:
            raise ValueError(f"input_files.{key} must be a nonempty path string")
        file_path = Path(value)
        input_files[key] = str((file_path if file_path.is_absolute() else data_dir / file_path).resolve())

    files = data.get("files", {})
    if not isinstance(files, dict):
        raise ValueError(f"files must be an object in {path}")
    for key, value in files.items():
        if not isinstance(value, str) or not value:
            raise ValueError(f"files.{key} must be a nonempty path string")
        file_path = Path(value)
        files[key] = str((file_path if file_path.is_absolute() else data_dir / file_path).resolve())
    data["files"] = files

    prompt_file = data["ai"].get("prompt_file")
    if prompt_file:
        prompt_path = Path(prompt_file)
        data["ai"]["prompt_file"] = str(
            (prompt_path if prompt_path.is_absolute() else path.resolve().parent / prompt_path).resolve()
        )

    # Store the resolved config path for downstream use.
    data["_config_path"] = str(path.resolve())

    return data


def _empty_config() -> Dict[str, Any]:
    return {
        "report": {},
        "project": {},
        "stats": {},
        "input_files": {},
        "analysis": {},
        "ai": {},
    }


def get_report_setting(config: Dict[str, Any], key: str, default: Any = None) -> Any:
    """Helper to read a setting from the ``report`` section."""
    return config.get("report", {}).get(key, default)


def get_project_meta(config: Dict[str, Any], key: str, default: Any = None) -> Any:
    """Helper to read a setting from the ``project`` section."""
    return config.get("project", {}).get(key, default)


def get_input_path(
    config: Dict[str, Any], key: str, default: Optional[str] = None
) -> Optional[str]:
    """Helper to read an input file path and resolve it relative to data_dir."""
    raw = config.get("input_files", {}).get(key, default)
    if raw is None:
        return None
    raw = str(raw)
    if os.path.isabs(raw):
        return raw

    data_dir = config.get("input_files", {}).get("data_dir", ".")
    data_dir_path = Path(data_dir)
    if not data_dir_path.is_absolute():
        config_path = config.get("_config_path")
        if config_path:
            data_dir_path = Path(config_path).parent / data_dir_path

    resolved = (data_dir_path / raw).resolve()
    return str(resolved)


def resolve_path(config: Dict[str, Any], path_str: Optional[str]) -> Optional[Path]:
    """
    Resolve an arbitrary path using the same rules as get_input_path:
    absolute paths are kept, relative paths are resolved against data_dir
    (which itself is resolved against the config file directory).
    """
    if not path_str:
        return None
    path_str = str(path_str)
    if os.path.isabs(path_str):
        return Path(path_str).resolve()

    data_dir = config.get("input_files", {}).get("data_dir", ".")
    data_dir_path = Path(data_dir)
    if not data_dir_path.is_absolute():
        config_path = config.get("_config_path")
        if config_path:
            data_dir_path = Path(config_path).parent / data_dir_path

    return (data_dir_path / path_str).resolve()


def display_path(path_str: Optional[str], config: Optional[Dict[str, Any]] = None) -> str:
    """
    报告展示用路径：位于交付目录（input_files.data_dir）内的输入文件
    显示为相对交付目录的路径，避免暴露运行环境的绝对路径。

    data_dir 之外的路径保持原样（如显式给出的绝对路径），保证可核验性。
    """
    if not path_str:
        return ""
    path_str = str(path_str)
    if config is None:
        try:
            config = load_config()
        except Exception:
            # 找不到配置时无法判定交付目录；保留原路径，不在展示环节抛错。
            return path_str
    data_dir = config.get("input_files", {}).get("data_dir")
    if not data_dir:
        return path_str
    try:
        relative = Path(path_str).resolve().relative_to(Path(data_dir).resolve())
    except (ValueError, OSError):
        return path_str
    return relative.as_posix()


def project_file_stem(config: Dict[str, Any]) -> str:
    """
    报告交付文件的命名前缀：project_id 经文件名安全清洗后的形式。

    project_id 是必填项，贯穿日志、离线数据库与报告溯源；这里只做
    交付文件命名的安全化，不改变溯源与数据库中记录的原始值。
    空白与跨平台文件名非法字符折叠为连字符，例如
    ``PRJ-2026-001`` -> ``PRJ-2026-001``、``demo/样本 A`` -> ``demo-样本-A``。
    """
    project_id = str(config.get("project", {}).get("project_id", "")).strip()
    cleaned = re.sub(r'[\\/:*?"<>|\s]+', "-", project_id).strip("-.")
    return cleaned or "bioreport-report"


def report_artifact_name(config: Dict[str, Any], output_format: str) -> str:
    """报告交付文件名：<project_id>_report.<format>，如 PRJ-2026-001_report.pdf。"""
    return f"{project_file_stem(config)}_report.{output_format}"


def run_log_name(config: Dict[str, Any], timestamp: str) -> str:
    """
    运行日志文件名：<project_id>_<time>_bioreport.log。

    timestamp 为 time.strftime("%Y%m%d-%H%M%S") 形式的本地时间。
    """
    return f"{project_file_stem(config)}_{timestamp}_bioreport.log"


def load_project_metadata(
    config_path: str = None, default_client: str = "未指定客户"
) -> Dict[str, Any]:
    """
    加载项目元数据。

    兼容旧的 project_summary.json，同时支持新的 report_config.yaml。
    如果未传入路径，依次尝试 REPORT_CONFIG 环境变量、/app/report_config.yaml、
    /app/project_summary.json。

    返回的字典保留旧接口：
        {
            "client": ...,
            "species": ...,
            "genome": ...,
            "software": ...,
            "input_files": {...},
            ...
        }
    """
    meta_info = {
        "client": default_client,
        "species": "Unknown Species",
        "genome": "Unknown Genome",
        "software": "RNAFlow Pipeline",
        "project_id": "N/A",
        "input_files": {
            "data_dir": "../data/index/",
            "qc_file": "multiqc_qc_general_stats.txt",
            "mapping_file": "multiqc_mapping_general_stats.txt",
            "tpm_file": "merge_rsem_tpm.tsv",
            "sample_file": "sample.csv",
        },
    }

    explicit_path = config_path or os.environ.get("REPORT_CONFIG")
    if not config_path:
        config_path = explicit_path
    if not config_path:
        for fallback in [
            "/app/configs/report_config.yaml",
            "/app/report_config.yaml",
            "/app/project_summary.json",
        ]:
            if Path(fallback).exists():
                config_path = fallback
                break

    if not config_path or not Path(config_path).exists():
        if explicit_path:
            raise FileNotFoundError(f"Report config not found: {explicit_path}")
        print(f"[WARN] Metadata file not found: {config_path}. Using defaults.", file=sys.stderr)
        return meta_info

    data = load_config(config_path)

    project = data.get("project", {})
    if isinstance(project, dict):
        meta_info["client"] = project.get("client", meta_info["client"])
        meta_info["species"] = project.get("species", meta_info["species"])
        meta_info["project_id"] = project.get("project_id", meta_info["project_id"])
        meta_info["genome"] = project.get(
            "genome_version", project.get("genome", meta_info["genome"])
        )
        meta_info["software"] = project.get(
            "pipeline_version", project.get("software", meta_info["software"])
        )

    input_files = data.get("input_files", {})
    if isinstance(input_files, dict):
        meta_info["input_files"] = input_files.copy()

    # 透传 report/analysis/ai 等高级配置，方便 qmd 中直接使用
    meta_info["report"] = data.get("report", {})
    meta_info["stats"] = data.get("stats", {})
    meta_info["analysis"] = data.get("analysis", {})
    meta_info["files"] = data.get("files", {})
    meta_info["ai"] = data.get("ai", {})
    meta_info["_config_path"] = data.get("_config_path", config_path)

    return meta_info
