# Copyright (c) 2026 Yutaro Maeda
# Licensed under the MIT License. See LICENSE file for details.

"""Tests for the code parser module."""

from __future__ import annotations

from pathlib import Path

import pytest

from kagerou.parser import (
    FunctionInfo,
    collect_python_files,
    parse_file,
)


@pytest.fixture
def sample_python_file(tmp_path: Path) -> str:
    """Create a sample Python file for testing."""
    code = '''\
import os
from pathlib import Path

GLOBAL_VAR = 42


class MyClass:
    """A sample class."""

    def method_one(self, x: int) -> int:
        """Does something."""
        return x + 1

    def method_two(self, y: str) -> str:
        result = self.method_one(len(y))
        return str(result)


def standalone_func(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


def caller_func() -> None:
    result = standalone_func(1, 2)
    print(result)
'''
    file_path = tmp_path / "sample.py"
    file_path.write_text(code)
    return str(file_path)


@pytest.fixture
def syntax_error_file(tmp_path: Path) -> str:
    """Create a Python file with syntax errors."""
    code = "def broken(\n    # Missing closing paren and colon\n"
    file_path = tmp_path / "broken.py"
    file_path.write_text(code)
    return str(file_path)


@pytest.fixture
def empty_file(tmp_path: Path) -> str:
    """Create an empty Python file."""
    file_path = tmp_path / "empty.py"
    file_path.write_text("")
    return str(file_path)


class TestParseFile:
    """Tests for parse_file function."""

    def test_parses_imports(self, sample_python_file: str) -> None:
        ctx = parse_file(sample_python_file)
        assert "os" in ctx.imports
        assert "pathlib.Path" in ctx.imports

    def test_parses_classes(self, sample_python_file: str) -> None:
        ctx = parse_file(sample_python_file)
        assert "MyClass" in ctx.classes

    def test_parses_functions(self, sample_python_file: str) -> None:
        ctx = parse_file(sample_python_file)
        func_names = [f.name for f in ctx.functions]
        assert "standalone_func" in func_names
        assert "caller_func" in func_names

    def test_parses_methods(self, sample_python_file: str) -> None:
        ctx = parse_file(sample_python_file)
        method_names = [f.qualified_name for f in ctx.functions]
        assert "MyClass.method_one" in method_names
        assert "MyClass.method_two" in method_names

    def test_parses_function_calls(self, sample_python_file: str) -> None:
        ctx = parse_file(sample_python_file)
        caller = next(f for f in ctx.functions if f.name == "caller_func")
        assert "standalone_func" in caller.calls
        assert "print" in caller.calls

    def test_parses_global_vars(self, sample_python_file: str) -> None:
        ctx = parse_file(sample_python_file)
        assert "GLOBAL_VAR" in ctx.global_vars

    def test_parses_docstrings(self, sample_python_file: str) -> None:
        ctx = parse_file(sample_python_file)
        func = next(f for f in ctx.functions if f.name == "standalone_func")
        assert func.docstring == "Add two numbers."

    def test_handles_syntax_errors(self, syntax_error_file: str) -> None:
        ctx = parse_file(syntax_error_file)
        assert len(ctx.parse_errors) > 0
        assert "Syntax error" in ctx.parse_errors[0]

    def test_handles_empty_file(self, empty_file: str) -> None:
        ctx = parse_file(empty_file)
        assert ctx.functions == []
        assert ctx.classes == []
        assert ctx.parse_errors == []

    def test_handles_nonexistent_file(self) -> None:
        ctx = parse_file("/nonexistent/file.py")
        assert len(ctx.parse_errors) > 0
        assert "Failed to read" in ctx.parse_errors[0]

    def test_function_line_numbers(self, sample_python_file: str) -> None:
        ctx = parse_file(sample_python_file)
        func = next(f for f in ctx.functions if f.name == "standalone_func")
        assert func.start_line > 0
        assert func.end_line >= func.start_line

    def test_function_args(self, sample_python_file: str) -> None:
        ctx = parse_file(sample_python_file)
        func = next(f for f in ctx.functions if f.name == "standalone_func")
        assert "a" in func.args
        assert "b" in func.args

    def test_method_excludes_self(self, sample_python_file: str) -> None:
        ctx = parse_file(sample_python_file)
        method = next(f for f in ctx.functions if f.name == "method_one")
        assert "self" not in method.args
        assert "x" in method.args


class TestCollectPythonFiles:
    """Tests for collect_python_files function."""

    def test_collects_from_directory(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("x = 1")
        (tmp_path / "b.py").write_text("y = 2")
        (tmp_path / "c.txt").write_text("not python")
        files = collect_python_files(str(tmp_path))
        assert len(files) == 2
        assert all(f.endswith(".py") for f in files)

    def test_collects_single_file(self, tmp_path: Path) -> None:
        f = tmp_path / "single.py"
        f.write_text("x = 1")
        files = collect_python_files(str(f))
        assert len(files) == 1

    def test_respects_max_files(self, tmp_path: Path) -> None:
        for i in range(20):
            (tmp_path / f"file_{i}.py").write_text(f"x = {i}")
        files = collect_python_files(str(tmp_path), max_files=5)
        assert len(files) == 5

    def test_excludes_pycache(self, tmp_path: Path) -> None:
        (tmp_path / "good.py").write_text("x = 1")
        cache_dir = tmp_path / "__pycache__"
        cache_dir.mkdir()
        (cache_dir / "cached.py").write_text("y = 2")
        files = collect_python_files(str(tmp_path))
        assert len(files) == 1

    def test_excludes_venv(self, tmp_path: Path) -> None:
        (tmp_path / "good.py").write_text("x = 1")
        venv_dir = tmp_path / "venv"
        venv_dir.mkdir()
        (venv_dir / "lib.py").write_text("y = 2")
        files = collect_python_files(str(tmp_path))
        assert len(files) == 1

    def test_handles_nonexistent_path(self) -> None:
        files = collect_python_files("/nonexistent/path")
        assert files == []

    def test_handles_non_python_file(self, tmp_path: Path) -> None:
        f = tmp_path / "readme.md"
        f.write_text("# Hello")
        files = collect_python_files(str(f))
        assert files == []


class TestFunctionInfo:
    """Tests for FunctionInfo dataclass."""

    def test_qualified_name_standalone(self) -> None:
        info = FunctionInfo(
            name="func",
            file_path="test.py",
            start_line=1,
            end_line=3,
            source="def func(): pass",
        )
        assert info.qualified_name == "func"

    def test_qualified_name_method(self) -> None:
        info = FunctionInfo(
            name="method",
            file_path="test.py",
            start_line=1,
            end_line=3,
            source="def method(self): pass",
            class_name="MyClass",
        )
        assert info.qualified_name == "MyClass.method"
