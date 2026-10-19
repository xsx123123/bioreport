#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quarto 模板渲染模块。

根据统一配置渲染 Jinja2 模板，生成运行时的 _quarto.yml 和 qmd/_report.qmd。
"""

from pathlib import Path
import shutil
from typing import Any, Dict

from jinja2 import Environment, FileSystemLoader
from loguru import logger

from .modules import compose_report, output_formats, selected_modules


def render_templates(
    config: Dict[str, Any],
    output_dir: str,
    template_dir: str = "/app/templates",
) -> None:
    """Render Quarto project settings and compose the selected modules."""
    logger.info("Rendering Quarto templates...")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

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
    pages = compose_report(config, Path(template_dir), website=True) if layout == "website" else []
    requested_formats = output_formats(config)

    # 1.0 HTML 输出:把内置字体拷贝到输出目录并声明 @font-face,
    # 报告文件夹自带字体,客户机器无需安装。
    staged_fonts = None
    try:
        from .utils.font_stage import stage_fonts
        staged_fonts = stage_fonts(output_dir) if "html" in requested_formats else None
        if staged_fonts:
            logger.debug(f"Report fonts staged in output: {staged_fonts}")
        elif "html" in requested_formats:
            logger.warning("Built-in font files are missing; HTML will use system fonts.")
    except Exception as e:
        logger.warning(f"Could not stage report fonts (rendering can continue): {e}")

    # 1. 渲染 _quarto.yml
    try:
        template_name = "_quarto-single.yml.j2" if layout == "single" else "_quarto.yml.j2"
        quarto_template = env.get_template(template_name)
        quarto_content = quarto_template.render(
            report=report, sections=sections, pages=pages, output_dir=output_dir,
            staged_fonts=staged_fonts,
        )
        quarto_path = Path(template_dir) / "_quarto.yml"
        quarto_path.write_text(quarto_content, encoding="utf-8")
        logger.debug(f"Generated {quarto_path}")
    except Exception as e:
        logger.error(f"Failed to render _quarto.yml: {e}")
        raise

    if layout == "single":
        # 按实际输出格式按需生成 .qmd：html 模式不生成 report_pdf.qmd。
        if "html" in requested_formats:
            report_qmd_path = compose_report(config, Path(template_dir))
            logger.debug(f"Generated {report_qmd_path}")
        if "pdf" in requested_formats:
            pdf_qmd_path = compose_report(config, Path(template_dir), pdf=True)
            shutil.copyfile(Path(template_dir) / "qmd/report-plan.json", Path(output_dir) / "report-plan.json")
            logger.debug(f"Generated {pdf_qmd_path}")
