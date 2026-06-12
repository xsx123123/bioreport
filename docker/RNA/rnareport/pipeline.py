#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 分析流程封装模块。
"""

import os
import subprocess
from pathlib import Path
from typing import Any, Dict

from loguru import logger
from rich.panel import Panel
from rich.console import Console


def run_ai_pipeline(config: Dict[str, Any], config_path: str, output_dir: str) -> None:
    """
    在 Quarto 渲染前执行数据整合与 AI 解读。

    Args:
        config: 统一配置字典。
        config_path: 配置文件路径（透传给 consolidate_rna_seq_data.py）。
        output_dir: 报告输出目录（仅用于日志/展示）。
    """
    ai_config = config.get("ai", {})
    if not ai_config.get("enabled", True):
        logger.info("AI 解读已禁用，跳过 AI 流程。")
        return

    logger.info("启动 AI 分析流程...")

    script_path = "/app/rnareport/utils/consolidate_rna_seq_data.py"
    if not Path(script_path).exists():
        logger.warning(f"AI 脚本未找到: {script_path}，跳过 AI 分析。")
        return

    console = Console()

    # Step 1: Generate consolidated data
    cmd_gen = [
        "python3",
        script_path,
        "generate",
        "--config",
        config_path,
        "--verbose",
    ]

    deg_limit = ai_config.get("deg_limit")
    if deg_limit is not None:
        cmd_gen.extend(["--deg-limit", str(deg_limit)])
    enrichment_limit = ai_config.get("enrichment_limit")
    if enrichment_limit is not None:
        cmd_gen.extend(["--enrichment-limit", str(enrichment_limit)])
    prompt_file = ai_config.get("prompt_file")
    if prompt_file:
        cmd_gen.extend(["--prompt-path", str(prompt_file)])

    logger.info("正在执行数据整合...")
    try:
        subprocess.run(cmd_gen, check=True, text=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"AI 数据整合失败: {e}")
        raise

    # Step 2: Report
    consolidated_file = "/app/templates/data/consolidated_rna_seq_data.txt"
    consolidated_md = "/app/templates/data/consolidated_rna_seq_report.md"

    cmd_report = [
        "python3",
        script_path,
        "report",
        "--input",
        consolidated_file,
        "--output-dir",
        consolidated_md,
        "--verbose",
    ]

    model = ai_config.get("model")
    if model:
        cmd_report.extend(["--model", str(model)])
    temperature = ai_config.get("temperature")
    if temperature is not None:
        cmd_report.extend(["--temperature", str(temperature)])

    logger.info("正在生成 AI 解读报告...")
    try:
        subprocess.run(cmd_report, check=True, text=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"AI 报告生成失败: {e}")
        raise

    console.print(Panel("✨ AI 分析流程完成！", border_style="purple"))
