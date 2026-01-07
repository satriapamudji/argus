# Task 01: Project Scaffold + Configuration

## Summary
Fixed CLI test failures caused by missing `__main__.py` module entry point and incorrect module paths in test files.

## What It Was Before
- The CLI tests in `tests/test_cli.py` used `python -m argus.cli` to run the CLI
- Tests used `subprocess.os.environ` which is not valid Python (should be `os.environ`)
- Tests referenced incorrect parent directory paths for locating `bin/argus`
- The `argus` package lacked a `__main__.py` file, making `python -m argus` fail

## What Changed

### 1. Added `src/argus/__main__.py`
Created a new entry point file to enable running the module with `python -m argus`:
```python
"""Entry point for running argus as a module: python -m argus."""

from argus.cli import main

if __name__ == "__main__":
    main()
```

### 2. Fixed `tests/test_cli.py`
- Added missing `import os` statement
- Changed `subprocess.os.environ` to `os.environ` (5 occurrences)
- Changed `python -m argus.cli` to `python -m argus` (4 occurrences)
- Fixed path references from `Path(__file__).parent.parent.parent` to `Path(__file__).parent.parent`

### 3. Fixed `tests/test_config.py` (via ruff --fix)
- Removed unused imports: `pytest`, `DedupeConfig`, `EnrichmentConfig`, `RetentionConfig`, `RSSConfig`, `ScheduleConfig`, `StreamConfig`

## Reasoning

1. **`__main__.py`**: Python requires a `__main__.py` file in a package directory to run it as a module with `python -m package_name`. Without this, only `python -m argus.cli` would work (directly running the `cli` module), but the standard convention is to use the package name.

2. **Import fixes**: The tests incorrectly used `subprocess.os.environ`, which attempts to access `os` as an attribute of `subprocess`. This is a type error (as flagged by the LSP diagnostics). The correct approach is to import `os` directly and use `os.environ`.

3. **Path fixes**: The test file is at `tests/test_cli.py` and the project root is at `argus/`. The path `Path(__file__).parent.parent` correctly goes from `tests/test_cli.py` -> `tests/` -> `argus/` (project root). The previous code used `.parent.parent.parent` which went one level too high.

4. **Unused imports**: Cleaned up to satisfy linting (ruff F401) and keep the codebase clean.

## Verification Results
- `mypy src/`: Success - no issues found in 4 source files
- `ruff check src/ tests/`: All checks passed
- `pytest -v`: 13 tests passed

## Acceptance Criteria Met
- `bin/argus --help` works
- `bin/argus run --stream us_close_basic --mode us_close --dry-run` loads config and prints resolved settings
- All tests pass
