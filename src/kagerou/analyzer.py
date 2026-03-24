# Copyright (c) 2026 Yutaro Maeda
# Licensed under the MIT License. See LICENSE file for details.

"""Core analysis engine that uses Claude API for semantic bug detection."""

from __future__ import annotations

import json
import time

import anthropic

from kagerou.models import (
    AnalysisResult,
    BugCategory,
    BugReport,
    Location,
    Severity,
)
from kagerou.parser import FileContext, FunctionInfo, collect_python_files, parse_file

# Map of category string values to enum members for parsing LLM output
_CATEGORY_MAP: dict[str, BugCategory] = {c.value: c for c in BugCategory}
_SEVERITY_MAP: dict[str, Severity] = {s.value: s for s in Severity}

SYSTEM_PROMPT = """\
You are Kagerou, an expert AI bug detector. Your task is to analyze Python code \
and find REAL bugs -- not style issues, not minor improvements, but actual logic \
bugs that could cause incorrect behavior, crashes, or security vulnerabilities.

Focus on these categories:
1. **Logic Errors**: Conditions that are always true/false, incorrect boolean logic, \
wrong variable used, inverted conditions
2. **Off-by-One**: Array index errors, loop boundary mistakes, fence-post errors
3. **Null/None References**: Accessing attributes on potentially None values, \
missing None checks after operations that can return None
4. **Resource Leaks**: Files, connections, or locks not properly closed/released
5. **Type Confusion**: Operations on wrong types, implicit type coercion bugs
6. **Race Conditions**: Shared state access without synchronization
7. **Error Handling**: Swallowed exceptions, wrong exception types caught, \
missing error handling for operations that can fail
8. **Boundary Violations**: Buffer overflows, integer overflow, unchecked input bounds
9. **State Inconsistency**: Object state that can become invalid, partial updates \
that leave data inconsistent
10. **Security Vulnerabilities**: SQL injection, path traversal, command injection, \
unsafe deserialization

RULES:
- Only report bugs you are CONFIDENT about (confidence >= 0.6)
- Each bug must have a clear explanation of WHY it's a bug and WHAT could go wrong
- Provide a specific fix suggestion
- Do NOT report: style issues, naming conventions, missing docstrings, or \
theoretical issues that require extremely unlikely conditions
- Focus on bugs that a human reviewer would likely miss
- Consider cross-function interactions: does function A pass data to function B \
in a way that could cause B to fail?

Respond with a JSON array of bug objects. If no bugs found, respond with [].
Each bug object must have these exact fields:
{
  "title": "Short descriptive title",
  "description": "Detailed explanation of the bug",
  "category": "one of: logic_error, off_by_one, null_reference, resource_leak, \
type_confusion, race_condition, error_handling, boundary_violation, \
state_inconsistency, security_vulnerability",
  "severity": "one of: critical, high, medium, low, info",
  "confidence": 0.0 to 1.0,
  "start_line": <int>,
  "end_line": <int>,
  "function_name": "name or null",
  "suggestion": "How to fix it",
  "reasoning": "Step-by-step reasoning of why this is a bug"
}
"""


def _build_analysis_prompt(file_ctx: FileContext) -> str:
    """Build the analysis prompt for a single file."""
    parts = [f"## File: {file_ctx.file_path}\n"]

    if file_ctx.imports:
        parts.append("### Imports:")
        parts.append("\n".join(f"  - {imp}" for imp in file_ctx.imports))
        parts.append("")

    if file_ctx.classes:
        parts.append(f"### Classes: {', '.join(file_ctx.classes)}")
        parts.append("")

    parts.append("### Source Code:")
    parts.append("```python")

    # Add line numbers for reference
    for i, line in enumerate(file_ctx.source.splitlines(), 1):
        parts.append(f"{i:4d} | {line}")

    parts.append("```")
    parts.append("")

    # Add function dependency info for cross-function analysis
    if file_ctx.functions:
        parts.append("### Function Dependency Map:")
        for func in file_ctx.functions:
            calls_str = ", ".join(func.calls) if func.calls else "none"
            parts.append(
                f"  - {func.qualified_name}(lines {func.start_line}-{func.end_line}) "
                f"calls: [{calls_str}]"
            )
        parts.append("")

    parts.append(
        "Analyze this code for bugs. Focus on logic errors, cross-function issues, "
        "and subtle bugs that static analysis tools would miss. "
        "Respond ONLY with a JSON array."
    )

    return "\n".join(parts)


