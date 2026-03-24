# Copyright (c) 2026 Yutaro Maeda
# Licensed under the MIT License. See LICENSE file for details.

"""Rich terminal and JSON output for Kagerou analysis results."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from kagerou.models import AnalysisResult, BugReport, Severity

_SEVERITY_COLORS: dict[Severity, str] = {
    Severity.CRITICAL: "bold red",
    Severity.HIGH: "red",
    Severity.MEDIUM: "yellow",
    Severity.LOW: "cyan",
    Severity.INFO: "dim",
}

_SEVERITY_ICONS: dict[Severity, str] = {
    Severity.CRITICAL: "[!!!]",
    Severity.HIGH: "[!!]",
    Severity.MEDIUM: "[!]",
    Severity.LOW: "[~]",
    Severity.INFO: "[i]",
}


def _format_confidence(confidence: float) -> str:
    """Format confidence as a percentage with color hint."""
    pct = int(confidence * 100)
    if pct >= 90:
        return f"[bold green]{pct}%[/]"
    elif pct >= 75:
        return f"[green]{pct}%[/]"
    elif pct >= 60:
        return f"[yellow]{pct}%[/]"
    else:
        return f"[dim]{pct}%[/]"


def _render_bug(console: Console, bug: BugReport, index: int) -> None:
    """Render a single bug report to the console."""
    severity_color = _SEVERITY_COLORS.get(bug.severity, "white")
    icon = _SEVERITY_ICONS.get(bug.severity, "[?]")

    # Title line
    title = Text()
    title.append(f"  {icon} ", style=severity_color)
    title.append(f"#{index} ", style="bold")
    title.append(bug.title, style="bold")

    console.print(title)
    console.print(f"      Category: [bold]{bug.category.value}[/] | "
                  f"Severity: [{severity_color}]{bug.severity.value}[/] | "
                  f"Confidence: {_format_confidence(bug.confidence)}")
    console.print(f"      Location: [underline]{bug.location}[/]")
    console.print()

    if bug.description:
        console.print(f"      {bug.description}")
        console.print()

    if bug.code_snippet:
        console.print("      [dim]Code:[/]")
        for line in bug.code_snippet.splitlines():
            console.print(f"        [dim]{line}[/]")
        console.print()

    if bug.reasoning:
        console.print(f"      [bold]Why this is a bug:[/] {bug.reasoning}")
        console.print()

    if bug.suggestion:
        console.print(f"      [green bold]Fix:[/] {bug.suggestion}")
        console.print()

    console.print("      " + "-" * 60)
    console.print()


def print_report(result: AnalysisResult, console: Console | None = None) -> None:
    """Print a rich terminal report of the analysis results.

    Args:
        result: The analysis result to display.
        console: Rich console to use (creates new one if None).
    """
    if console is None:
        console = Console()

    # Header
    console.print()
    header = Panel(
        f"[bold]Target:[/] {result.target_path}\n"
        f"[bold]Files analyzed:[/] {result.files_analyzed}\n"
        f"[bold]Bugs found:[/] {result.bug_count}\n"
        f"[bold]Analysis time:[/] {result.analysis_time_seconds:.1f}s",
        title="[bold magenta]Kagerou Analysis Report[/]",
        subtitle="[dim]AI-powered logic bug detection[/]",
        border_style="magenta",
    )
    console.print(header)

    if result.errors:
        console.print("\n[bold red]Errors:[/]")
        for error in result.errors:
            console.print(f"  [red]- {error}[/]")
        console.print()

    if not result.bugs:
        console.print("\n  [green bold]No bugs detected.[/]\n")
        return

    # Summary table
    summary = Table(title="Bug Summary", show_header=True, header_style="bold")
    summary.add_column("Severity", style="bold")
    summary.add_column("Count", justify="right")

    severity_counts: dict[str, int] = {}
    for bug in result.bugs:
        key = bug.severity.value
        severity_counts[key] = severity_counts.get(key, 0) + 1

    for sev in Severity:
        count = severity_counts.get(sev.value, 0)
        if count > 0:
            color = _SEVERITY_COLORS.get(sev, "white")
            summary.add_row(f"[{color}]{sev.value}[/]", str(count))

    console.print()
    console.print(summary)
    console.print()

    # Detailed reports
    console.print("[bold]Detailed Findings:[/]\n")
    for i, bug in enumerate(result.bugs, 1):
        _render_bug(console, bug, i)


def save_json_report(result: AnalysisResult, output_path: str) -> None:
    """Save analysis result as a JSON file.

    Args:
        result: The analysis result to save.
        output_path: Path to write the JSON file.
    """
    from pathlib import Path

    Path(output_path).write_text(result.to_json(), encoding="utf-8")
