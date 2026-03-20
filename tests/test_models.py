"""Tests for the data models."""

from __future__ import annotations

import json

import pytest

from kagerou.models import (
    AnalysisResult,
    BugCategory,
    BugReport,
    Location,
    Severity,
)


class TestLocation:
    """Tests for Location dataclass."""

    def test_str_single_line(self) -> None:
        loc = Location(file_path="test.py", start_line=10, end_line=10)
        assert str(loc) == "test.py:10"

    def test_str_multi_line(self) -> None:
        loc = Location(file_path="test.py", start_line=10, end_line=15)
        assert str(loc) == "test.py:10-15"

    def test_str_with_function(self) -> None:
        loc = Location(
            file_path="test.py", start_line=10, end_line=15, function_name="my_func"
        )
        assert str(loc) == "test.py:10-15 (my_func)"

    def test_frozen(self) -> None:
        loc = Location(file_path="test.py", start_line=1, end_line=1)
        with pytest.raises(AttributeError):
            loc.start_line = 5  # type: ignore[misc]


class TestBugReport:
    """Tests for BugReport dataclass."""

    @pytest.fixture
    def sample_bug(self) -> BugReport:
        return BugReport(
            title="Test Bug",
            description="A test bug description",
            category=BugCategory.LOGIC_ERROR,
            severity=Severity.HIGH,
            confidence=0.85,
            location=Location(
                file_path="test.py", start_line=10, end_line=12, function_name="buggy"
            ),
            code_snippet="x = 1\ny = 2",
            suggestion="Fix the logic",
            reasoning="Because X should be Y",
        )

    def test_to_dict(self, sample_bug: BugReport) -> None:
        d = sample_bug.to_dict()
        assert d["title"] == "Test Bug"
        assert d["category"] == "logic_error"
        assert d["severity"] == "high"
        assert d["confidence"] == 0.85

    def test_to_dict_serializable(self, sample_bug: BugReport) -> None:
        d = sample_bug.to_dict()
        # Should be JSON-serializable
        json_str = json.dumps(d)
        assert json_str  # non-empty

    def test_frozen(self, sample_bug: BugReport) -> None:
        with pytest.raises(AttributeError):
            sample_bug.title = "Modified"  # type: ignore[misc]


class TestAnalysisResult:
    """Tests for AnalysisResult dataclass."""

    @pytest.fixture
    def result_with_bugs(self) -> AnalysisResult:
        bugs = [
            BugReport(
                title="Critical Bug",
                description="",
                category=BugCategory.SECURITY_VULNERABILITY,
                severity=Severity.CRITICAL,
                confidence=0.9,
                location=Location("a.py", 1, 1),
                code_snippet="",
                suggestion="",
                reasoning="",
            ),
            BugReport(
                title="High Bug",
                description="",
                category=BugCategory.LOGIC_ERROR,
                severity=Severity.HIGH,
                confidence=0.8,
                location=Location("b.py", 5, 10),
                code_snippet="",
                suggestion="",
                reasoning="",
            ),
            BugReport(
                title="Medium Bug",
                description="",
                category=BugCategory.OFF_BY_ONE,
                severity=Severity.MEDIUM,
                confidence=0.7,
                location=Location("a.py", 20, 25),
                code_snippet="",
                suggestion="",
                reasoning="",
            ),
        ]
        return AnalysisResult(
            target_path="/test/project",
            files_analyzed=5,
            bugs=bugs,
            analysis_time_seconds=2.5,
        )

    def test_bug_count(self, result_with_bugs: AnalysisResult) -> None:
        assert result_with_bugs.bug_count == 3

    def test_critical_count(self, result_with_bugs: AnalysisResult) -> None:
        assert result_with_bugs.critical_count == 1

    def test_high_count(self, result_with_bugs: AnalysisResult) -> None:
        assert result_with_bugs.high_count == 1

    def test_to_json(self, result_with_bugs: AnalysisResult) -> None:
        json_str = result_with_bugs.to_json()
        data = json.loads(json_str)
        assert data["bug_count"] == 3
        assert data["critical_count"] == 1
        assert data["files_analyzed"] == 5
        assert len(data["bugs"]) == 3

    def test_empty_result(self) -> None:
        result = AnalysisResult(target_path="/test", files_analyzed=0)
        assert result.bug_count == 0
        assert result.critical_count == 0
        assert result.high_count == 0

    def test_merge(self) -> None:
        r1 = AnalysisResult(target_path="/test", files_analyzed=2)
        r1.bugs.append(
            BugReport(
                title="Bug 1",
                description="",
                category=BugCategory.LOGIC_ERROR,
                severity=Severity.LOW,
                confidence=0.7,
                location=Location("a.py", 1, 1),
                code_snippet="",
                suggestion="",
                reasoning="",
            )
        )

        r2 = AnalysisResult(target_path="/test2", files_analyzed=3)
        r2.bugs.append(
            BugReport(
                title="Bug 2",
                description="",
                category=BugCategory.OFF_BY_ONE,
                severity=Severity.HIGH,
                confidence=0.8,
                location=Location("b.py", 1, 1),
                code_snippet="",
                suggestion="",
                reasoning="",
            )
        )
        r2.errors.append("Some error")

        r1.merge(r2)
        assert r1.files_analyzed == 5
        assert r1.bug_count == 2
        assert len(r1.errors) == 1