def _build_cross_file_prompt(file_contexts: list[FileContext]) -> str:
    """Build a prompt for cross-file analysis."""
    parts = ["## Cross-File Analysis\n"]
    parts.append(
        "Analyze these files together for cross-file bugs: "
        "inconsistent interfaces, type mismatches between callers and callees, "
        "shared state issues.\n"
    )

    for ctx in file_contexts:
        parts.append(f"### {ctx.file_path}")
        if ctx.functions:
            for func in ctx.functions:
                sig_parts = [f"  - {func.qualified_name}("]
                sig_parts.append(", ".join(func.args))
                sig_parts.append(")")
                if func.docstring:
                    sig_parts.append(f' """{func.docstring[:100]}"""')
                parts.append("".join(sig_parts))
                if func.calls:
                    parts.append(f"    calls: {', '.join(func.calls)}")
        parts.append("")

    # Include abbreviated source for the most connected functions
    all_funcs: list[FunctionInfo] = []
    for ctx in file_contexts:
        all_funcs.extend(ctx.functions)

    # Sort by number of cross-references (most connected first)
    all_func_names = {f.name for f in all_funcs}
    connected = sorted(
        all_funcs,
        key=lambda f: sum(1 for c in f.calls if c in all_func_names),
        reverse=True,
    )

    parts.append("### Key Functions (most interconnected):")
    for func in connected[:10]:
        parts.append(f"\n#### {func.qualified_name} ({func.file_path}:{func.start_line})")
        parts.append("```python")
        parts.append(func.source)
        parts.append("```")

    parts.append(
        "\nAnalyze for cross-file bugs. Respond ONLY with a JSON array."
    )
    return "\n".join(parts)


def _parse_bug_reports(
    raw_response: str, file_path: str
) -> list[BugReport]:
    """Parse LLM response into BugReport objects."""
    # Extract JSON from response (handle markdown code blocks)
    text = raw_response.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # Remove first and last lines (```json and ```)
        json_lines = []
        in_block = False
        for line in lines:
            if line.startswith("```") and not in_block:
                in_block = True
                continue
            if line.startswith("```") and in_block:
                break
            if in_block:
                json_lines.append(line)
        text = "\n".join(json_lines)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON array in the text
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1:
            try:
                data = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return []
        else:
            return []

    if not isinstance(data, list):
        return []

    reports: list[BugReport] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            category = _CATEGORY_MAP.get(
                item.get("category", ""), BugCategory.LOGIC_ERROR
            )
            severity = _SEVERITY_MAP.get(
                item.get("severity", ""), Severity.MEDIUM
            )
            confidence = float(item.get("confidence", 0.5))

            # Skip low-confidence findings
            if confidence < 0.6:
                continue

            location = Location(
                file_path=file_path,
                start_line=int(item.get("start_line", 1)),
                end_line=int(item.get("end_line", item.get("start_line", 1))),
                function_name=item.get("function_name"),
            )

            # Extract code snippet from source
            code_snippet = item.get("code_snippet", "")

            report = BugReport(
                title=str(item.get("title", "Untitled bug")),
                description=str(item.get("description", "")),
                category=category,
                severity=severity,
                confidence=confidence,
                location=location,
                code_snippet=code_snippet,
                suggestion=str(item.get("suggestion", "")),
                reasoning=str(item.get("reasoning", "")),
            )
            reports.append(report)
        except (ValueError, KeyError, TypeError):
            continue

    return reports


