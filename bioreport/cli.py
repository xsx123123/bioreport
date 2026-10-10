#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RNAReport CLI 与主流程编排。
"""

import argparse
import os
import re
import shutil
import signal
import subprocess
import sys
import sysconfig
import tempfile
import time
from importlib import resources
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
from .modules import selected_modules
from .registry import get_registry


console = Console()


def show_help() -> None:
    console.print("[bold]bioreport[/bold]  Quarto 报告生成器\n")
    console.print("[dim]用法[/dim]  bioreport <命令> -c <配置文件> [-o <输出目录>]\n")
    commands = Table(show_header=False, box=None, padding=(0, 2))
    commands.add_column(style="bold cyan", no_wrap=True)
    commands.add_column()
    commands.add_row("run", "生成 HTML / PDF 报告")
    commands.add_row("validate", "检查配置格式")
    commands.add_row("init", "查看初始配置位置")
    console.print(commands)
    console.print("\n[dim]选项[/dim]  -c, --config 配置路径    -o, --output 输出目录")
    console.print("[dim]      [/dim]  --dry-run 仅检查模板       --data-prefix 数据挂载前缀")
    console.print("[dim]      [/dim]  -h, --help 显示帮助")
    console.print("\n[dim]本地示例[/dim]  bioreport run -c tests/report.rna.local.json -o output/rna-report")
    console.print("[dim]Docker 示例[/dim]  bioreport run -c configs/report.example.json -o output/rna-report")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="bioreport",
        add_help=False,
    )
    parser.add_argument("-h", "--help", action="store_true")
    parser.add_argument("command", nargs="?", choices=("run", "validate", "init"), default="run")

    parser.add_argument(
        "-c",
        "--config",
        default=None,
        help="配置文件路径 (默认查找 REPORT_CONFIG 或旧版兼容路径)",
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

    arguments = sys.argv[1:] if argv is None else argv
    args = parser.parse_args(arguments)
    if not arguments or args.help:
        show_help()
        raise SystemExit(0)
    return args


def setup_logging(output_dir: str | None = None) -> str | None:
    """Configure concise console logs and optional file logs."""
    logger.remove()

    logger.add(
        sys.stderr,
        format="<dim>{time:HH:mm:ss}</dim>  <level>{level: <7}</level>  {message}",
        level="INFO",
        colorize=sys.stderr.isatty(),
    )

    if output_dir is None:
        return None
    log_file = os.path.join(output_dir, "pipeline.log")
    logger.add(
        log_file,
        format="{time:YYYY-MM-DD HH:mm:ss}  {level: <7}  {message}",
        level="DEBUG",
        rotation="10 MB",
    )
    return log_file


def signal_handler(sig, frame):
    console.print()
    logger.warning("⚠️  接收到中断信号 (Ctrl+C)，正在安全退出...")
    sys.exit(0)


def print_banner(report_type: str = "report"):
    title = Text(f"{report_type} Report Generator", justify="center", style="bold cyan")
    subtitle = Text("v2.0.0 | Powered by Quarto", justify="center", style="dim white")
    console.print(
        Panel(
            Text.assemble(title, "\n", subtitle),
            border_style="cyan",
            expand=False,
            padding=(1, 5),
        )
    )


def load_config_with_fallback(config_path: str | None) -> dict:
    logger.info(f"正在读取配置文件: {config_path or '默认搜索路径'}")
    try:
        return load_config(config_path)
    except Exception as e:
        logger.critical(f"解析配置失败: {e}")
        sys.exit(1)


def check_input_files(config: dict) -> None:
    """使用 Rich Table 展示输入文件检查结果。"""
    logger.info("开始检查输入文件完整性...")

    table = Table(
        title="输入文件检查清单", show_header=True, header_style="bold magenta"
    )
    table.add_column("Key", style="cyan", no_wrap=True)
    table.add_column("Path", style="white")
    table.add_column("Status", justify="center")

    files_to_check = config.get("input_files", {})
    selected = selected_modules(config)
    registry = get_registry()
    definitions = registry.modules
    required = {
        key for module in selected
        for key in (
            definitions[registry.canonical(module)].required_inputs
            if registry.canonical(module) in definitions else ()
        )
    }
    custom = config.get("report", {}).get("module_definitions", {})
    required.update(
        key for module in selected for key in custom.get(module, {}).get("required_inputs", ())
    )
    required.update(
        key for module in selected
        for key in (
            definitions[registry.canonical(module)].optional_inputs
            if registry.canonical(module) in definitions else ()
        )
        if key in files_to_check
    )
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
                if key in required:
                    all_passed = False
                logger.warning(f"缺失文件: {key} -> {path_str}")

            table.add_row(key, str(path_str), status)
            progress.advance(task)
            time.sleep(0.05)

    console.print(table)

    for key in required - files_to_check.keys():
        logger.error(f"缺少必需输入配置: {key}")
        all_passed = False
    if not all_passed:
        raise FileNotFoundError("Input files are missing; check paths in the report config")


def check_quarto_env():
    if shutil.which("quarto") is None:
        logger.critical("未找到 Quarto 可执行文件！")
        sys.exit(1)

    res = subprocess.run(["quarto", "--version"], capture_output=True, text=True)
    version = res.stdout.strip()
    console.print(f"🛠️  Quarto Environment: [bold green]{version}[/]")


def output_formats(config: dict) -> list[str]:
    requested = config.get("report", {}).get("output_format", "html")
    formats = [requested] if isinstance(requested, str) else requested
    if not isinstance(formats, list) or not formats or any(
        value not in ("html", "pdf") for value in formats
    ):
        raise ValueError("report.output_format must be html, pdf, or a list of them")
    return list(dict.fromkeys(formats))


def resolve_template_candidates() -> list[Path]:
    """Locate templates in editable checkouts and installed distributions."""
    candidates = []
    try:
        package = resources.files("bioreport")
        candidates.append(Path(package).parent / "templates")
        # ``pip install --target`` places data-files below the target root;
        # regular installs expose the same tree through sysconfig below.
        candidates.append(Path(package).parent / "share" / "bioreport" / "templates")
    except (ModuleNotFoundError, TypeError):
        pass
    candidates.extend([
        Path(__file__).resolve().parents[1] / "templates",
        Path(sysconfig.get_path("data")) / "share" / "bioreport" / "templates",
    ])
    return candidates


def render_report(config: dict, config_path: str, output_dir: str, template_dir: Path) -> None:
    logger.info("启动 Quarto 渲染引擎...")
    layout = config.get("report", {}).get("layout", "single")
    env = os.environ.copy()
    env["REPORT_CONFIG"] = config_path
    env["XDG_CACHE_HOME"] = str(template_dir.parent / "cache")
    env["XDG_DATA_HOME"] = str(template_dir.parent / "share")
    package_root = str(Path(__file__).resolve().parents[1])
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [package_root, env.get("PYTHONPATH")]))
    abs_output_dir = str(Path(output_dir).resolve())
    for output_format in output_formats(config):
        if layout == "website" and output_format != "html":
            raise ValueError("PDF output requires report.layout: single")
        quarto_format = "typst" if output_format == "pdf" else "html"
        source = f"qmd/report{'_pdf' if output_format == 'pdf' else ''}.qmd" if layout == "single" else "."
        cmd = ["quarto", "render", source, "--output-dir", abs_output_dir, "--to", quarto_format]
        env["BIOREPORT_OUTPUT_FORMAT"] = output_format
        process = subprocess.Popen(
            cmd, cwd=template_dir, env=env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True,
        )
        last_cell = None
        error_summary = None
        for raw_line in iter(process.stdout.readline, ""):
            line = re.sub(r"\x1b\[[0-9;]*m", "", raw_line).strip()
            if not line:
                continue
            logger.debug("[Quarto] {}", line)
            if line.startswith("Cell "):
                last_cell = line
                console.print(f"[dim]{line}[/dim]")
            elif line.startswith("Output created:"):
                console.print(line)
            if re.match(r"^[A-Za-z_][\w.]*(?:Error|Exception):\s+.+", line):
                error_summary = line

        process.stdout.close()
        return_code = process.wait()

        if return_code != 0:
            detail = f" ({last_cell})" if last_cell else ""
            cause = f": {error_summary}" if error_summary else ""
            raise RuntimeError(
                f"Quarto {output_format} 渲染失败{detail}{cause}；完整输出见 {Path(output_dir) / 'pipeline.log'}"
            )
        if layout == "single":
            stem = "report_pdf" if output_format == "pdf" else "report"
            rendered = Path(abs_output_dir) / "qmd" / f"{stem}.{output_format}"
            expected = Path(abs_output_dir) / f"report.{output_format}"
            if rendered.exists():
                shutil.move(str(rendered), str(expected))
                if not any(rendered.parent.iterdir()):
                    rendered.parent.rmdir()
        else:
            expected = Path(abs_output_dir) / "index.html"
        if not expected.exists():
            raise RuntimeError(f"Quarto finished but expected artifact is missing: {expected}")
        console.print(Panel(f"报告生成成功: {expected}", border_style="green"))


def backup_config(config_path: str, output_dir: str) -> None:
    try:
        dst = os.path.join(output_dir, f"run_config_backup{Path(config_path).suffix}")
        shutil.copy(config_path, dst)
        logger.debug(f"配置文件已备份至: {dst}")
    except Exception as e:
        logger.warning(f"备份失败: {e}")


def main():
    signal.signal(signal.SIGINT, signal_handler)

    args = parse_args()
    setup_logging()

    if args.command == "init":
        console.print("请复制 configs/report.example.json 后填写项目参数。")
        return

    config = load_config_with_fallback(args.config)
    if args.command == "validate":
        console.print(f"配置有效: {config['_config_path']}")
        return
    if not os.path.exists(args.output):
        os.makedirs(args.output, exist_ok=True)

    log_file = setup_logging(args.output)
    logger.info(f"日志文件已创建: {log_file}")
    print_banner(config["report"].get("type", "report"))
    selected_modules(config)
    formats = output_formats(config)
    if config["report"].get("layout") == "website" and "pdf" in formats:
        raise ValueError("PDF output requires report.layout: single")
    candidates = resolve_template_candidates()
    source_template = next((candidate for candidate in candidates if candidate.is_dir()), None)
    if source_template is None:
        raise FileNotFoundError(f"Template directory is missing; checked: {candidates}")

    with tempfile.TemporaryDirectory(prefix="bioreport-") as temporary:
        template_dir = Path(temporary) / "templates"
        shutil.copytree(source_template, template_dir)
        # RNA-specific QMD lives in omics/rna; stage it beside shared templates
        # so the renderer has one stable Quarto project root.
        rna_qmd_candidates = [
            Path(__file__).resolve().parents[1] / "omics" / "rna" / "qmd",
            Path(__file__).resolve().parents[1] / ".." / "omics" / "rna" / "qmd",
        ]
        rna_qmd = next((path for path in rna_qmd_candidates if path.is_dir()), None)
        if rna_qmd:
            shutil.copytree(rna_qmd, template_dir / "qmd", dirs_exist_ok=True)
        render_templates(config, str(Path(args.output).resolve()), str(template_dir))
        if args.dry_run:
            console.print(Panel("配置与模块已验证，跳过 Quarto 渲染。", border_style="blue"))
            return

        check_input_files(config)
        check_quarto_env()
        if "ai" in selected_modules(config):
            run_ai_pipeline(config, config["_config_path"], args.output, template_dir)
        try:
            render_report(config, config["_config_path"], args.output, template_dir)
        except (RuntimeError, FileNotFoundError) as exc:
            logger.error("{}", exc)
            raise SystemExit(1) from None

    backup_config(config["_config_path"], args.output)


if __name__ == "__main__":
    main()
