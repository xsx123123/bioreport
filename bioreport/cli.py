#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BioReport CLI 与主流程编排。
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
from rich.box import ROUNDED
from rich.console import Console, Group
from rich.panel import Panel
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text

from .config import load_config
from .pipeline import run_ai_pipeline
from .renderer import render_templates
from .modules import output_formats, selected_modules
from .registry import get_registry
from .utils.provenance import build_provenance, write_provenance
from .utils.run_db import default_db_path, record_run


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
    console.print("[dim]      [/dim]  --verbose 显示调试日志    -h, --help 显示帮助")
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
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="在终端显示调试日志（临时文件路径等内部细节，默认仅写入 pipeline.log）",
    )

    arguments = sys.argv[1:] if argv is None else argv
    args = parser.parse_args(arguments)
    if not arguments or args.help:
        show_help()
        raise SystemExit(0)
    return args


def setup_logging(output_dir: str | None = None, verbose: bool = False) -> str | None:
    """Configure concise console logs and a DEBUG-level file log."""
    logger.remove()

    # 终端只展示精简的高价值步骤状态；--verbose 才放开 DEBUG。
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green>  <level>{level: <7}</level>  {message}",
        level="DEBUG" if verbose else "INFO",
        colorize=True,
    )

    if output_dir is None:
        return None
    log_file = os.path.join(output_dir, "pipeline.log")
    # 文件日志完整记录 DEBUG 及以上（含 /tmp 路径与完整 64 位 SHA256）。
    logger.add(
        log_file,
        format="{time:YYYY-MM-DDTHH:mm:ssZZ}  {level: <7}  {message}",
        level="DEBUG",
        rotation="10 MB",
    )
    return log_file


def signal_handler(sig, frame):
    logger.warning("接收到中断信号 (Ctrl+C)，正在安全退出...")
    sys.exit(0)


def print_banner():
    artwork = r""" ____  ___ ___  ____  _____ ____   ___  ____ _____
| __ )|_ _/ _ \|  _ \| ____|  _ \ / _ \|  _ \_   _|
|  _ \ | | | | | |_) |  _| | |_) | | | | |_) || |
| |_) || | |_| |  _ <| |___|  __/| |_| |  _ < | |
|____/|___\___/|_| \_\_____|_|    \___/|_| \_\|_|"""
    console.print(Text(artwork, style="bold cyan"))
    console.print(Text("Powered by JZHANG | CygnusX BioOps", style="dim"))
    console.print(Text("https://github.com/xsx123123/bioreport", style="dim"))
    console.print()


def print_task_overview(config: dict, provenance: dict, output_dir: str) -> None:
    """Banner 之后的紧凑任务概览面板，替代逐行 INFO 刷屏。"""
    formats = " + ".join(f.upper() for f in provenance["output_format"])
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold", justify="right", no_wrap=True)
    grid.add_column(style="cyan", no_wrap=True)
    grid.add_column(style="bold", justify="right", no_wrap=True)
    grid.add_column(style="cyan", no_wrap=True)
    grid.add_row(
        "引擎", f"BioReport v{provenance['bioreport_version']}",
        "流程", provenance.get("pipeline_version", "-"),
    )
    grid.add_row("格式", formats, "布局", provenance["layout"])
    grid.add_row("输出", output_dir, "", "")
    modules_line = Text.assemble(
        ("模块", "bold"),
        ("  ", ""),
        (" → ".join(provenance["rendered_modules"]), "cyan"),
    )
    content = Group(grid, Text(), modules_line)
    console.print(Panel(content, title="任务概览", title_align="left", border_style="cyan", padding=(0, 1)))


def load_config_with_fallback(config_path: str | None) -> dict:
    logger.info(f"正在读取配置文件: {config_path or '默认搜索路径'}")
    try:
        return load_config(config_path)
    except Exception as e:
        logger.critical(f"解析配置失败: {e}")
        sys.exit(1)


