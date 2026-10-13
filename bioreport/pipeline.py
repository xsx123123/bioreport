#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 分析流程封装模块。
"""

import os
import shutil
from pathlib import Path
from typing import Any, Dict

from loguru import logger


def run_generate(*args, **kwargs):
    """Lazy-load RNA data consolidation so the core CLI stays lightweight."""
    from .utils.consolidate_rna_seq_data import run_generate as implementation

    return implementation(*args, **kwargs)


def run_report(*args, **kwargs):
    """Lazy-load AI reporting and its optional scientific dependencies."""
    from .utils.consolidate_rna_seq_data import run_report as implementation

    return implementation(*args, **kwargs)


def run_ai_pipeline(config: Dict[str, Any], config_path: str, output_dir: str, template_dir: Path) -> None:
    """
    在 Quarto 渲染前执行数据整合与 AI 解读。

    Args:
        config: 统一配置字典。
        config_path: 配置文件路径（传给数据整合业务函数）。
        output_dir: 报告输出目录（仅用于日志/展示）。
    """
    ai_config = config.get("ai", {})
    if not ai_config.get("enabled", True):
        logger.info("AI 解读已禁用，跳过 AI 流程。")
        return

    logger.info("启动 AI 分析流程...")

    # Step 1: Generate consolidated data
    deg_limit = ai_config.get("deg_limit")
    enrichment_limit = ai_config.get("enrichment_limit")
    prompt_file = ai_config.get("prompt_file")
    if prompt_file:
        if not Path(prompt_file).is_file():
            raise FileNotFoundError(f"AI prompt file is missing: {prompt_file}")
    consolidated_file = template_dir / "data" / "consolidated_rna_seq_data.txt"
    logger.info("正在执行数据整合...")
    run_generate(consolidated_file, int(deg_limit) if deg_limit is not None else 20,
                 int(enrichment_limit) if enrichment_limit is not None else 10,
                 Path(prompt_file) if prompt_file else None, Path(config_path), True)
    if not consolidated_file.exists():
        raise RuntimeError("AI data consolidation completed without producing its text output")

    # Step 2: Report
    consolidated_file = template_dir / "data" / "consolidated_rna_seq_data.txt"
    consolidated_md = template_dir / "data" / "consolidated_rna_seq_report.md"
    ai_output_dir = template_dir / "data" / "ai_reports"

    model = ai_config.get("model")
    provider = ai_config.get("provider", "volcengine")
    if provider == "aliyun" and not model:
        raise ValueError("ai.model is required when ai.provider is aliyun")
    temperature = ai_config.get("temperature")
    logger.info("正在生成 AI 解读报告...")
    run_report(consolidated_file, ai_output_dir, str(model) if model else None,
               float(temperature) if temperature is not None else 0.7, provider, True)

    generated_report = ai_output_dir / "AI_Interpretation_Report.md"
    if not generated_report.exists():
        raise RuntimeError("AI report command completed without producing its Markdown report")
    shutil.copyfile(generated_report, consolidated_md)

    logger.info("AI 分析流程完成。")
