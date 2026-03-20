# Kagerou (陽炎)

**AI-powered logic bug detector that finds bugs hiding in plain sight.**

Kagerou uses Claude's semantic understanding to find real logic bugs that traditional static analysis tools miss. Named after the Japanese word for "heat haze" -- bugs that shimmer and hide in plain sight, invisible to conventional tools but revealed by AI.

## What Makes Kagerou Different

| Feature | Traditional SAST | Sashiko | Kagerou |
|---------|-----------------|---------|---------|
| Target | Pattern matching | Kernel patches (diffs) | Existing codebases |
| Focus | Known vulnerability patterns | Patch review | **Latent logic bugs** |
| Analysis | Single-file rules | Single-patch context | **Cross-function & cross-file** |
| Bugs Found | Style, known CVE patterns | Patch-introduced bugs | **Logic errors, semantic bugs** |

### Key Differentiators

- **Cross-function analysis**: Understands how data flows between functions and finds bugs at the boundaries
- **Semantic understanding**: Detects logic errors that require understanding the code's *intent*, not just its syntax
- **Existing code focus**: Finds bugs already hiding in your codebase, not just in new changes
- **10 bug categories**: Logic errors, off-by-one, null references, resource leaks, type confusion, race conditions, error handling gaps, boundary violations, state inconsistencies, security vulnerabilities

## Quick Start

```bash
# Install
pip install -e .

# Set your API key
export ANTHROPIC_API_KEY=your_key_here

# Scan a file
kagerou scan path/to/file.py

# Scan a directory
kagerou scan path/to/project/

# Output JSON report
kagerou scan src/ --output report.json

# Parse-only mode (no AI, shows code structure)
kagerou parse path/to/project/
```

## Example Output

```
╭──────────────── Kagerou Analysis Report ────────────────╮
│ Target: examples/buggy_server.py                        │
│ Files analyzed: 1                                       │
│ Bugs found: 8                                           │
│ Analysis time: 12.3s                                    │
╰─────────────────────────────────────────────────────────╯

  [!!!] #1 SQL Injection in get_user
      Category: security_vulnerability | Severity: critical | Confidence: 95%
      Location: examples/buggy_server.py:30-35 (get_user)

      User input is directly interpolated into SQL query string,
      allowing arbitrary SQL execution.

      Why this is a bug: The f-string builds a SQL query with unsanitized
      username input. An attacker can pass username like "' OR '1'='1"
      to bypass authentication or extract data.

      Fix: Use parameterized queries: cursor.execute(
        "SELECT ... WHERE username = ?", (username,))
```

## Architecture

```
Target Code
    │
    ▼
┌─────────────────┐
│   Parser (AST)  │  Extract functions, dependencies, call graph
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Analyzer      │  Per-file analysis + Cross-file analysis
│   (Claude API)  │  10 bug detection strategies
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Reporter      │  Rich terminal output + JSON export
└─────────────────┘
```

## Bug Categories

| Category | Description | Example |
|----------|-------------|---------|
| `logic_error` | Incorrect boolean logic, wrong variables | Checking `token` instead of `session` |
| `off_by_one` | Array bounds, loop boundaries | `page * size` instead of `(page-1) * size` |
| `null_reference` | Missing None checks | Accessing `.attr` on potentially None value |
| `resource_leak` | Unclosed files/connections | File opened but not closed on error path |
| `type_confusion` | Wrong type operations | Float comparison for money |
| `race_condition` | Shared state without sync | TOCTOU in file operations |
| `error_handling` | Swallowed/wrong exceptions | `except Exception` catching SystemExit |
| `boundary_violation` | Unchecked input bounds | No validation for negative amounts |
| `state_inconsistency` | Invalid object states | Partial updates without rollback |
| `security_vulnerability` | Injection, traversal, etc. | SQL injection, path traversal |

## Integration with Faultray

Kagerou is designed to complement [Faultray](https://github.com/mattyopon/faultray):

- **Faultray**: Analyzes failures *after* they happen (post-mortem)
- **Kagerou**: Finds bugs *before* they cause failures (prevention)

Together, they form a complete bug lifecycle: **Prevent** (Kagerou) -> **Detect** (monitoring) -> **Analyze** (Faultray) -> **Learn** (feed back to Kagerou).

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
make test

# Run linter
make lint

# Run type checker
make typecheck

# Run all quality checks
make quality
```

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `--model` | `claude-sonnet-4-20250514` | Claude model to use |
| `--max-files` | 50 | Maximum files to analyze |
| `--min-confidence` | 0.6 | Minimum confidence threshold |
| `--no-cross-file` | false | Disable cross-file analysis |
| `--output` | - | JSON output file path |

## License

MIT