def check_input_files(config: dict, provenance: dict | None = None) -> None:
    """使用紧凑的 Rich Table 展示输入文件检查结果（含 SHA256 指纹）。"""
    logger.info("检查输入文件完整性...")

    table = Table(
        title="输入文件检查清单",
        show_header=True,
        header_style="bold magenta",
        box=ROUNDED,
        expand=True,
    )
    table.add_column("Key", style="cyan", no_wrap=True)
    table.add_column("Relative Path", style="white")
    table.add_column("SHA256", style="dim", no_wrap=True)
    table.add_column("Status", justify="center")

    checksums = provenance["input_checksums"] if provenance else {}
    data_dir = config.get("input_files", {}).get("data_dir", "")
    if data_dir:
        table.caption = f"基准目录: {data_dir}"

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

    for key, path_str in files_to_check.items():
        if key == "data_dir":
            continue
        path = Path(path_str)
        exists = path.exists() or Path(os.getcwd()).joinpath(path).exists()
        rel_path = path_str
        if data_dir and str(path).startswith(str(Path(data_dir).resolve()) + os.sep):
            rel_path = os.path.relpath(str(path), str(Path(data_dir).resolve()))
        elif data_dir and not path.is_absolute():
            rel_path = os.path.relpath(str(path), str(Path(data_dir).resolve()))

        digest = checksums.get(key)
        if digest:
            sha_display = digest[:12]
        elif exists and path.is_dir():
            sha_display = "-"
        else:
            sha_display = "-"

        if exists:
            status = "[bold green]✔ Found[/]"
        else:
            status = "[bold red]✘ Missing[/]"
            if key in required:
                all_passed = False
            logger.warning(f"缺失文件: {key} -> {path_str}")

        table.add_row(key, rel_path, sha_display, status)

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
    logger.debug("Quarto Environment: {}", version)


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


# Quarto 输出中的 Cell 进度行，例如 ``Cell 3/22: 'qc-fastp'...Done``。
_CELL_PATTERN = re.compile(r"Cell (\d+)/(\d+):\s*'([^']*)'")


def _stream_quarto_output(process: subprocess.Popen, output_format: str) -> tuple[str, str, bool]:
    """读取 Quarto stdout：原始行全部写入 pipeline.log，终端仅显示单行动态进度条。

    返回 (last_cell, error_summary, cells_completed)。
    """
    last_cell = None
    error_summary = None
    cells_completed = False
    # Live 活动期间终端只允许进度条自刷新；否则 loguru 直写 stderr 会把
    # transient 清屏打断，进度条残留并黏上日志行（截图问题 2 的根因）。
    pending: list[tuple[str, str]] = []
    progress_columns = [
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
    ]
    with Progress(*progress_columns, console=console, transient=True) as progress:
        task = progress.add_task(f"Quarto 渲染 ({output_format.upper()})", total=None)

        for raw_line in iter(process.stdout.readline, ""):
            line = re.sub(r"\x1b\[[0-9;]*m", "", raw_line).strip()
            if not line:
                continue
            logger.debug("[Quarto] {}", line)
            match = _CELL_PATTERN.match(line)
            if match:
                index, total, cell_name = int(match.group(1)), int(match.group(2)), match.group(3)
                last_cell = line
                progress.update(
                    task,
                    total=total,
                    completed=index,
                    description=f"正在执行代码块 [{index}/{total}]: {cell_name or '-'}",
                )
                if index == total:
                    cells_completed = True
            elif line.startswith("Output created:"):
                pending.append(("info", f"[Quarto] {line}"))
            if re.match(r"^(?:ERROR|FATAL):\s+.+", line, re.IGNORECASE) or re.match(
                r"^[A-Za-z_][\w.]*(?:Error|Exception):\s+.+", line
            ):
                error_summary = line
                pending.append(("error", f"[Quarto] {line}"))

    # 进度条已随 with 块消失，此刻再上屏缓冲的日志。
    for level, message in pending:
        logger.log(level.upper(), message)

    return last_cell, error_summary, cells_completed


