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

from .modules import compose_report, selected_modules


def render_templates(
    config: Dict[str, Any],
    output_dir: str,
    template_dir: str = "/app/templates",
) -> None:
    """Render Quarto project settings and compose the selected modules."""
    logger.info("正在渲染 Quarto 模板...")

    env = Environment(
        loader=FileSystemLoader(template_dir),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    report = config.get("report", {})
    sections = selected_modules(config)
    layout = report.get("layout", "single")
    if layout not in ("single", "website"):
        raise ValueError("report.layout must be 'single' or 'website'")

    # 1. 渲染 _quarto.yml
    try:
        template_name = "_quarto-single.yml.j2" if layout == "single" else "_quarto.yml.j2"
        quarto_template = env.get_template(template_name)
        quarto_content = quarto_template.render(
            report=report, sections=sections, output_dir=output_dir
        )
        quarto_path = Path(template_dir) / "_quarto.yml"
        quarto_path.write_text(quarto_content, encoding="utf-8")
        logger.info(f"✅ 已生成 {quarto_path}")
    except Exception as e:
        logger.error(f"渲染 _quarto.yml 失败: {e}")
        raise

    if layout == "single":
        report_qmd_path = compose_report(config, Path(template_dir))
        logger.info(f"已生成 {report_qmd_path}")
        pdf_qmd_path = compose_report(config, Path(template_dir), pdf=True)
        logger.info(f"已生成 {pdf_qmd_path}")
