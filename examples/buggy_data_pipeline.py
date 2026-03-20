"""Example: A data processing pipeline with subtle logic bugs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Iterator


@dataclass
class DataRecord:
    """A single data record."""

    id: str
    timestamp: datetime
    value: float
    tags: dict[str, str] = field(default_factory=dict)
    _processed: bool = False

    def mark_processed(self) -> None:
        self._processed = True


class DataPipeline:
    """Processes data records through a series of transformations."""

    def __init__(self, batch_size: int = 100) -> None:
        self.batch_size = batch_size
        self.processors: list[callable] = []  # type: ignore[type-arg]
        self.error_count = 0
        self.processed_ids: set[str] = set()

    def add_processor(self, func: callable) -> None:  # type: ignore[type-arg]
        """Add a processing function to the pipeline."""
        self.processors.append(func)

    # BUG 1: Generator exhaustion - iterator consumed on first call only
    def process_stream(self, records: Iterator[DataRecord]) -> list[DataRecord]:
        """Process records from a stream."""
        results: list[DataRecord] = []

        # First pass: validate
        valid_records = [r for r in records if self._validate(r)]

        # BUG: 'records' iterator is exhausted, second pass gets nothing
        # Second pass: transform
        for record in records:  # This will yield nothing!
            for processor in self.processors:
                record = processor(record)
            results.append(record)

        return results

    def _validate(self, record: DataRecord) -> bool:
        """Validate a single record."""
        if not record.id:
            return False
        if record.value < 0:
            return False
        return True

    # BUG 2: Deduplication uses mutable set but doesn't account for order dependency
    def deduplicate(self, records: list[DataRecord]) -> list[DataRecord]:
        """Remove duplicate records, keeping the first occurrence."""
        seen: set[str] = set()
        result: list[DataRecord] = []
        for record in records:
            if record.id not in seen:
                result.append(record)
                # BUG 3: Never adds to 'seen', so no deduplication happens
        return result

    # BUG 4: Time window calculation is wrong
    def get_records_in_window(
        self,
        records: list[DataRecord],
        window_hours: int,
    ) -> list[DataRecord]:
        """Get records within the last N hours."""
        now = datetime.now()
        # BUG: Adding instead of subtracting - gets future records instead of past
        cutoff = now + timedelta(hours=window_hours)
        return [r for r in records if r.timestamp >= cutoff]

    # BUG 5: Aggregation loses precision due to running average calculation error
    def calculate_running_average(self, values: list[float]) -> list[float]:
        """Calculate running average of values."""
        if not values:
            return []

        averages: list[float] = []
        running_sum = 0.0
        for i, val in enumerate(values):
            running_sum += val
            # BUG: Division by i instead of (i+1), causing ZeroDivisionError on first element
            avg = running_sum / i
            averages.append(avg)

        return averages


def parse_log_line(line: str) -> dict[str, Any] | None:
    """Parse a structured log line.

    Expected format: [TIMESTAMP] LEVEL: message {json_payload}
    """
    # BUG 6: Regex doesn't handle multi-line messages or escaped brackets
    pattern = r"\[(.+?)\] (\w+): (.+?) ({.+})"
    match = re.match(pattern, line)
    if not match:
        return None

    timestamp_str, level, message, payload_str = match.groups()

    # BUG 7: No error handling for malformed JSON
    payload = json.loads(payload_str)

    return {
        "timestamp": timestamp_str,
        "level": level,
        "message": message,
        "payload": payload,
    }


def merge_configs(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge two configuration dictionaries.

    BUG 8: Shallow copy - mutations to nested dicts affect the original
    """
    result = base.copy()  # Shallow copy!
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            # Recursive merge, but base[key] is same reference as result[key]
            result[key] = merge_configs(result[key], value)
        else:
            result[key] = value
    return result


def retry_with_backoff(
    func: callable,  # type: ignore[type-arg]
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> Any:
    """Retry a function with exponential backoff.

    BUG 9: Catches all exceptions including KeyboardInterrupt and SystemExit
    BUG 10: No actual delay implemented (missing import time / sleep call)
    """
    last_exception: Exception | None = None
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:  # Too broad
            last_exception = e
            delay = base_delay * (2 ** attempt)
            # Forgot to actually sleep! Just calculates the delay
            continue

    raise last_exception  # type: ignore[misc]