def render_report(config: dict, config_path: str, output_dir: str, template_dir: Path) -> None:
    layout = config.get("report", {}).get("layout", "single")
    env = os.environ.copy()
    env["REPORT_CONFIG"] = config_path
    env["XDG_CACHE_HOME"] = str(template_dir.parent / "cache")
    env["XDG_DATA_HOME"] = str(template_dir.parent / "share")
    # Typst scans TYPST_FONT_PATHS for the built-in font stack, so reports
    # render identically on machines without system CJK fonts installed.
    from .utils.fonts import typst_font_paths
    env["TYPST_FONT_PATHS"] = typst_font_paths()
    package_root = str(Path(__file__).resolve().parents[1])
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [package_root, env.get("PYTHONPATH")]))
    abs_output_dir = str(Path(output_dir).resolve())
    env["BIOREPORT_DELIVERY_DIR"] = abs_output_dir
    for output_format in output_formats(config):
        logger.info("启动 Quarto 渲染引擎 ({})...", output_format.upper())
        if layout == "website" and output_format != "html":
            raise ValueError("PDF output requires report.layout: single")
        quarto_format = "typst" if output_format == "pdf" else "html"
        source = f"qmd/report{'_pdf' if output_format == 'pdf' else ''}.qmd" if layout == "single" else "."
        cmd = ["quarto", "render", source, "--output-dir", abs_output_dir, "--to", quarto_format]
        env["BIOREPORT_OUTPUT_FORMAT"] = output_format
        block_manifest = Path(abs_output_dir) / f'report-blocks-{output_format}.jsonl'
        block_manifest.unlink(missing_ok=True)
        env['BIOREPORT_BLOCK_MANIFEST'] = str(block_manifest)
        process = subprocess.Popen(
            cmd, cwd=template_dir, env=env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True,
        )
        last_cell, error_summary, cells_completed = _stream_quarto_output(process, output_format)
        process.stdout.close()
        return_code = process.wait()

        if return_code != 0:
            detail = " (代码执行后的图表转换或文档渲染阶段)" if cells_completed else (
                f" ({last_cell})" if last_cell else ""
            )
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
        if output_format == "pdf" and expected.suffix == ".pdf":
            from .utils.pdf_metadata import set_pdf_metadata
            set_pdf_metadata(expected, config)
            from .report.validation import write_validation
            validation = write_validation(expected, template_dir / 'qmd/report_pdf.typ', config, env)
            if validation['errors']:
                raise RuntimeError(f"PDF layout validation failed; see {Path(output_dir) / 'pdf-validation.json'}")
            # 交付加固:按配置给 PDF 注入 AES-256 只读权限锁(免密阅读+打印,禁止编辑)。
            from .utils.pdf_security import protect_report_pdf
            if protect_report_pdf(expected, config):
                logger.info("PDF 已启用只读加密: 可免密阅读与打印,编辑功能已锁定")


def backup_config(config_path: str, output_dir: str) -> None:
    try:
        dst = os.path.join(output_dir, f"run_config_backup{Path(config_path).suffix}")
        shutil.copy(config_path, dst)
        logger.debug(f"配置文件已备份至: {dst}")
    except Exception as e:
        logger.warning(f"备份失败: {e}")


def print_success_summary(config: dict, output_dir: str, log_file: str | None, elapsed: float) -> None:
    """渲染成功后的绿色交付摘要：总耗时、报告主文件与日志位置。"""
    formats = output_formats(config)
    primary = formats[0] if formats else "html"
    layout = config.get("report", {}).get("layout", "single")
    if layout == "single":
        report_path = Path(output_dir).resolve() / f"report.{primary}"
    else:
        report_path = Path(output_dir).resolve() / "index.html"

    grid = Table.grid(padding=(0, 1))
    grid.add_column(style="bold green", no_wrap=True)
    grid.add_column()
    grid.add_row(f"✨ 报告生成完成！总耗时 {elapsed:.1f}s", "")
    grid.add_row("📄 报告路径", str(report_path))
    if log_file:
        grid.add_row("📋 日志文件", str(Path(output_dir) / "pipeline.log"))
    console.print(Panel(grid, border_style="green", padding=(0, 1)))


