#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BioReport CLI 与主流程编排。
"""

import argparse
import json
import os
import re
import shlex
import shutil
import signal
import sqlite3
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
from rich_argparse import RichHelpFormatter

from .config import load_config, report_artifact_name, run_log_name
from .pipeline import run_ai_pipeline
from .renderer import render_templates
from .modules import output_formats, selected_modules, skipped_modules
from .registry import get_registry
from .utils.provenance import build_provenance, write_provenance
from .utils.run_db import default_db_path, record_run
from .utils.run_browser import browse_runs, render_runs


console = Console()


def _positive_workers(value: str) -> int:
    try:
        count = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError('workers must be a positive integer') from exc
    if count < 1:
        raise argparse.ArgumentTypeError('workers must be a positive integer')
    return count


def _workspace_execution(project_id: str) -> tuple[object, str] | None:
    """Start tracking only when the explicit Workspace schema is present."""
    db_path = default_db_path()
    if not db_path.is_file():
        return None
    try:
        with sqlite3.connect(db_path) as connection:
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'agent_runs'"
            ).fetchone()
        if not exists:
            return None
        from .ai.persistence import InterpretationRepository
        repository = InterpretationRepository(db_path)
        execution_id = repository.create_execution(project_id=project_id)
        logger.debug("Workspace execution staged: {}", execution_id)
        return repository, execution_id
    except Exception as exc:
        logger.warning("Workspace execution tracking unavailable; continuing legacy run: {}", exc)
        return None


def _finish_workspace_execution(
    execution: tuple[object, str] | None,
    *,
    run_id: int | None,
    status: str,
) -> None:
    if execution is None or run_id is None:
        return
    repository, execution_id = execution
    try:
        repository.bind_execution(execution_id, run_id=run_id, status=status)
        logger.debug("Workspace execution bound: {} -> run {} ({})", execution_id, run_id, status)
    except Exception as exc:
        logger.warning("Workspace execution binding failed (execution={}): {}", execution_id, exc)


def show_help() -> None:
    build_parser().print_help()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bioreport",
        formatter_class=RichHelpFormatter,
        description="BioReport · Quarto-based multi-omics report generator",
        epilog="Examples: bioreport validate -c tests/report.rna.local.json; bioreport run -c report.json -o output",
    )
    parser.add_argument(
        "command", nargs="?",
        choices=("run", "runs", "validate", "init", "workspace-migrate", "workspace-restore"),
        default="run", metavar="COMMAND",
        help="run generate a report; validate check configuration, modules, and input paths; runs browse history; init show setup instructions; workspace-migrate/restore migrate or restore the database",
    )

    report_args = parser.add_argument_group("Reports and validation")
    run_args = parser.add_argument_group("Run history and database")
    report_args.add_argument(
        "-c",
        "--config",
        default=None,
        help="Configuration file (defaults to REPORT_CONFIG or a legacy path)",
    )
    report_args.add_argument(
        "-o",
        "--output",
        default="/workspace",
        help="Report output directory (default: /workspace)",
    )
    report_args.add_argument(
        "--workers", "-t", "--threads",
        type=_positive_workers,
        default=None,
        help="PDF DEG/enrichment worker processes (overrides report.pdf.workers; default: 8; use 1 for serial rendering)",
    )
    report_args.add_argument(
        "--data-prefix",
        default="/data",
        help="Data mount prefix inside Docker (default: /data)",
    )
    report_args.add_argument(
        "--dry-run",
        action="store_true",
        help="Render templates and validate configuration without running Quarto",
    )
    report_args.add_argument(
        "--verbose",
        action="store_true",
        help="Show debug logs in the terminal (internal details are otherwise written only to the run log)",
    )
    run_args.add_argument("--db", default=None, help="Run database path (default: ~/.bioreport/runs.db)")
    run_args.add_argument("--project", default=None, help="Filter run history by project ID")
    run_args.add_argument("--status", choices=("success", "failed"), default=None, help="Filter by run status")
    run_args.add_argument("--since", default=None, help="Start time (ISO date or datetime)")
    run_args.add_argument("--until", default=None, help="End time (ISO date or datetime)")
    run_args.add_argument("--limit", type=int, default=50, help="Maximum number of records to show (default: 50)")
    run_args.add_argument("--tui", action="store_true", help="Open the interactive run history browser")
    run_args.add_argument("--json", action="store_true", help="Output run history as JSON")

    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = build_parser()
    arguments = sys.argv[1:] if argv is None else argv
    args = parser.parse_args(arguments)
    if not arguments:
        parser.print_help()
        raise SystemExit(0)
    return args


def setup_logging(output_dir: str | None = None, verbose: bool = False,
                  log_file_name: str = "pipeline.log") -> str | None:
    """Configure concise console logs and a DEBUG-level file log."""
    logger.remove()

    # 终端只展示精简的高价值步骤状态；--verbose 才放开 DEBUG。
    logger.add(
        # Resolve the current stream when writing: embedded CLI callers may
        # replace/close their redirected stderr between report builds.
        lambda message: sys.stderr.write(message),
        format="<green>{time:HH:mm:ss}</green>  <level>{level: <7}</level>  {message}",
        level="DEBUG" if verbose else "INFO",
        colorize=True,
    )

    if output_dir is None:
        return None
    log_file = os.path.join(output_dir, log_file_name)
    # 文件日志完整记录 DEBUG 及以上（含 /tmp 路径与完整 64 位 SHA256）。
    logger.add(
        log_file,
        format="{time:YYYY-MM-DDTHH:mm:ssZZ}  {level: <7}  {message}",
        level="DEBUG",
        rotation="10 MB",
    )
    return log_file


def signal_handler(sig, frame):
    logger.warning("Interrupt received (Ctrl+C); exiting...")
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
        "Engine", f"BioReport v{provenance['bioreport_version']}",
        "Pipeline", provenance.get("pipeline_version", "-"),
    )
    grid.add_row("Format", formats, "Layout", provenance["layout"])
    if 'pdf' in provenance['output_format']:
        from .pdf_parallel import worker_count
        grid.add_row('PDF workers', str(worker_count(config, use_environment=False)), '', '')
    grid.add_row("Output", output_dir, "", "")
    modules_line = Text.assemble(
        ("Modules", "bold"),
        ("  ", ""),
        (" → ".join(provenance["rendered_modules"]), "cyan"),
    )
    content = Group(grid, Text(), modules_line)
    console.print(Panel(content, title="Run Overview", title_align="left", border_style="cyan", padding=(0, 1)))


def load_config_with_fallback(config_path: str | None, *, show_help_on_missing: bool = False) -> dict:
    logger.info(f"Loading configuration: {config_path or 'default search paths'}")
    try:
        return load_config(config_path)
    except FileNotFoundError as e:
        if show_help_on_missing and config_path is None:
            show_help()
            raise SystemExit(0) from e
        logger.critical(f"Failed to parse configuration: {e}")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"Failed to parse configuration: {e}")
        sys.exit(1)


def check_input_files(config: dict, provenance: dict | None = None) -> None:
    """使用紧凑的 Rich Table 展示输入文件检查结果（含 SHA256 指纹）。"""
    logger.info("Checking input files...")

    table = Table(
        title="Input File Checklist",
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
        table.caption = f"Base directory: {data_dir}"

    files_to_check = config.get("input_files", {})
    selected = selected_modules(config)
    registry = get_registry()
    definitions = registry.modules
    required = {
        key for module in selected
        for key in (
            definitions[registry.canonical(module)].required_inputs
            if registry.canonical(module) in definitions
            and not definitions[registry.canonical(module)].skip_if_missing_inputs else ()
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
    skippable = {
        key for module in selected
        if registry.canonical(module) in definitions
        and definitions[registry.canonical(module)].skip_if_missing_inputs
        for key in definitions[registry.canonical(module)].required_inputs
    }
    all_passed = True

    for key, path_str in files_to_check.items():
        if key == "data_dir":
            continue
        path = Path(path_str)
        exists = path.exists()
        problem = None
        if exists and key in (required | skippable):
            if key.endswith("_dir") and not path.is_dir():
                problem = "Expected directory"
            elif key.endswith("_file") and not path.is_file():
                problem = "Expected file"
            elif not os.access(path, os.R_OK | (os.X_OK if path.is_dir() else 0)):
                problem = "Unreadable"
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

        if problem:
            status = f"[bold red]✘ {problem}[/]"
            all_passed = False
            logger.error("Invalid input: {} -> {} ({})", key, path_str, problem)
        elif exists:
            status = "[bold green]✔ Found[/]"
        else:
            status = ("[yellow]⚠ Skipped[/]" if key in skippable and key not in required
                      else "[bold red]✘ Missing[/]")
            if key in required:
                all_passed = False
            logger.warning(f"Missing input: {key} -> {path_str}")

        table.add_row(key, rel_path, sha_display, status)

    console.print(table)
    for module_id, missing in skipped_modules(config, selected).items():
        logger.warning("Skipping {}: missing inputs {}. The report will include a missing-data notice.",
                       module_id, ", ".join(missing))

    if 'software_versions' in config:
        required.discard('software_versions_file')
    if config.get('enrichment'):
        required.discard('enrichment_dir')
        if any(registry.canonical(m) in ('rna.results', 'rna.results.enrichment') for m in selected):
            from .enrichment import validate_enrichment_inputs
            validate_enrichment_inputs(config)
    if all_passed and any(registry.canonical(m) == 'rna.workflow' for m in selected):
        from .software import software_records
        software_records(config)
    for key in required - files_to_check.keys():
        logger.error(f"Required input is not configured: {key}")
        all_passed = False
    if not all_passed:
        raise FileNotFoundError("Input files are missing; check paths in the report config")


def check_quarto_env():
    if shutil.which("quarto") is None:
        logger.critical("Quarto executable was not found.")
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


def _short_quarto_output_path(line: str) -> str:
    """Keep Quarto's output location useful without exposing its long cwd-relative prefix."""
    raw_path = line.removeprefix("Output created:").strip().replace("\\", "/")
    parts = [part for part in raw_path.split("/") if part and part != "."]
    qmd_index = max((index for index, part in enumerate(parts) if part == "qmd"), default=-1)
    display_path = "/".join(parts[qmd_index:]) if qmd_index >= 0 else "/".join(parts[-2:])
    return f"[Quarto] Render output: {display_path} (before delivery processing)"


