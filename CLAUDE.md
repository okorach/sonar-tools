# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

sonar-tools is a Python CLI application suite for SonarQube administration. It provides 17 CLI commands for auditing, exporting, syncing, and managing SonarQube instances (Server 9.9+, 2025.1+, 2026.1+, Community Build, and SonarQube Cloud). Published on PyPI as `sonar-tools`.

## Build & Development

**Build system:** Poetry (Python 3.9+)

```bash
# Install dependencies
poetry install

# Build package
poetry build

# Run all linters (ruff, pylint, flake8)
conf/run_linters.sh

# Run individual linters
ruff check .
pylint --rcfile conf/pylintrc sonar/ cli/
flake8 --config conf/.flake8 --exclude test/gen .

# Run tests with coverage
poetry run coverage run --branch --source=. -m pytest test/gen/latest/ test/gen/cb/ test/gen/99/ test/gen/cloud/ test/gen/common/ --junit-xml=build/xunit-results.xml
poetry run coverage xml -o build/coverage.xml

# Run a single test file
poetry run pytest test/gen/latest/test_projects.py

# Run a single test
poetry run pytest test/gen/latest/test_projects.py::test_function_name
```

Tests require running SonarQube instances with pre-provisioned test data. Test generation uses `test/build` to prepare test files in `test/gen/`. Unit tests are in `test/unit/`.

## Code Style

- Line length: 150 characters
- Ruff configured with `select = ["ALL"]` and specific ignores (see pyproject.toml)
- Double quotes for strings
- Target Python version: 3.9

## Architecture

### Package Structure

- **`sonar/`** - Core library: SonarQube object abstractions and API layer
- **`cli/`** - CLI entry points for most commands (findings-export, housekeeper, projects, measures, etc.)
- **`sonar/cli/`** - CLI entry points for audit, config, maturity, misra commands
- **`conf/`** - Build scripts, linter configs, Dockerfiles
- **`test/`** - Tests: `unit/` for unit tests, `gen/` for generated integration tests per SQ version

### Core Class Hierarchy

`SqObject` (`sonar/sqobject.py`) is the base class for all SonarQube entities. It provides caching via `SqObject.CACHE` and common API operations.

Key classes inheriting from `SqObject`:
- `Platform` (`sonar/platform.py`) - Main entry point representing a SonarQube instance. Manages API communication via `ApiManager`, handles authentication, and provides access to all SQ entities.
- `Project` (`sonar/projects.py`) - Project management (branches, PRs, settings, permissions, measures)
- `Finding` (`sonar/findings.py`) - Base for `Issue` (`sonar/issues.py`) and `Hotspot` (`sonar/hotspots.py`)
- `QualityProfile` / `QualityGate` / `Rule` - Quality management
- `Portfolio` / `Application` - Enterprise edition aggregation objects
- `User` / `Group` / `Token` - Identity management

### API Layer

`sonar/api/manager.py` contains `ApiManager` and `ApiOperation` for all HTTP communication with SonarQube. Version-specific API specs are in `sonar/api/*.json` (9.9, 2025.1, cloud).

`sonar/config.json` defines API endpoint configurations.

### Audit System

`sonar/audit/` contains the audit framework:
- `rules.json` - 200+ audit rule definitions
- `rules.py` / `problem.py` - Rule loading, checking, and problem representation
- `severities.py` / `types.py` - Severity levels and audit type definitions

### CLI Framework

`cli/options.py` centralizes command-line argument parsing. Common arguments: `-u` (URL), `-t` (token), `-o` (org), `-v` (verbose), `-f` (file format).

### Permissions

`sonar/permissions/` is a sub-package handling global, project, quality gate/profile, portfolio, application, and template permissions.

### Entry Points

All CLI commands are defined in `pyproject.toml` under `[project.scripts]`. Each maps to a `main()` function (e.g., `sonar-audit` -> `sonar.cli.audit:main`, `sonar-findings-export` -> `cli.findings_export:main`).

### Test Structure

Tests use pytest with fixtures defined in `test/unit/conftest.py`. Test utilities are in `test/unit/utilities.py`. The `tutil.SQ` object is the shared Platform endpoint for tests. Credential files (`test/unit/credentials*.py`) configure connections to different SQ versions.

### Error Handling

Exit codes are defined in `sonar/errcodes.py` (0=success through 17=server error). Custom exceptions are in `sonar/exceptions.py`.

<!-- sonar:begin:sonarqube-agentic-analysis-protocol -->
# SonarQube Agentic Analysis protocol

SonarQube Agentic Analysis is the final confirmation layer at the end of every turn in which you wrote to one or more files in the workspace (create, edit, patch, format — any tool call that changed file contents on disk).

**Trigger:** the moment before you send your final reply for the turn.

When the trigger fires, you **MUST** run SonarQube Agentic Analysis on the full set of files you modified this turn — **one command, not a per-file loop**.

**Preferred:** pass every path you modified this turn in a single invocation (repeat `--file` for each path). Use paths **relative to the project root** (e.g. `src/foo.ts`). For end-of-turn analysis, **always** pass `--depth DEEP` — even when you changed only one file — so cross-file findings are included.

```bash
sonar analyze agentic --project okorach-oss_sonar-tools --depth DEEP --file <path/to/file1> --file <path/to/file2>
```

**Fallback:** when you cannot reliably list every modified path (e.g. you did not track them, or git state is the only source of truth), use the git change set with DEEP analysis:

```bash
sonar analyze agentic --project okorach-oss_sonar-tools --depth DEEP
```

Per-edit hooks run faster STANDARD analysis. End-of-turn analysis must always use `--depth DEEP` (including a single `--file`). Use `--depth STANDARD` only for optional faster passes — never for the mandatory end-of-turn run.

Non-negotiable rules:

1. Mid-turn edits do **not** need SonarQube Agentic Analysis — only the final on-disk state matters. Skipping SonarQube Agentic Analysis at end-of-turn is a protocol violation.
2. Run SonarQube Agentic Analysis **before** sending your final reply, marking the task done, or handing control back to the user.
3. If SonarQube Agentic Analysis reports issues on lines you touched in this turn, fix them, then re-run SonarQube Agentic Analysis on the same scope (change set or explicit file list). Repeat until clean (or only pre-existing findings on lines you did not touch remain). Pre-existing findings on untouched lines are out of scope — do not "fix" them unless the user asked.
4. If SonarQube Agentic Analysis is skipped (no SonarQube Cloud connection, or no project configured), state the skip reason to the user once and continue — do not retry.
5. Do not suppress, summarize away, or omit SonarQube Agentic Analysis findings from your reply. Surface them verbatim.
<!-- sonar:end:sonarqube-agentic-analysis-protocol -->