def main():
    start_time = time.perf_counter()
    signal.signal(signal.SIGINT, signal_handler)

    args = parse_args()
    if args.command == "run":
        print_banner()
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

    log_file = setup_logging(args.output, verbose=args.verbose)
    logger.debug(f"日志文件已创建: {log_file}")
    selected = selected_modules(config)
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
        # Shared built-in pages (about/faq/license/trademark/AI) and their
        # assets ship with the core templates, so the engine never depends
        # on any specific omics package; stage them first as the qmd/ root.
        shutil.copytree(template_dir / "shared", template_dir / "qmd")
        # Omics packages (e.g. omics/rna) overlay their own pages on top.
        rna_qmd_candidates = [
            Path(__file__).resolve().parents[1] / "omics" / "rna" / "qmd",
            Path(__file__).resolve().parents[1] / ".." / "omics" / "rna" / "qmd",
        ]
        rna_qmd = next((path for path in rna_qmd_candidates if path.is_dir()), None)
        if rna_qmd:
            shutil.copytree(rna_qmd, template_dir / "qmd", dirs_exist_ok=True)
        # 组装阶段写入溯源信息（引擎版本/生成时间/模块清单/输入指纹），
        # 供共享页、组学页与页脚在 Quarto 执行阶段读取。
        provenance = build_provenance(config, selected)
        provenance_path = write_provenance(provenance, template_dir / "qmd")
        logger.debug(f"报告溯源信息已写入: {provenance_path}")

        def _record_run(status: str) -> None:
            """将本次运行写入本地离线数据库；失败只告警，不阻断报告。"""
            try:
                db = default_db_path()
                row_id = record_run(
                    db,
                    project_id=config["project"]["project_id"],
                    provenance=provenance,
                    config_path=config["_config_path"],
                    output_dir=str(Path(args.output).resolve()),
                    status=status,
                )
                logger.debug(f"运行记录已写入本地数据库: {db} (id={row_id}, 状态={status})")
            except Exception as exc:
                logger.warning(f"写入本地运行数据库失败（不影响报告生成）: {exc}")

        # 先读取配置并检查输入文件完整性（含计算 SHA256），再渲染 Quarto 模板。
        check_input_files(config, provenance)
        # 完整 SHA256 指纹同步写入运行日志（pipeline.log），终端只展示前 12 位。
        for key, digest in provenance["input_checksums"].items():
            logger.debug("输入指纹(完整): {} = SHA256:{}", key, digest)
        print_task_overview(config, provenance, args.output)
        check_quarto_env()

        render_templates(config, str(Path(args.output).resolve()), str(template_dir))
        if args.dry_run:
            logger.info("配置与模块已验证，跳过 Quarto 渲染。")
            return

        if "ai" in selected:
            run_ai_pipeline(config, config["_config_path"], args.output, template_dir)
        try:
            render_report(config, config["_config_path"], args.output, template_dir)
        except (RuntimeError, FileNotFoundError) as exc:
            logger.error("{}", exc)
            _record_run("failed")
            raise SystemExit(1) from None

    backup_config(config["_config_path"], args.output)
    if not args.dry_run:
        from .utils.provenance import write_delivery_manifests
        write_delivery_manifests(config, provenance, args.output)
        from .utils.provenance import validate_delivery_manifests
        if validate_delivery_manifests(config, args.output)['errors']:
            _record_run('failed')
            raise RuntimeError('Delivery manifest integrity validation failed')
    _record_run("success")
    print_success_summary(config, args.output, log_file, time.perf_counter() - start_time)


if __name__ == "__main__":
    main()
