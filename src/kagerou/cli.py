"""Command-line interface for Kagerou."""

from __future__ import annotations

import os
import sys

import click
from rich.console import Console

from kagerou import __version__
from kagerou.analyzer import Analyzer
from kagerou.reporter import print_report, save_json_report

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="kagerou")
def main() -> None:
    """Kagerou - AI-powered logic bug detector.

    Finds bugs hiding in plain sight using semantic code analysis.
    """


@main.command()
@click.argument("target", type=click.Path(exists=True))
@click.option(
    "--model",
    "-m",
    default="claude-sonnet-4-20250514",
    help="Claude model to use for analysis.",
)
@click.option(
    "--api-key",
    envvar="ANTHROPIC_API_KEY",
    help="Anthropic API key (or set ANTHROPIC_API_KEY env var).",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Output JSON report to file.",
)
@click.option(
    "--max-files",
    default=50,
    help="Maximum number of files to analyze.",
)
@click.option(
    "--no-cross-file",
    is_flag=True,
    help="Disable cross-file analysis.",
)
@click.option(
    "--min-confidence",
    default=0.6,
    type=float,
    help="Minimum confidence threshold (0.0-1.0).",
)
def scan(
    target: str,
    model: str,
    api_key: str | None,
    output: str | None,
    max_files: int,
    no_cross_file: bool,
    min_confidence: float,
) -> None:
    """Scan a file or directory for bugs.

    TARGET is a Python file or directory to analyze.

    Examples:

        kagerou scan myproject/

        kagerou scan buggy_file.py --output report.json

        kagerou scan src/ --model claude-sonnet-4-20250514 --max-files 100
    """
    if not api_key:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            console.print("[bold red]Error:[/] ANTHROPIC_API_KEY not set.")
            console.print("Set it via --api-key or ANTHROPIC_API_KEY environment variable.")
            sys.exit(1)

    console.print()
    console.print(
        f"[bold magenta]Kagerou[/] [dim]v{__version__}[/] - "
        "AI-powered logic bug detector"
    )
    console.print("[dim]Finding bugs hiding in plain sight...[/]")
    console.print()

    with console.status("[bold green]Analyzing code...", spinner="dots"):
        analyzer = Analyzer(
            api_key=api_key,
            model=model,
            max_files=max_files,
        )
        result = analyzer.analyze(target)

    # Filter by confidence
    if min_confidence > 0:
        result.bugs = [b for b in result.bugs if b.confidence >= min_confidence]

    print_report(result, console)

    if output:
        save_json_report(result, output)
        console.print(f"\n[green]JSON report saved to {output}[/]")

    # Exit code based on findings
    if result.critical_count > 0:
        sys.exit(2)
    elif result.high_count > 0:
        sys.exit(1)
    else:
        sys.exit(0)


@main.command()
@click.argument("target", type=click.Path(exists=True))
def parse(target: str) -> None:
    """Parse and display code structure (no AI analysis).

    Useful for debugging and understanding what Kagerou sees.
    """
    from kagerou.parser import collect_python_files, parse_file

    files = collect_python_files(target)
    console.print(f"\n[bold]Found {len(files)} Python files[/]\n")

    for file_path in files:
        ctx = parse_file(file_path)
        console.print(f"[bold cyan]{file_path}[/]")

        if ctx.parse_errors:
            for err in ctx.parse_errors:
                console.print(f"  [red]Error: {err}[/]")
            continue

        if ctx.imports:
            console.print(f"  Imports: {len(ctx.imports)}")

        if ctx.classes:
            console.print(f"  Classes: {', '.join(ctx.classes)}")

        for func in ctx.functions:
            calls = f" -> calls: {', '.join(func.calls)}" if func.calls else ""
            console.print(
                f"  [green]{func.qualified_name}[/]"
                f"(L{func.start_line}-{func.end_line}){calls}"
            )

        console.print()


if __name__ == "__main__":
    main()