class Analyzer:
    """Main analysis engine that coordinates parsing and LLM-based bug detection."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-20250514",
        max_files: int = 50,
        max_tokens: int = 4096,
    ) -> None:
        """Initialize the analyzer.

        Args:
            api_key: Anthropic API key. Uses ANTHROPIC_API_KEY env var if not provided.
            model: Claude model to use.
            max_files: Maximum number of files to analyze.
            max_tokens: Maximum tokens for LLM response.
        """
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_files = max_files
        self.max_tokens = max_tokens

    def _call_llm(self, prompt: str) -> str:
        """Call Claude API with the analysis prompt."""
        message = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        # Extract text from response
        text_parts: list[str] = []
        for block in message.content:
            if hasattr(block, "text"):
                text_parts.append(block.text)
        return "\n".join(text_parts)

    def analyze_file(self, file_path: str) -> AnalysisResult:
        """Analyze a single Python file for bugs.

        Args:
            file_path: Path to the Python file.

        Returns:
            AnalysisResult with any bugs found.
        """
        start_time = time.time()
        result = AnalysisResult(target_path=file_path, files_analyzed=1)

        file_ctx = parse_file(file_path)
        if file_ctx.parse_errors:
            result.errors.extend(file_ctx.parse_errors)
            if not file_ctx.source:
                result.analysis_time_seconds = time.time() - start_time
                return result

        prompt = _build_analysis_prompt(file_ctx)

        try:
            response = self._call_llm(prompt)
            bugs = _parse_bug_reports(response, file_path)

            # Enrich code snippets from source
            source_lines = file_ctx.source.splitlines()
            enriched_bugs: list[BugReport] = []
            for bug in bugs:
                if not bug.code_snippet:
                    start = max(0, bug.location.start_line - 1)
                    end = min(len(source_lines), bug.location.end_line)
                    snippet = "\n".join(source_lines[start:end])
                    # Create new BugReport with snippet (frozen dataclass)
                    bug = BugReport(
                        title=bug.title,
                        description=bug.description,
                        category=bug.category,
                        severity=bug.severity,
                        confidence=bug.confidence,
                        location=bug.location,
                        code_snippet=snippet,
                        suggestion=bug.suggestion,
                        reasoning=bug.reasoning,
                        related_locations=bug.related_locations,
                    )
                enriched_bugs.append(bug)

            result.bugs = enriched_bugs
        except anthropic.APIError as e:
            result.errors.append(f"API error: {e}")

        result.analysis_time_seconds = time.time() - start_time
        return result

    def analyze_directory(
        self,
        target_path: str,
        cross_file: bool = True,
    ) -> AnalysisResult:
        """Analyze a directory of Python files.

        Args:
            target_path: Path to the directory.
            cross_file: Whether to perform cross-file analysis.

        Returns:
            AnalysisResult with all bugs found.
        """
        start_time = time.time()
        result = AnalysisResult(target_path=target_path, files_analyzed=0)

        files = collect_python_files(target_path, max_files=self.max_files)
        if not files:
            result.errors.append(f"No Python files found in {target_path}")
            result.analysis_time_seconds = time.time() - start_time
            return result

        # Phase 1: Per-file analysis
        file_contexts: list[FileContext] = []
        for file_path in files:
            file_result = self.analyze_file(file_path)
            result.merge(file_result)
            file_ctx = parse_file(file_path)
            if not file_ctx.parse_errors:
                file_contexts.append(file_ctx)

        # Phase 2: Cross-file analysis (if enabled and multiple files)
        if cross_file and len(file_contexts) > 1:
            try:
                cross_prompt = _build_cross_file_prompt(file_contexts)
                response = self._call_llm(cross_prompt)
                cross_bugs = _parse_bug_reports(response, target_path)

                # Mark cross-file bugs
                for bug in cross_bugs:
                    result.bugs.append(bug)
            except anthropic.APIError as e:
                result.errors.append(f"Cross-file analysis error: {e}")

        # Sort bugs by severity then confidence
        severity_order = {
            Severity.CRITICAL: 0,
            Severity.HIGH: 1,
            Severity.MEDIUM: 2,
            Severity.LOW: 3,
            Severity.INFO: 4,
        }
        result.bugs.sort(
            key=lambda b: (severity_order.get(b.severity, 5), -b.confidence)
        )

        result.analysis_time_seconds = time.time() - start_time
        return result

    def analyze(self, target_path: str) -> AnalysisResult:
        """Analyze a file or directory.

        Args:
            target_path: Path to a file or directory.

        Returns:
            AnalysisResult with all bugs found.
        """
        from pathlib import Path

        path = Path(target_path)
        if path.is_file():
            return self.analyze_file(str(path))
        elif path.is_dir():
            return self.analyze_directory(str(path))
        else:
            result = AnalysisResult(target_path=target_path, files_analyzed=0)
            result.errors.append(f"Path not found: {target_path}")
            return result
