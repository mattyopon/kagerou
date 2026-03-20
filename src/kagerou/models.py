"""Data models for Kagerou bug detection results."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    """Bug severity levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class BugCategory(str, Enum):
    """Categories of bugs that Kagerou can detect."""

    LOGIC_ERROR = "logic_error"
    OFF_BY_ONE = "off_by_one"
    NULL_REFERENCE = "null_reference"
    RESOURCE_LEAK = "resource_leak"
    TYPE_CONFUSION = "type_confusion"
    RACE_CONDITION = "race_condition"
    ERROR_HANDLING = "error_handling"
    BOUNDARY_VIOLATION = "boundary_violation"
    STATE_INCONSISTENCY = "state_inconsistency"
    SECURITY_VULNERABILITY = "security_vulnerability"


@dataclass(frozen=True)
class Location:
    """Source code location of a bug."""

    file_path: str
    start_line: int
    end_line: int
    function_name: str | None = None

    def __str__(self) -> str:
        loc = f"{self.file_path}:{self.start_line}"
        if self.end_line != self.start_line:
            loc += f"-{self.end_line}"
        if self.function_name:
            loc += f" ({self.function_name})"
        return loc


@dataclass(frozen=True)
class BugReport:
    """A single bug finding from Kagerou analysis."""

    title: str
    description: str
    category: BugCategory
    severity: Severity
    confidence: float  # 0.0 - 1.0
    location: Location
    code_snippet: str
    suggestion: str
    reasoning: str
    related_locations: list[Location] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        data["category"] = self.category.value
        data["severity"] = self.severity.value
        return data


@dataclass
class AnalysisResult:
    """Complete analysis result for a file or project."""

    target_path: str
    files_analyzed: int
    bugs: list[BugReport] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    analysis_time_seconds: float = 0.0

    @property
    def bug_count(self) -> int:
        """Total number of bugs found."""
        return len(self.bugs)

    @property
    def critical_count(self) -> int:
        """Number of critical bugs."""
        return sum(1 for b in self.bugs if b.severity == Severity.CRITICAL)

    @property
    def high_count(self) -> int:
        """Number of high severity bugs."""
        return sum(1 for b in self.bugs if b.severity == Severity.HIGH)

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        data = {
            "target_path": self.target_path,
            "files_analyzed": self.files_analyzed,
            "bug_count": self.bug_count,
            "critical_count": self.critical_count,
            "high_count": self.high_count,
            "analysis_time_seconds": self.analysis_time_seconds,
            "bugs": [b.to_dict() for b in self.bugs],
            "errors": self.errors,
        }
        return json.dumps(data, indent=indent, ensure_ascii=False)

    def merge(self, other: AnalysisResult) -> None:
        """Merge another result into this one."""
        self.bugs.extend(other.bugs)
        self.errors.extend(other.errors)
        self.files_analyzed += other.files_analyzed
        self.analysis_time_seconds += other.analysis_time_seconds
