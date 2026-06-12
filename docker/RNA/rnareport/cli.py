#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RNAReport CLI 与主流程编排。
"""

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

from .config import load_config
from .pipeline import run_ai_pipeline
from .renderer import render_templates


try:
    from rich_argparse import RichHelpFormatter
except ImportError:  # pragma: no cover
    RichHelpFormatter = argparse.RawDescriptionHelpFormatter


console = Console()


def parse_args() -> argparse.Namespace:
    if hasattr(RichHelpFormatter, "styles"):
        RichHelpFormatter.styles["argparse.groups"] = "bold cyan"
        RichHelpFormatter.styles["argparse.metavar"] = "bold yellow"
        RichHelpFormatter.styles["argparse.args"] = "green"
        RichHelpFormatter.styles["argparse.prog"] = "bold blue"

    parser = argparse.ArgumentParser(
        prog="rnareport",
        description="RNAFlow 报告生成器\n基于 Quarto 的 RNA-seq 自动化报告生成流程",
        epilog="示例:\n"
               "  rnareport -c /app/configs/report_config.yaml -o /workspace\n"
               "  rnareport -c config.yaml --dry-run",
        formatter_class=RichHelpFormatter,
    )

    parser.add_argument(
        "-c",
        "--config",
        default="/app/configs/report_config.yaml",
        help="配置文件路径 (默认: /app/configs/report_config.yaml)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="/workspace",
        help="报告输出目录 (默认: /workspace)",
    )
    parser.add_argument(
        "--data-prefix",
        default="/data",
        help="Docker 容器内的数据挂载前缀 (默认: /data)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅渲染模板并检查配置，不执行 Quarto 渲染",
    )

    return parser.parse_args()


def setup_logging(output_dir: str) -> str:
    """配置 loguru 日志。"""
    logger.remove()

    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO",
    )

    log_file = os.path.join(output_dir, "pipeline.log")
    logger.add(
        log_file,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG",
        rotation="10 MB",
    )
    return log_file


def signal_handler(sig, frame):
    console.print()
    logger.warning("⚠️  接收到中断信号 (Ctrl+C)，正在安全退出...")
    sys.exit(0)


def print_banner():
    title = Text("RNAFlow Report Generator", justify="center", style="bold cyan")
    subtitle = Text("v1.1.0 | Powered by Quarto & Docker", justify="center", style="dim white")
    console.print(
        Panel(
            Text.assemble(title, "\n", subtitle),
            border_style="cyan",
            expand=False,
            padding=(1, 5),
        )
    )


def load_config_with_fallback(config_path: str) -> dict:
    logger.info(f"正在读取配置文件: [cyan]{config_path}[/]")
    path = Path(config_path)
    if not path.exists():
        legacy_path = Path("/app/project_summary.json")
        if legacy_path.exists():
            logger.warning(f"未找到 {config_path}，使用旧版配置 {legacy_path}")
            return load_config(legacy_path)
        logger.error(f"配置文件不存在: {config_path}")
        sys.exit(1)

    try:
        return load_config(config_path)
    except Exception as e:
        logger.critical(f"解析配置失败: {e}")
        sys.exit(1)


def check_input_files(config: dict):
    """使用 Rich Table 展示输入文件检查结果。"""
    logger.info("开始检查输入文件完整性...")

    table = Table(
        title="输入文件检查清单", show_header=True, header_style="bold magenta"
    )
    table.add_column("Key", style="cyan", no_wrap=True)
    table.add_column("Path", style="white")
    table.add_column("Status", justify="center")

    files_to_check = config.get("input_files", {})
    all_passed = True

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task(
            description="Scanning files...", total=len(files_to_check)
        )

        for key, path_str in files_to_check.items():
            path = Path(path_str)
            exists = path.exists() or Path(os.getcwd()).joinpath(path).exists()

            if exists:
                status = "[bold green]✔ Found[/]"
            else:
                status = "[bold red]✖ Missing[/]"
                all_passed = False
                logger.warning(f"缺失文件: {key} -> {path_str}")

            table.add_row(key, str(path_str), status)
            progress.advance(task)
            time.sleep(0.05)

    console.print(table)

    if not all_passed:
        logger.error("检测到缺失文件，请检查挂载路径 (-v) 或 YAML 配置。")


def check_quarto_env():
    if shutil.which("quarto") is None:
        logger.critical("未找到 Quarto 可执行文件！")
        sys.exit(1)

    res = subprocess.run(["quarto", "--version"], capture_output=True, text=True)
    version = res.stdout.strip()
    console.print(f"🛠️  Quarto Environment: [bold green]{version}[/]")


def render_report(config_path: str, output_dir: str) -> None:
    logger.info("启动 Quarto 渲染引擎...")

    template_dir = "/app/templates"
    if not os.path.exists(template_dir):
        logger.error(f"模板目录缺失: {template_dir}")
        sys.exit(1)

    os.chdir(template_dir)

    env = os.environ.copy()
    env["REPORT_CONFIG"] = config_path

    abs_output_dir = os.path.abspath(output_dir)
    cmd = ["quarto", "render", ".", "--output-dir", abs_output_dir, "--to", "html"]

    try:
        process = subprocess.Popen(
            cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )

        for line in iter(process.stdout.readline, ""):
            line = line.strip()
            if line:
                if "ERROR" in line or "Error" in line:
                    logger.error(f"[Quarto] {line}")
                else:
                    console.print(f"[dim blue][Quarto][/] {line}")

        process.stdout.close()
        return_code = process.wait()

        if return_code != 0:
            logger.error("❌ Quarto 渲染失败！")
            sys.exit(return_code)

        final_index = os.path.join(abs_output_dir, "index.html")
        success_msg = Text.assemble(
            ("🎉 报告生成成功！\n", "bold green"),
            (f"📂 目录: {abs_output_dir}\n", "white"),
            (f"👉 入口: {final_index}", "underline blue"),
        )
        console.print(Panel(success_msg, border_style="green"))

    except Exception as e:
        logger.critical(f"渲染未知错误: {e}")
        sys.exit(1)


def backup_config(config_path: str, output_dir: str) -> None:
    try:
        dst = os.path.join(output_dir, "run_config_backup.yaml")
        shutil.copy(config_path, dst)
        logger.debug(f"配置文件已备份至: {dst}")
    except Exception as e:
        logger.warning(f"备份失败: {e}")


def main():
    signal.signal(signal.SIGINT, signal_handler)

    args = parse_args()

    if not os.path.exists(args.output):
        os.makedirs(args.output, exist_ok=True)

    log_file = setup_logging(args.output)

    print_banner()
    logger.info(f"日志文件已创建: {log_file}")

    config = load_config_with_fallback(args.config)

    render_templates(config, args.output)

    if args.dry_run:
        console.print(
            Panel(
                "🧪 干运行模式完成，模板已渲染，跳过数据检查与 Quarto 渲染。",
                border_style="blue",
            )
        )
        return

    check_input_files(config)
    check_quarto_env()

    run_ai_pipeline(config, args.config, args.output)

    render_report(args.config, args.output)

    backup_config(args.config, args.output)


if __name__ == "__main__":
    main()
