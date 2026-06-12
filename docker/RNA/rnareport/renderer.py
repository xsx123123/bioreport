#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quarto 模板渲染模块。

根据统一配置渲染 Jinja2 模板，生成运行时的 _quarto.yml 和 qmd/_report.qmd。
"""

from pathlib import Path
from typing import Any, Dict

from jinja2 import Environment, FileSystemLoader
from loguru import logger


def render_templates(
    config: Dict[str, Any],
    output_dir: str,
    template_dir: str = "/app/templates",
) -> None:
    """使用 Jinja2 渲染 _quarto.yml 和 qmd/_report.qmd。"""
    logger.info("正在渲染 Quarto 模板...")

    env = Environment(
        loader=FileSystemLoader(template_dir),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    report = config.get("report", {})
    sections = report.get(
        "sections", ["index", "workflow", "qc", "results", "ai", "about"]
    )

    # 1. 渲染 _quarto.yml
    try:
        quarto_template = env.get_template("_quarto.yml.j2")
        quarto_content = quarto_template.render(
            report=report, sections=sections, output_dir=output_dir
        )
        quarto_path = Path(template_dir) / "_quarto.yml"
        quarto_path.write_text(quarto_content, encoding="utf-8")
        logger.info(f"✅ 已生成 {quarto_path}")
    except Exception as e:
        logger.error(f"渲染 _quarto.yml 失败: {e}")
        raise

    # 2. 渲染 qmd/_report.qmd（单文件报告模板）
    try:
        report_template = env.get_template("qmd/_report.qmd.j2")
        report_content = report_template.render(report=report, sections=sections)
        report_qmd_path = Path(template_dir) / "qmd" / "_report.qmd"
        report_qmd_path.write_text(report_content, encoding="utf-8")
        logger.info(f"✅ 已生成 {report_qmd_path}")
    except Exception as e:
        logger.error(f"渲染 _report.qmd 失败: {e}")
        raise
