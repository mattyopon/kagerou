"""Source code parser for extracting function-level context."""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FunctionInfo:
    """Information about a parsed function."""

    name: str
    file_path: str
    start_line: int
    end_line: int
    source: str
    docstring: str | None = None
    calls: list[str] = field(default_factory=list)
    args: list[str] = field(default_factory=list)
    return_annotation: str | None = None
    decorators: list[str] = field(default_factory=list)
    class_name: str | None = None

    @property
    def qualified_name(self) -> str:
        """Full qualified name including class if applicable."""
        if self.class_name:
            return f"{self.class_name}.{self.name}"
        return self.name


@dataclass
class FileContext:
    """Parsed context of a single Python file."""

    file_path: str
    source: str
    imports: list[str] = field(default_factory=list)
    functions: list[FunctionInfo] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    global_vars: list[str] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)


class _CallCollector(ast.NodeVisitor):
    """AST visitor that collects function call names."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            self.calls.append(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            self.calls.append(node.func.attr)
        self.generic_visit(node)


def _get_source_segment(source_lines: list[str], start: int, end: int) -> str:
    """Extract source code lines (1-indexed)."""
    return "\n".join(source_lines[start - 1 : end])


def _extract_function_info(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    source_lines: list[str],
    file_path: str,
    class_name: str | None = None,
) -> FunctionInfo:
    """Extract function information from an AST node."""
    end_line = node.end_lineno or node.lineno
    source = _get_source_segment(source_lines, node.lineno, end_line)

    # Collect function calls
    collector = _CallCollector()
    collector.visit(node)

    # Get arguments
    args = [arg.arg for arg in node.args.args if arg.arg != "self"]

    # Get return annotation
    return_ann = None
    if node.returns:
        return_ann = ast.dump(node.returns)

    # Get decorators
    decorators = []
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name):
            decorators.append(dec.id)
        elif isinstance(dec, ast.Attribute):
            decorators.append(dec.attr)

    # Get docstring
    docstring = ast.get_docstring(node)

    return FunctionInfo(
        name=node.name,
        file_path=file_path,
        start_line=node.lineno,
        end_line=end_line,
        source=source,
        docstring=docstring,
        calls=collector.calls,
        args=args,
        return_annotation=return_ann,
        decorators=decorators,
        class_name=class_name,
    )


def parse_file(file_path: str) -> FileContext:
    """Parse a Python file and extract structural information.

    Args:
        file_path: Path to the Python file.

    Returns:
        FileContext with parsed information.
    """
    path = Path(file_path)
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return FileContext(
            file_path=file_path,
            source="",
            parse_errors=[f"Failed to read file: {e}"],
        )

    source_lines = source.splitlines()
    ctx = FileContext(file_path=file_path, source=source)

    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError as e:
        ctx.parse_errors.append(f"Syntax error: {e}")
        return ctx

    for node in ast.walk(tree):
        # Imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                ctx.imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                ctx.imports.append(f"{module}.{alias.name}")

    # Top-level traversal for functions and classes
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_info = _extract_function_info(node, source_lines, file_path)
            ctx.functions.append(func_info)

        elif isinstance(node, ast.ClassDef):
            ctx.classes.append(node.name)
            for item in ast.iter_child_nodes(node):
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    func_info = _extract_function_info(
                        item, source_lines, file_path, class_name=node.name
                    )
                    ctx.functions.append(func_info)

        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    ctx.global_vars.append(target.id)

    return ctx


def collect_python_files(
    target_path: str,
    max_files: int = 100,
    exclude_patterns: list[str] | None = None,
) -> list[str]:
    """Collect Python files from a directory or single file.

    Args:
        target_path: Path to a file or directory.
        max_files: Maximum number of files to collect.
        exclude_patterns: Patterns to exclude (e.g., 'test_', '__pycache__').

    Returns:
        List of Python file paths.
    """
    if exclude_patterns is None:
        exclude_patterns = ["__pycache__", ".venv", "venv", "node_modules", ".git", ".tox"]

    path = Path(target_path)

    if path.is_file():
        if path.suffix == ".py":
            return [str(path)]
        return []

    if not path.is_dir():
        return []

    files: list[str] = []
    for root, dirs, filenames in os.walk(path):
        # Filter excluded directories in-place
        dirs[:] = [d for d in dirs if not any(pat in d for pat in exclude_patterns)]

        for fname in sorted(filenames):
            if fname.endswith(".py") and not any(pat in fname for pat in exclude_patterns):
                files.append(os.path.join(root, fname))
                if len(files) >= max_files:
                    return files

    return files
