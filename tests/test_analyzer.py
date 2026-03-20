"""Tests for the analyzer module (unit tests, no API calls)."""

from __future__ import annotations

import json

from kagerou.analyzer import _build_analysis_prompt, _parse_bug_reports
from kagerou.models import BugCategory, Severity
from kagerou.parser import parse_file


class TestParseBugReports:
    """Tests for _parse_bug_reports function."""

    def test_parses_valid_json(self) -> None:
        raw = json.dumps([
            {
                "title": "Test Bug",
                "description": "A bug",
                "category": "logic_error",
                "severity": "high",
                "confidence": 0.85,
                "start_line": 10,
                "end_line": 12,
                "function_name": "my_func",
                "suggestion": "Fix it",
                "reasoning": "Because reasons",
            }
        ])
        bugs = _parse_bug_reports(raw, "test.py")
        assert len(bugs) == 1
        assert bugs[0].title == "Test Bug"
        assert bugs[0].category == BugCategory.LOGIC_ERROR
        assert bugs[0].severity == Severity.HIGH
        assert bugs[0].confidence == 0.85
        assert bugs[0].location.file_path == "test.py"
        assert bugs[0].location.start_line == 10

    def test_handles_markdown_wrapped_json(self) -> None:
        bug_json = json.dumps([{
            "title": "Bug", "description": "", "category": "off_by_one",
            "severity": "medium", "confidence": 0.7, "start_line": 1,
            "end_line": 1, "function_name": None, "suggestion": "", "reasoning": "",
        }])
        raw = f"```json\n{bug_json}\n```"
        bugs = _parse_bug_reports(raw, "test.py")
        assert len(bugs) == 1
        assert bugs[0].category == BugCategory.OFF_BY_ONE

    def test_filters_low_confidence(self) -> None:
        raw = json.dumps([
            {
                "title": "Low confidence",
                "description": "",
                "category": "logic_error",
                "severity": "low",
                "confidence": 0.3,
                "start_line": 1,
                "end_line": 1,
                "function_name": None,
                "suggestion": "",
                "reasoning": "",
            }
        ])
        bugs = _parse_bug_reports(raw, "test.py")
        assert len(bugs) == 0

    def test_handles_empty_array(self) -> None:
        bugs = _parse_bug_reports("[]", "test.py")
        assert bugs == []

    def test_handles_invalid_json(self) -> None:
        bugs = _parse_bug_reports("not json at all", "test.py")
        assert bugs == []

    def test_handles_json_with_extra_text(self) -> None:
        bug_json = json.dumps([{
            "title": "Bug", "description": "", "category": "logic_error",
            "severity": "high", "confidence": 0.8, "start_line": 1,
            "end_line": 1, "function_name": None, "suggestion": "fix",
            "reasoning": "reason",
        }])
        raw = f"Here are the bugs I found:\n{bug_json}\nEnd of analysis."
        bugs = _parse_bug_reports(raw, "test.py")
        assert len(bugs) == 1

    def test_handles_multiple_bugs(self) -> None:
        raw = json.dumps([
            {
                "title": f"Bug {i}",
                "description": "",
                "category": "logic_error",
                "severity": "medium",
                "confidence": 0.7,
                "start_line": i * 10,
                "end_line": i * 10 + 5,
                "function_name": f"func_{i}",
                "suggestion": "",
                "reasoning": "",
            }
            for i in range(5)
        ])
        bugs = _parse_bug_reports(raw, "test.py")
        assert len(bugs) == 5

    def test_handles_unknown_category(self) -> None:
        raw = json.dumps([
            {
                "title": "Bug",
                "description": "",
                "category": "unknown_category",
                "severity": "high",
                "confidence": 0.8,
                "start_line": 1,
                "end_line": 1,
                "function_name": None,
                "suggestion": "",
                "reasoning": "",
            }
        ])
        bugs = _parse_bug_reports(raw, "test.py")
        assert len(bugs) == 1
        # Falls back to LOGIC_ERROR
        assert bugs[0].category == BugCategory.LOGIC_ERROR

    def test_handles_missing_optional_fields(self) -> None:
        raw = json.dumps([
            {
                "title": "Minimal Bug",
                "category": "high",
                "confidence": 0.75,
                "start_line": 5,
            }
        ])
        bugs = _parse_bug_reports(raw, "test.py")
        assert len(bugs) == 1


class TestBuildAnalysisPrompt:
    """Tests for _build_analysis_prompt function."""

    def test_includes_file_path(self, tmp_path: object) -> None:
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("def hello():\n    return 'world'\n")
            f.flush()
            ctx = parse_file(f.name)
            prompt = _build_analysis_prompt(ctx)
            assert f.name in prompt

    def test_includes_source_with_line_numbers(self) -> None:
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("x = 1\ny = 2\n")
            f.flush()
            ctx = parse_file(f.name)
            prompt = _build_analysis_prompt(ctx)
            assert "1 |" in prompt or "   1 |" in prompt

    def test_includes_function_dependency_map(self) -> None:
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("def a():\n    b()\ndef b():\n    pass\n")
            f.flush()
            ctx = parse_file(f.name)
            prompt = _build_analysis_prompt(ctx)
            assert "Function Dependency Map" in prompt
            assert "a" in prompt
