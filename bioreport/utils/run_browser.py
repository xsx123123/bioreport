"""Rich-based search and terminal browser for local BioReport runs."""

import json
from collections import Counter
from datetime import datetime
from typing import Any, Optional

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table

from .run_db import default_db_path, search_runs


def _short(value: Any, length: int = 42) -> str:
    text = "-" if value in (None, "") else str(value)
    return text if len(text) <= length else text[: length - 1] + "..."


def render_runs(console: Console, rows: list[dict], db_path) -> None:
    counts = Counter(row.get("status", "unknown") for row in rows)
    summary = Table.grid(padding=(0, 1))
    summary.add_column(style="bold")
    summary.add_column(justify="right")
    summary.add_column(style="cyan")
    max_count = max(counts.values(), default=1)
    for status, count in sorted(counts.items()):
        bar = "#" * max(1, round(20 * count / max_count))
        summary.add_row(status, str(count), bar)
    if not counts:
        summary.add_row("状态", "0", "无记录")
    console.print(Panel(Group(f"数据库: {db_path}\n记录数: {len(rows)}", summary),
                        title="BioReport 运行记录"))
    table = Table(show_header=True, header_style="bold cyan", expand=True)
    for column in ("ID", "项目", "运行时间", "状态", "格式", "模块", "输出目录"):
        table.add_column(column, no_wrap=column in {"ID", "状态"})
    for row in rows:
        formats = ", ".join(json.loads(row.get("output_format") or "[]"))
        modules = ", ".join(json.loads(row.get("modules") or "[]"))
        status = row.get("status", "-")
        style = "green" if status == "success" else "red" if status == "failed" else "yellow"
        table.add_row(
            str(row.get("id", "-")), _short(row.get("project_id")),
            _short(row.get("run_at"), 25), f"[{style}]{status}[/{style}]",
            _short(formats, 18), _short(modules, 28), _short(row.get("output_dir"), 42),
        )
    if rows:
        console.print(table)


def render_dashboard(console: Console, rows: list[dict], db_path) -> None:
    """Render the landing screen for the interactive browser."""
    now = datetime.now().astimezone()
    weekdays = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")
    current_date = f"{now:%Y-%m-%d} {weekdays[now.weekday()]}"
    current_time = now.strftime("%H:%M:%S %z")
    total = len(rows)
    success = sum(row.get("status") == "success" for row in rows)
    failed = sum(row.get("status") == "failed" for row in rows)
    projects = len({row.get("project_id") for row in rows if row.get("project_id")})
    rate = f"{success / total:.0%}" if total else "-"

    metrics = Table.grid(expand=True, padding=(0, 2))
    metrics.add_column(justify="center")
    metrics.add_column(justify="center")
    metrics.add_column(justify="center")
    metrics.add_column(justify="center")
    metrics.add_row(
        f"[bold cyan]{total}[/bold cyan]\n运行总数",
        f"[bold green]{success}[/bold green]\n成功",
        f"[bold red]{failed}[/bold red]\n失败",
        f"[bold yellow]{rate}[/bold yellow]\n成功率",
    )
    console.print(Panel(metrics, title="BioReport 运行仪表盘", border_style="cyan"))

    project_panel = Table.grid(padding=(0, 1))
    project_panel.add_column(style="bold")
    project_panel.add_column(justify="right", style="cyan")
    project_panel.add_row("当前日期", current_date)
    project_panel.add_row("当前时间", current_time)
    project_panel.add_row("项目数", str(projects))
    project_panel.add_row("数据库", _short(db_path, 60))
    console.print(Panel(project_panel, title="概览", border_style="dim"))

    recent = sorted(rows, key=lambda row: row.get("id", 0), reverse=True)[:10]
    console.print("[bold]最近运行（最多 10 条）[/bold]")
    if recent:
        render_runs(console, recent, db_path)
    else:
        console.print("[dim]暂无运行记录。执行 bioreport run 后这里会显示运行结果。[/dim]")


def browse_runs(console: Optional[Console] = None, db_path=None) -> None:
    """Interactive dashboard with an on-demand search flow."""
    console = console or Console()
    db_path = db_path or default_db_path()
    active_filters = {}
    while True:
        try:
            rows = search_runs(db_path, **active_filters)
            console.clear()
            render_dashboard(console, rows, db_path)
            filter_hint = "已应用筛选" if active_filters else "全量数据"
            console.print(f"\n[bold]操作[/bold]  [cyan]s[/cyan] 搜索  [cyan]r[/cyan] 刷新  [cyan]c[/cyan] 清除筛选  [cyan]q[/cyan] 退出    [dim]{filter_hint}[/dim]")
            action = console.input("> ").strip().lower()
            if action in {"q", "quit", "exit"}:
                return
            if action == "r":
                continue
            if action == "c":
                active_filters = {}
                continue
            if action not in {"s", "search"}:
                continue

            project = console.input("项目关键词 [不限]: ").strip()
            if project.lower() == "q":
                return
            status = console.input("状态 (success/failed) [不限]: ").strip()
            if status.lower() == "q":
                return
            since = console.input("起始时间 ISO (YYYY-MM-DD) [不限]: ").strip()
            if since.lower() == "q":
                return
            until = console.input("结束时间 ISO (YYYY-MM-DD) [不限]: ").strip()
            if until.lower() == "q":
                return
            active_filters = {
                key: value for key, value in {
                    "project": project or None,
                    "status": status or None,
                    "since": since or None,
                    "until": until or None,
                }.items() if value
            }
        except (EOFError, KeyboardInterrupt):
            console.print()
            return