def _quarto_output_lines(process, poll_progress):
    """Poll the result channel while Quarto waits for a complete output line."""
    from queue import Empty, Queue
    from threading import Thread
    lines = Queue()

    def read_output():
        try:
            for line in iter(process.stdout.readline, ''):
                lines.put(line)
        except Exception as exc:
            lines.put(exc)
        finally:
            lines.put(None)

    reader = Thread(target=read_output, name='quarto-output', daemon=True)
    reader.start()
    try:
        while True:
            poll_progress()
            try:
                line = lines.get(timeout=.1)
            except Empty:
                continue
            if line is None:
                poll_progress()
                return
            if isinstance(line, Exception):
                raise line
            yield line
    finally:
        reader.join(timeout=1)


def _stream_quarto_output(process: subprocess.Popen, output_format: str,
                          progress_file: Path | None = None) -> tuple[str, str, bool]:
    """读取 Quarto stdout 与结果进度；原始行写入日志，终端展示模块和结果进度。

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
    from .result_progress import ResultProgressReader
    from rich.markup import escape
    with Progress(*progress_columns, console=console, transient=True) as progress, ResultProgressReader(progress_file) as result_events:
        task = progress.add_task(f"Rendering Quarto ({output_format.upper()})", total=None)
        result_tasks = {}
        result_kind = None

        def clear_results():
            nonlocal result_kind
            for result_task in result_tasks.values():
                progress.remove_task(result_task)
            result_tasks.clear()
            result_kind = None

        def poll_results():
            nonlocal result_kind
            for event in result_events.read():
                kind, stage = event['kind'], event['stage']
                if result_kind != kind:
                    clear_results()
                    result_kind = kind
                    for name in ('prepare', 'render'):
                        result_tasks[name] = progress.add_task('', total=None, visible=False)
                title = 'DEG' if kind == 'DEG' else 'Enrichment'
                label = escape(event.get('label', ''))
                if stage == 'prepare':
                    workers = event.get('workers', '')
                    description = f'  {title} plots ({workers} processes): {label}'
                else:
                    description = f'  {title} results: {label}'
                progress.update(result_tasks[stage], total=event['total'], completed=event['completed'],
                                description=description, visible=event['total'] > 0)
                # A Jupyter cell-start line may itself be buffered until Done.
                # Keep the active module accurate using the live result channel.
                cell = 'pdf-deg' if kind == 'DEG' else 'pdf-enrichment'
                progress.update(task, description=f'Modules: {cell}')

        for raw_line in _quarto_output_lines(process, poll_results):
            line = re.sub(r"\x1b\[[0-9;]*m", "", raw_line).strip()
            if not line:
                continue
            logger.debug("[Quarto] {}", line)
            match = _CELL_PATTERN.match(line)
            if match:
                index, total, cell_name = int(match.group(1)), int(match.group(2)), match.group(3)
                last_cell = line
                expected = 'pdf-deg' if result_kind == 'DEG' else 'pdf-enrichment'
                if cell_name != expected:
                    clear_results()
                progress.update(
                    task,
                    total=total,
                    completed=index,
                    description=f"Running cell [{index}/{total}]: {cell_name or '-'}",
                )
                if index == total and re.search(r'\bDone\b', line):
                    cells_completed = True
                    clear_results()
                    progress.remove_task(task)
                    task = progress.add_task(
                        f"Quarto ({output_format.upper()}): converting figures / rendering document", total=None)
            elif line.startswith('[typst]:') and 'Compiling' in line:
                clear_results()
                progress.remove_task(task)
                task = progress.add_task("Quarto (PDF): compiling document with Typst", total=None)
            elif line.startswith("Output created:"):
                pending.append(("info", _short_quarto_output_path(line)))
            if re.match(r"^(?:ERROR|FATAL):\s+.+", line, re.IGNORECASE) or re.match(
                r"^[A-Za-z_][\w.]*(?:Error|Exception):\s+.+", line
            ):
                error_summary = line
                pending.append(("error", f"[Quarto] {line}"))

    # 进度条已随 with 块消失，此刻再上屏缓冲的日志。
    for level, message in pending:
        logger.log(level.upper(), message)

    return last_cell, error_summary, cells_completed


def render_report(config: dict, config_path: str, output_dir: str, template_dir: Path,
                  log_file: str | None = None) -> None:
    layout = config.get("report", {}).get("layout", "single")
    env = os.environ.copy()
    # Use the CLI environment unless the caller explicitly selects another one.
    env.setdefault("QUARTO_PYTHON", sys.executable)
    env["REPORT_CONFIG"] = config_path
    from .pdf_parallel import worker_count
    env['BIOREPORT_PDF_WORKERS'] = str(worker_count(config, use_environment=False))
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
    from .i18n import is_bilingual, is_rna, languages, localized_config
    original_config = config
    bilingual = is_bilingual(config)
    paired_html = bilingual and layout == "single"
    asset_audit = Path(abs_output_dir) / "html-assets.jsonl"
    html_requested = 'html' in output_formats(config)
    if html_requested:
        asset_audit.unlink(missing_ok=True)
        env['BIOREPORT_ASSET_AUDIT_FILE'] = str(asset_audit)
    else:
        env.pop('BIOREPORT_ASSET_AUDIT_FILE', None)
    if bilingual and html_requested and is_rna(config):
        from .utils.asset_audit import static_plotly_calls
        logger.info('RNA Plotly static calls: {}', ', '.join(static_plotly_calls(Path(package_root)/'omics/rna/analysis')))
    jobs = [(fmt, lang) for fmt in output_formats(config) for lang in (languages(config)[:1] if layout == "website" else languages(config))]
    for output_format, lang in jobs:
        config = localized_config(original_config, lang)
        env["BIOREPORT_LANGUAGE"] = lang
        abs_output_dir = str(Path(output_dir).resolve() / ("en" if layout == "website" and bilingual and lang == "en" else ""))
        Path(abs_output_dir).mkdir(parents=True, exist_ok=True)
        if bilingual and layout != "website":
            render_templates(config, abs_output_dir, str(template_dir))
        edition_name = {"zh": "Chinese", "en": "English"}.get(lang, lang)
        logger.info("Starting Quarto render ({} / {})...", output_format.upper(), edition_name)
        if layout == "website" and output_format != "html":
            raise ValueError("PDF output requires report.layout: single")
        quarto_format = "typst" if output_format == "pdf" else "html"
        source = f"qmd/report{'_pdf' if output_format == 'pdf' else ''}.qmd" if layout == "single" else "."
        cmd = ["quarto", "render", source, "--output-dir", abs_output_dir, "--to", quarto_format]
        env["BIOREPORT_OUTPUT_FORMAT"] = output_format
        block_manifest = Path(abs_output_dir) / f'report-blocks-{output_format}.jsonl'
        block_manifest.unlink(missing_ok=True)
        env['BIOREPORT_BLOCK_MANIFEST'] = str(block_manifest)
        progress_file = None
        if output_format == 'pdf':
            # Quarto may reuse the Jupyter kernel between language editions.
            # Keep its channel path stable, with fresh events for every render.
            progress_file = template_dir / 'result-progress.jsonl'
            progress_file.unlink(missing_ok=True)
            env['BIOREPORT_PROGRESS_FILE'] = str(progress_file)
        else:
            env.pop('BIOREPORT_PROGRESS_FILE', None)
        if layout == "single":
            stem = "report_pdf" if output_format == "pdf" else "report"
            (Path(abs_output_dir) / "qmd" / f"{stem}.{output_format}").unlink(missing_ok=True)
            edition_path = Path(abs_output_dir) / report_artifact_name(config, output_format, lang if bilingual else None)
            edition_path.unlink(missing_ok=True)
            if paired_html and output_format == "html" and lang == "zh":
                (Path(abs_output_dir) / report_artifact_name(config, output_format)).unlink(missing_ok=True)
        process = subprocess.Popen(
            cmd, cwd=template_dir, env=env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True,
        )
        last_cell, error_summary, cells_completed = _stream_quarto_output(process, output_format, progress_file)
        process.stdout.close()
        return_code = process.wait()

        if return_code != 0:
            detail = " (post-execution figure conversion or document rendering)" if cells_completed else (
                f" ({last_cell})" if last_cell else ""
            )
            cause = f": {error_summary}" if error_summary else ""
            log_hint = log_file or Path(output_dir) / "pipeline.log"
            termination = f"; exit code: {return_code}"
            if return_code < 0:
                termination += f" ({signal.Signals(-return_code).name})"
            if return_code in (-signal.SIGKILL, 128 + signal.SIGKILL):
                termination += "; process killed (check kernel OOM logs)"
            raise RuntimeError(
                f"Quarto {output_format} render failed{detail}{cause}{termination}; full output: {log_hint}"
            )
        if output_format == "html" and asset_audit.exists():
            events = [json.loads(line) for line in asset_audit.read_text().splitlines() if line.strip()]
            kinds = sorted({kind for event in events if event.get('kind') == 'plotly' for kind in event['traces']})
            logger.info('Rendered Plotly trace types: {}', ', '.join(kinds))
        if layout == "single":
            stem = "report_pdf" if output_format == "pdf" else "report"
            rendered = Path(abs_output_dir) / "qmd" / f"{stem}.{output_format}"
            edition = Path(abs_output_dir) / report_artifact_name(config, output_format, lang if bilingual else None)
            if rendered.exists():
                shutil.move(str(rendered), str(edition))
                logger.info(
                    "Moved and renamed: qmd/{} -> {}{}",
                    rendered.name, edition.name,
                    " (staged for bilingual HTML merge)" if paired_html and output_format == "html" else "",
                )
                if not any(rendered.parent.iterdir()):
                    rendered.parent.rmdir()
        else:
            from .website import finalize_website
            shutil.copytree(template_dir / "assets", Path(abs_output_dir) / "assets", dirs_exist_ok=True)
            finalize_website(Path(abs_output_dir), original_config)
            edition = Path(abs_output_dir) / "index.html"
        expected = Path(abs_output_dir) / report_artifact_name(config, output_format) if paired_html and output_format == "html" else edition
        if not edition.exists():
            raise RuntimeError(f"Quarto finished but expected artifact is missing: {edition}")
        if output_format == "html" and bilingual and not paired_html and layout != "website":
            from .i18n import add_language_switch
            add_language_switch(edition, original_config, lang, layout)
        if paired_html and output_format == "html" and lang == "en":
            from .i18n import combine_language_editions
            chinese = Path(abs_output_dir) / report_artifact_name(config, output_format, "zh")
            english = Path(abs_output_dir) / report_artifact_name(config, output_format, "en")
            from .utils.html_fonts import subset_html_fonts
            font_metrics = subset_html_fonts([chinese, english])
            (Path(abs_output_dir) / "font-subset-metrics.json").write_text(
                json.dumps(font_metrics, ensure_ascii=False, indent=2), encoding="utf-8")
            title = original_config.get("report", {}).get("title", "BioReport bilingual report")
            combined = expected.with_name(expected.name + ".combined")
            combine_language_editions(chinese, english, combined, title)
            combined.replace(expected)
            if chinese != expected:
                chinese.unlink()
            english.unlink()
            logger.info(
                "Merged Chinese and English HTML into: {} (single file; language editions removed)",
                expected.name,
            )
        elif not expected.exists() and not (paired_html and output_format == "html" and lang == "zh"):
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
                logger.info("Read-only PDF protection enabled: viewing and printing are allowed; editing is locked.")

            if bilingual:
                for name in ("report-plan.json", "report-blocks-pdf.jsonl", "layout-observations.json", "pdf-validation.json", "content-validation.json"):
                    path = Path(abs_output_dir) / name
                    if path.is_file():
                        shutil.copyfile(path, path.with_name(path.stem + "." + lang + path.suffix))
            logger.info("PDF delivery ready ({}): {}", edition_name, expected.name)


def backup_config(config_path: str, output_dir: str) -> None:
    try:
        dst = os.path.join(output_dir, f"run_config_backup{Path(config_path).suffix}")
        shutil.copy(config_path, dst)
        logger.debug(f"Configuration backed up to: {dst}")
    except Exception as e:
        logger.warning(f"Configuration backup failed: {e}")


def print_success_summary(config: dict, output_dir: str, log_file: str | None, elapsed: float) -> None:
    """渲染成功后的绿色交付摘要：总耗时、报告主文件与日志位置。"""
    formats = output_formats(config)
    primary = formats[0] if formats else "html"
    layout = config.get("report", {}).get("layout", "single")
    if layout == "single":
        report_path = Path(output_dir).resolve() / report_artifact_name(config, primary)
    else:
        report_path = Path(output_dir).resolve() / "index.html"

    grid = Table.grid(padding=(0, 1))
    grid.add_column(style="bold green", no_wrap=True)
    grid.add_column()
    grid.add_row(f"Report generation complete in {elapsed:.1f}s", "")
    grid.add_row("Main report", str(report_path))
    from .i18n import is_rna
    if is_rna(config):
        for fmt in formats:
            if fmt == "html" and layout == "single":
                grid.add_row("Bilingual HTML", str(Path(output_dir).resolve() / report_artifact_name(config, fmt)))
                continue
            for edition, label in (("zh", "Chinese"), ("en", "English")):
                relative = (("en/index.html" if edition == "en" else "index.html") if layout == "website" else report_artifact_name(config, fmt, edition))
                grid.add_row(f"📄 {label} {fmt.upper()}", str(Path(output_dir).resolve() / relative))
    if log_file:
        grid.add_row("Run log", str(log_file))
    console.print(Panel(grid, border_style="green", padding=(0, 1)))


def main():
    start_time = time.perf_counter()
    signal.signal(signal.SIGINT, signal_handler)

    args = parse_args()
    if args.command == "runs":
        from .utils.run_db import search_runs
        db_path = Path(args.db).expanduser() if args.db else default_db_path()
        if args.tui:
            browse_runs(console, db_path)
            return
        rows = search_runs(db_path, project=args.project, status=args.status,
                           since=args.since, until=args.until, limit=args.limit)
        if args.json:
            console.print_json(data=rows)
        else:
            render_runs(console, rows, db_path)
        return
    if args.command in {"workspace-migrate", "workspace-restore"}:
        from .db.migrations import migrate_workspace, restore_workspace_backup
        db_path = Path(args.db).expanduser() if args.db else default_db_path()
        if args.command == "workspace-migrate":
            backup = migrate_workspace(db_path)
            console.print(f"Workspace schema migrated to v2: {db_path}")
            if backup:
                console.print(f"Pre-migration backup: {backup}")
        else:
            restore_workspace_backup(db_path)
            console.print(f"Workspace migration backup restored: {db_path}")
        return
    if args.command == "run":
        print_banner()
    setup_logging()

    if args.command == "init":
        console.print("Copy configs/report.example.json and fill in the project settings.")
        return

    if args.command == "validate":
        config = load_config_with_fallback(args.config, show_help_on_missing=True)
    else:
        config = load_config_with_fallback(args.config)
    if args.workers is not None:
        config.setdefault('report', {}).setdefault('pdf', {})['workers'] = args.workers
    if args.command == "validate":
        try:
            formats = output_formats(config)
            if config["report"].get("layout") == "website" and "pdf" in formats:
                raise ValueError("PDF output requires report.layout: single")
            check_input_files(config)
        except (ValueError, OSError) as exc:
            logger.error("Validation failed: {}", exc)
            raise SystemExit(1) from exc
        console.print(f"Configuration, modules, and required input paths are valid: {config['_config_path']}")
        return
    if not os.path.exists(args.output):
        os.makedirs(args.output, exist_ok=True)

    log_file = setup_logging(args.output, verbose=args.verbose,
                             log_file_name=run_log_name(config, time.strftime("%Y%m%d-%H%M%S")))
    logger.debug(f"Run log created: {log_file}")
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
        _repo_root = Path(__file__).resolve().parents[1]
        for omics_name in ("rna", "gwas"):
            qmd_candidates = [
                _repo_root / "omics" / omics_name / "qmd",
                _repo_root / ".." / "omics" / omics_name / "qmd",
            ]
            omics_qmd = next((path for path in qmd_candidates if path.is_dir()), None)
            if omics_qmd:
                shutil.copytree(omics_qmd, template_dir / "qmd", dirs_exist_ok=True)
        # 组装阶段写入溯源信息（引擎版本/生成时间/模块清单/输入指纹），
        # 供共享页、组学页与页脚在 Quarto 执行阶段读取。
        provenance = build_provenance(config, selected)
        provenance_path = write_provenance(provenance, template_dir / "qmd")
        logger.debug(f"Report provenance written to: {provenance_path}")
        workspace_execution = None
        execution_id = None

        def _record_run(status: str) -> int | None:
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
                _finish_workspace_execution(workspace_execution, run_id=row_id, status=status)
                logger.debug(f"Run recorded in local database: {db} (id={row_id}, status={status})")
                return row_id
            except Exception as exc:
                logger.warning(f"Could not write to local run database (report generation will continue): {exc}")
                return None

        # 先读取配置并检查输入文件完整性（含计算 SHA256），再渲染 Quarto 模板。
        check_input_files(config, provenance)
        # 完整 SHA256 指纹同步写入运行日志，终端只展示前 12 位。
        for key, digest in provenance["input_checksums"].items():
            logger.debug("Full input fingerprint: {} = SHA256:{}", key, digest)
        print_task_overview(config, provenance, args.output)
        check_quarto_env()

        render_templates(config, str(Path(args.output).resolve()), str(template_dir))
        if args.dry_run:
            logger.info("Configuration and modules validated; skipping Quarto rendering.")
            return

        workspace_execution = _workspace_execution(config["project"]["project_id"])
        if workspace_execution:
            execution_id = workspace_execution[1]
            provenance["execution_id"] = execution_id
            write_provenance(provenance, template_dir / "qmd")

        try:
            ai_enabled = "ai" in selected or config.get("ai", {}).get("enabled", False)
            visual_pdf = (
                ai_enabled
                and config.get("ai", {}).get("scope", "results") == "results"
                and "pdf" in formats
                and config.get("report", {}).get("layout", "single") == "single"
            )
            if visual_pdf:
                logger.info("Two-pass PDF AI workflow: rendering figures without AI cards...")
                render_report(config, config["_config_path"], args.output, template_dir, log_file)
                run_ai_pipeline(
                    config, config["_config_path"], args.output, template_dir,
                    execution_id=execution_id, visual_mode=True,
                )
                logger.info("Two-pass PDF AI workflow: adding visual interpretations and rendering again...")
                render_report(config, config["_config_path"], args.output, template_dir, log_file)
            else:
                if ai_enabled:
                    run_ai_pipeline(
                        config, config["_config_path"], args.output, template_dir,
                        execution_id=execution_id,
                    )
                render_report(config, config["_config_path"], args.output, template_dir, log_file)
        except Exception as exc:
            logger.error("{}", exc)
            try:
                from .utils.render_recovery import preserve_failed_render
                saved = preserve_failed_render(template_dir, args.output, exc)
                logger.error("Failed render project preserved: {}", saved)
                if (saved / 'templates/compile-pdf.sh').is_file():
                    logger.info("Retry PDF typesetting without rerunning Python: {}",
                                shlex.join(['sh', str(saved / 'templates/compile-pdf.sh')]))
            except Exception as recovery_error:
                logger.warning("Could not preserve failed render project: {}", recovery_error)
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
